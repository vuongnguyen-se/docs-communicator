import pytest

from clouddocs.config import Settings
from clouddocs.errors import ValidationFailed
from clouddocs.validators import (
    build_s3_key,
    clean_filename,
    document_id_from_key,
    looks_like_pdf,
    validate_question,
    validate_upload_request,
)

S = Settings()


def test_rejects_non_pdf_content_type():
    with pytest.raises(ValidationFailed):
        validate_upload_request("a.pdf", "image/png", 10, S)


@pytest.mark.parametrize("size", [0, -1, S.max_file_bytes + 1])
def test_rejects_bad_sizes(size):
    with pytest.raises(ValidationFailed):
        validate_upload_request("a.pdf", "application/pdf", size, S)


def test_accepts_max_size():
    assert validate_upload_request("a.pdf", "application/pdf", S.max_file_bytes, S) == "a.pdf"


@pytest.mark.parametrize("name", ["", "a.txt", ".pdf", "a.pdf.exe", "   "])
def test_rejects_bad_filenames(name):
    with pytest.raises(ValidationFailed):
        clean_filename(name, 200)


def test_filename_strips_path_and_control_chars():
    assert clean_filename("../../etc/passwd\x00/evil\n.pdf", 200) == "evil.pdf"


def test_filename_keeps_vietnamese():
    assert clean_filename("Tài liệu AWS.pdf", 200) == "Tài liệu AWS.pdf"


def test_question_limits():
    with pytest.raises(ValidationFailed):
        validate_question("   ", S)
    with pytest.raises(ValidationFailed):
        validate_question("x" * (S.max_question_chars + 1), S)
    assert validate_question("  hi  ", S) == "hi"


def test_s3_key_is_server_generated_and_round_trips():
    doc_id = "doc_" + "a" * 32
    key = build_s3_key("user-1", doc_id)
    assert key == f"uploads/user-1/{doc_id}.pdf"
    assert document_id_from_key(key) == doc_id


@pytest.mark.parametrize("user", ["../x", "a/b", "", "a b"])
def test_user_id_cannot_escape_prefix(user):
    with pytest.raises(ValidationFailed):
        build_s3_key(user, "doc_" + "a" * 32)


def test_pdf_magic():
    assert looks_like_pdf(b"%PDF-1.4")
    assert not looks_like_pdf(b"MZ\x90\x00")
