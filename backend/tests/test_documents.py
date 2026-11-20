import pytest

from clouddocs.errors import (
    Conflict,
    LimitExceeded,
    NotFound,
    UpstreamUnavailable,
    ValidationFailed,
)
from clouddocs.models import DocumentStatus as S
from clouddocs.models import IndexState, UploadUrlRequest

from .conftest import USER_A, USER_B, Env


def test_request_upload_creates_pending_doc_with_server_key(env: Env):
    doc = env.upload_pdf()
    assert doc.status == S.PENDING_UPLOAD
    assert doc.s3_key == f"uploads/{USER_A}/{doc.document_id}.pdf"


def test_request_upload_validates(env: Env):
    with pytest.raises(ValidationFailed):
        env.docs.request_upload(
            USER_A, UploadUrlRequest(filename="a.pdf", contentType="text/plain", size=5)
        )


def test_document_limit(env: Env):
    for i in range(3):
        env.upload_pdf(name=f"{i}.pdf")
    with pytest.raises(LimitExceeded):
        env.upload_pdf(name="extra.pdf")


def test_complete_starts_indexing(env: Env):
    doc = env.upload_pdf()
    done = env.docs.complete_upload(USER_A, doc.document_id)
    assert done.status == S.INDEXING
    assert env.kb.index_state(doc.s3_key) == IndexState.IN_PROGRESS


def test_complete_is_idempotent_and_does_not_reingest(env: Env):
    doc = env.upload_pdf()
    env.docs.complete_upload(USER_A, doc.document_id)
    env.kb.states[doc.s3_key] = IndexState.INDEXED
    again = env.docs.complete_upload(USER_A, doc.document_id)
    assert again.status == S.INDEXING
    assert env.kb.states[doc.s3_key] == IndexState.INDEXED  # not reset by a second ingest


def test_complete_without_object_conflicts(env: Env):
    doc = env.upload_pdf()
    del env.storage.objects[doc.s3_key]
    with pytest.raises(Conflict):
        env.docs.complete_upload(USER_A, doc.document_id)


def test_complete_rejects_non_pdf_content_and_removes_object(env: Env):
    doc = env.upload_pdf(data=b"MZ not a pdf")
    result = env.docs.complete_upload(USER_A, doc.document_id)
    assert result.status == S.FAILED and result.error_code == "INVALID_FILE"
    assert doc.s3_key not in env.storage.objects
    assert env.kb.states == {}


def test_complete_rejects_oversize_actual_object(env: Env):
    doc = env.upload_pdf()
    env.storage.objects[doc.s3_key] = b"%PDF-" + b"0" * env.settings.max_file_bytes
    assert env.docs.complete_upload(USER_A, doc.document_id).status == S.FAILED


def test_ingest_failure_marks_failed_visibly(env: Env):
    env.kb.ingest_error = RuntimeError("boom")
    doc = env.upload_pdf()
    result = env.docs.complete_upload(USER_A, doc.document_id)
    assert result.status == S.FAILED and result.error_code == "INGEST_REQUEST_FAILED"


def test_status_only_ready_after_index_confirms(env: Env):
    doc = env.upload_pdf()
    env.docs.complete_upload(USER_A, doc.document_id)
    assert env.docs.get_document(USER_A, doc.document_id).status == S.INDEXING
    env.kb.states[doc.s3_key] = IndexState.INDEXED
    assert env.docs.get_document(USER_A, doc.document_id).status == S.READY


def test_index_failure_surfaces(env: Env):
    doc = env.upload_pdf()
    env.docs.complete_upload(USER_A, doc.document_id)
    env.kb.states[doc.s3_key] = IndexState.FAILED
    got = env.docs.get_document(USER_A, doc.document_id)
    assert got.status == S.FAILED and got.error_code == "INDEXING_FAILED"


def test_transient_status_error_keeps_indexing(env: Env):
    doc = env.upload_pdf()
    env.docs.complete_upload(USER_A, doc.document_id)

    def boom(_key: str) -> IndexState:
        raise RuntimeError("throttled")

    env.kb.index_state = boom  # type: ignore[method-assign]
    assert env.docs.get_document(USER_A, doc.document_id).status == S.INDEXING


