import pytest

from clouddocs.errors import ValidationFailed
from clouddocs.models import ChatRequest, RagResult, RetrievedReference
from clouddocs.services.chat import NO_EVIDENCE_MESSAGE
from clouddocs.services.rag import parse_retrieve_and_generate

from .conftest import USER_A, USER_B, Env


def ref(doc, text="SQS is a queue."):
    return RetrievedReference(s3_uri=f"s3://bucket/{doc.s3_key}", text=text)


def test_answer_with_resolved_citation(env: Env):
    doc = env.upload_pdf(name="aws-notes.pdf")
    env.kb.result = RagResult(answer="SQS buffers messages.", references=[ref(doc)])
    answer, cites = env.chat.query(USER_A, ChatRequest(question="What is SQS?"))
    assert answer == "SQS buffers messages."
    assert cites[0].document_name == "aws-notes.pdf"
    assert cites[0].document_id == doc.document_id


def test_no_references_means_uncertainty_and_no_citations(env: Env):
    env.kb.result = RagResult(answer="The capital of France is Paris.", references=[])
    answer, cites = env.chat.query(USER_A, ChatRequest(question="Capital of France?"))
    assert answer == NO_EVIDENCE_MESSAGE
    assert cites == []


def test_citation_to_other_users_document_is_dropped(env: Env):
    other = env.upload_pdf(USER_B, name="secret.pdf")
    env.kb.result = RagResult(answer="leaked", references=[ref(other, "secret text")])
    answer, cites = env.chat.query(USER_A, ChatRequest(question="anything"))
    assert cites == [] and answer == NO_EVIDENCE_MESSAGE


def test_unknown_or_malformed_uris_are_ignored(env: Env):
    env.kb.result = RagResult(
        answer="x",
        references=[
            RetrievedReference(s3_uri="https://evil/x", text="t"),
            RetrievedReference(s3_uri="s3://b/uploads/u/../etc.pdf", text="t"),
        ],
    )
    assert env.chat.query(USER_A, ChatRequest(question="q"))[1] == []


def test_duplicate_excerpts_collapsed_and_whitespace_normalised(env: Env):
    doc = env.upload_pdf()
    env.kb.result = RagResult(answer="a", references=[ref(doc, "a  b\n c"), ref(doc, "a b c")])
    _, cites = env.chat.query(USER_A, ChatRequest(question="q"))
    assert [c.excerpt for c in cites] == ["a b c"]


def test_question_length_enforced_before_calling_kb(env: Env):
    with pytest.raises(ValidationFailed):
        env.chat.query(USER_A, ChatRequest(question="x" * 5000))
    assert env.kb.queries == []


def test_parse_bedrock_response():
    resp = {
        "output": {"text": "Answer"},
        "citations": [
            {
                "retrievedReferences": [
                    {
                        "content": {"text": "passage"},
                        "location": {"s3Location": {"uri": "s3://b/uploads/u/doc.pdf"}},
                    },
                    {"content": {"text": "no location"}},
                ]
            }
        ],
    }
    result = parse_retrieve_and_generate(resp)
    assert result.answer == "Answer"
    assert [(r.s3_uri, r.text) for r in result.references] == [
        ("s3://b/uploads/u/doc.pdf", "passage")
    ]


def test_parse_empty_response():
    assert parse_retrieve_and_generate({}).references == []


def test_retrieval_is_always_scoped_to_the_caller(env: Env):
    env.chat.query(USER_A, ChatRequest(question="What is SQS?"))
    env.chat.query(USER_B, ChatRequest(question="What is SQS?"))
    assert env.kb.queries == [("What is SQS?", USER_A), ("What is SQS?", USER_B)]
