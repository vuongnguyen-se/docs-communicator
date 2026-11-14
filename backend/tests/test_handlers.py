import json

from clouddocs.handlers import chat, documents, health

from .conftest import USER_A, USER_B, Env, api_event


def body(resp):
    return json.loads(resp["body"]) if resp["body"] else None


def test_health():
    resp = health.handler(api_event("GET /health", user=None), None)
    assert resp["statusCode"] == 200 and body(resp) == {"status": "ok"}


def test_unauthenticated_request_is_401(env: Env):
    resp = documents.handler(api_event("GET /documents", user=None), None)
    assert resp["statusCode"] == 401
    assert body(resp)["error"]["code"] == "UNAUTHORIZED"


def test_full_flow_through_handlers(env: Env):
    resp = documents.handler(
        api_event(
            "POST /documents/upload-url",
            body={"filename": "a.pdf", "contentType": "application/pdf", "size": 12},
        ),
        None,
    )
    assert resp["statusCode"] == 201
    data = body(resp)
    doc_id = data["document"]["documentId"]
    assert "s3Key" not in json.dumps(data) and "ownerId" not in json.dumps(data)
    assert data["upload"]["url"].startswith("https://")

    env.storage.objects[f"uploads/{USER_A}/{doc_id}.pdf"] = b"%PDF-1.7 xx"
    resp = documents.handler(api_event("POST /documents/{id}/complete", path_id=doc_id), None)
    assert resp["statusCode"] == 202 and body(resp)["document"]["status"] == "INDEXING"

    resp = documents.handler(api_event("GET /documents"), None)
    assert [d["documentId"] for d in body(resp)["documents"]] == [doc_id]

    resp = documents.handler(api_event("DELETE /documents/{id}", path_id=doc_id), None)
    assert resp["statusCode"] == 204


def test_other_user_gets_404_not_403(env: Env):
    doc = env.upload_pdf(USER_A)
    resp = documents.handler(
        api_event("GET /documents/{id}", user=USER_B, path_id=doc.document_id), None
    )
    assert resp["statusCode"] == 404


def test_invalid_body_is_400_and_extra_fields_rejected(env: Env):
    resp = documents.handler(
        api_event(
            "POST /documents/upload-url",
            body={"filename": "a.pdf", "contentType": "application/pdf", "size": 1, "ownerId": "x"},
        ),
        None,
    )
    assert resp["statusCode"] == 400
    assert (
        documents.handler(api_event("POST /documents/upload-url", body="nope"), None)["statusCode"]
        == 400
    )


def test_invalid_document_id_is_400(env: Env):
    resp = documents.handler(api_event("GET /documents/{id}", path_id="../x"), None)
    assert resp["statusCode"] == 400


def test_chat_shape_matches_contract(env: Env):
    from clouddocs.models import RagResult, RetrievedReference

    doc = env.upload_pdf(name="aws-notes.pdf")
    env.kb.result = RagResult(
        answer="ok", references=[RetrievedReference(s3_uri=f"s3://b/{doc.s3_key}", text="snippet")]
    )
    resp = chat.handler(api_event("POST /chat/query", body={"question": "hi"}), None)
    data = body(resp)
    assert resp["statusCode"] == 200
    assert data["citations"] == [
        {"documentId": doc.document_id, "documentName": "aws-notes.pdf", "excerpt": "snippet"}
    ]
    assert data["requestId"] == "req-1"


def test_unexpected_error_is_500_without_details(env: Env):
    def boom(*_a, **_k):
        raise RuntimeError("secret internal detail")

    env.kb.query = boom  # type: ignore[method-assign]
    resp = chat.handler(api_event("POST /chat/query", body={"question": "hi"}), None)
    assert resp["statusCode"] == 500
    assert "secret" not in resp["body"]