def test_other_users_cannot_see_or_touch_document(env: Env):
    doc = env.upload_pdf(USER_A)
    with pytest.raises(NotFound):
        env.docs.get_document(USER_B, doc.document_id)
    with pytest.raises(NotFound):
        env.docs.complete_upload(USER_B, doc.document_id)
    with pytest.raises(NotFound):
        env.docs.delete_document(USER_B, doc.document_id)
    assert env.docs.list_documents(USER_B) == []
    assert doc.s3_key in env.storage.objects


def test_delete_removes_index_object_and_record(env: Env):
    doc = env.upload_pdf()
    env.docs.complete_upload(USER_A, doc.document_id)
    assert env.docs.delete_document(USER_A, doc.document_id) is None
    assert doc.s3_key not in env.storage.objects
    assert env.kb.index_state(doc.s3_key) == IndexState.NOT_FOUND
    assert env.repo.get(USER_A, doc.document_id) is None


def test_delete_keeps_deleting_until_index_confirms(env: Env):
    doc = env.upload_pdf()
    env.docs.complete_upload(USER_A, doc.document_id)
    env.kb.delete_completes = False
    pending = env.docs.delete_document(USER_A, doc.document_id)
    assert pending is not None and pending.status == S.DELETING
    assert doc.s3_key in env.storage.objects  # source kept until index removal verified
    env.kb.delete_completes = True
    assert env.docs.delete_document(USER_A, doc.document_id) is None


def test_delete_request_failure_keeps_data_and_stays_deleting(env: Env):
    doc = env.upload_pdf()
    env.docs.complete_upload(USER_A, doc.document_id)

    def boom(_key: str) -> None:
        raise RuntimeError("down")

    env.kb.delete = boom  # type: ignore[method-assign]
    pending = env.docs.delete_document(USER_A, doc.document_id)
    assert pending is not None and pending.status == S.DELETING  # index still has it
    assert doc.s3_key in env.storage.objects


def test_delete_is_503_when_the_index_cannot_be_checked(env: Env):
    doc = env.upload_pdf()
    env.docs.complete_upload(USER_A, doc.document_id)

    def boom(_key: str) -> IndexState:
        raise RuntimeError("down")

    env.kb.index_state = boom  # type: ignore[method-assign]
    with pytest.raises(UpstreamUnavailable):
        env.docs.delete_document(USER_A, doc.document_id)
    assert doc.s3_key in env.storage.objects


def test_list_finishes_a_pending_delete_once_the_index_confirms(env: Env):
    doc = env.upload_pdf()
    env.docs.complete_upload(USER_A, doc.document_id)
    env.kb.delete_completes = False
    assert env.docs.delete_document(USER_A, doc.document_id).status == S.DELETING
    env.kb.states.pop(doc.s3_key)  # the index finishes on its own, later
    assert env.docs.list_documents(USER_A) == []
    assert doc.s3_key not in env.storage.objects
    assert env.repo.get(USER_A, doc.document_id) is None


def test_get_of_a_finished_delete_is_404(env: Env):
    doc = env.upload_pdf()
    env.docs.complete_upload(USER_A, doc.document_id)
    env.kb.delete_completes = False
    env.docs.delete_document(USER_A, doc.document_id)
    env.kb.states.pop(doc.s3_key)
    with pytest.raises(NotFound):
        env.docs.get_document(USER_A, doc.document_id)


def test_delete_of_never_indexed_document_succeeds_even_if_kb_refuses(env: Env):
    doc = env.upload_pdf()  # PENDING_UPLOAD: never sent to the index

    def refuse(_key: str) -> None:
        raise RuntimeError("ValidationException: unknown document")

    env.kb.delete = refuse  # type: ignore[method-assign]
    assert env.docs.delete_document(USER_A, doc.document_id) is None
    assert env.repo.get(USER_A, doc.document_id) is None
