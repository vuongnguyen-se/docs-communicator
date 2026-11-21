"""Ingestion worker: SQS messages with S3 events -> complete_upload, partial batch retries."""

import json
from urllib.parse import quote_plus

from clouddocs.handlers import ingest_worker
from clouddocs.models import DocumentStatus as S

from .conftest import USER_A, USER_B, Env


def s3_body(*keys: str) -> str:
    return json.dumps(
        {
            "Records": [
                {
                    "eventSource": "aws:s3",
                    "eventName": "ObjectCreated:Post",
                    "s3": {"bucket": {"name": "docs"}, "object": {"key": quote_plus(k)}},
                }
                for k in keys
            ]
        }
    )


def sqs_event(*bodies: str) -> dict:
    return {"Records": [{"messageId": f"m{i}", "body": b} for i, b in enumerate(bodies)]}


def run(*bodies: str) -> list[str]:
    out = ingest_worker.handler(sqs_event(*bodies), None)
    return [f["itemIdentifier"] for f in out["batchItemFailures"]]


def test_uploaded_pdf_is_verified_and_sent_for_indexing(env: Env):
    doc = env.upload_pdf()
    assert run(s3_body(doc.s3_key)) == []
    assert env.repo.get(USER_A, doc.document_id).status == S.INDEXING


def test_fake_pdf_fails_and_its_file_is_deleted(env: Env):
    doc = env.upload_pdf(data=b"just text, renamed .pdf")
    assert run(s3_body(doc.s3_key)) == []
    stored = env.repo.get(USER_A, doc.document_id)
    assert stored.status == S.FAILED and stored.error_code == "INVALID_FILE"
    assert doc.s3_key not in env.storage.objects


def test_repeated_message_is_a_no_op(env: Env):
    doc = env.upload_pdf()
    body = s3_body(doc.s3_key)
    assert run(body) == [] and run(body) == []
    assert env.repo.get(USER_A, doc.document_id).status == S.INDEXING


def test_keys_that_are_not_uploads_are_skipped(env: Env):
    doc = env.upload_pdf()
    sidecar = doc.s3_key + ".metadata.json"
    assert run(s3_body(sidecar, "other/file.pdf", "uploads/x/not-a-doc.pdf")) == []
    assert env.repo.get(USER_A, doc.document_id).status == S.PENDING_UPLOAD


def test_upload_without_a_record_is_skipped(env: Env):
    assert run(s3_body(f"uploads/{USER_B}/doc_{'f' * 32}.pdf")) == []


def test_s3_test_event_is_ignored(env: Env):
    assert run(json.dumps({"Service": "Amazon S3", "Event": "s3:TestEvent"})) == []


def test_one_event_with_two_uploads(env: Env):
    a, b = env.upload_pdf(name="a.pdf"), env.upload_pdf(user=USER_B, name="b.pdf")
    assert run(s3_body(a.s3_key, b.s3_key)) == []
    assert env.repo.get(USER_A, a.document_id).status == S.INDEXING
    assert env.repo.get(USER_B, b.document_id).status == S.INDEXING


def test_only_the_failing_message_is_retried(env: Env, monkeypatch):
    ok, broken = env.upload_pdf(name="ok.pdf"), env.upload_pdf(name="broken.pdf")
    real_get = env.repo.get

    def flaky_get(owner, document_id):
        if document_id == broken.document_id:
            raise RuntimeError("DynamoDB throttled")
        return real_get(owner, document_id)

    monkeypatch.setattr(env.repo, "get", flaky_get)
    assert run(s3_body(ok.s3_key), s3_body(broken.s3_key)) == ["m1"]
    assert real_get(USER_A, ok.document_id).status == S.INDEXING


def test_unreadable_message_is_retried_so_it_reaches_the_dead_letter_queue(env: Env):
    assert run("not json") == ["m0"]
