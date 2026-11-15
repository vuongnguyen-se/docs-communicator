"""Bedrock Knowledge Base adapter (direct document ingestion + RetrieveAndGenerate).

UNVERIFIED against the live service (tracked as a Phase 2 spike): request/response shapes
follow the botocore service model; real-world status timing and whether the chosen data
source type accepts S3-location direct ingestion must be confirmed in ap-southeast-1.
"""

from __future__ import annotations

from typing import Any

from ..models import IndexState, RagResult
from ..services.rag import parse_retrieve_and_generate
from .errors import call

# Only a fully INDEXED document is searchable with its metadata. Partial states are treated
# as FAILED so a document is never reported READY while its isolation metadata is missing.
_STATE_MAP: dict[str, IndexState] = {
    "INDEXED": IndexState.INDEXED,
    "PENDING": IndexState.IN_PROGRESS,
    "STARTING": IndexState.IN_PROGRESS,
    "IN_PROGRESS": IndexState.IN_PROGRESS,
    "DELETING": IndexState.IN_PROGRESS,
    "DELETE_IN_PROGRESS": IndexState.IN_PROGRESS,
    "NOT_FOUND": IndexState.NOT_FOUND,
    "FAILED": IndexState.FAILED,
    "PARTIALLY_INDEXED": IndexState.FAILED,
    "METADATA_PARTIALLY_INDEXED": IndexState.FAILED,
    "METADATA_UPDATE_FAILED": IndexState.FAILED,
    "IGNORED": IndexState.FAILED,
}


def map_document_status(status: str) -> IndexState:
    # Unknown future statuses are treated as FAILED rather than guessed.
    return _STATE_MAP.get(status, IndexState.FAILED)


class BedrockKnowledgeBase:
    def __init__(
        self,
        agent_client: Any,
        runtime_client: Any,
        *,
        knowledge_base_id: str,
        data_source_id: str,
        bucket: str,
        model_arn: str,
    ) -> None:
        self._agent, self._rt = agent_client, runtime_client
        self._kb, self._ds, self._bucket, self._model = (
            knowledge_base_id,
            data_source_id,
            bucket,
            model_arn,
        )

    def _uri(self, s3_key: str) -> str:
        return f"s3://{self._bucket}/{s3_key}"

    def ingest(self, s3_key: str, owner_id: str, document_id: str) -> None:
        def attr(key: str, value: str) -> dict[str, Any]:
            return {"key": key, "value": {"type": "STRING", "stringValue": value}}

        call(
            self._agent.ingest_knowledge_base_documents,
            knowledgeBaseId=self._kb,
            dataSourceId=self._ds,
            documents=[
                {
                    "content": {
                        "dataSourceType": "S3",
                        "s3": {"s3Location": {"uri": self._uri(s3_key)}},
                    },
                    # Retrieval metadata for future per-owner filtering (Phase 4 isolation).
                    "metadata": {
                        "type": "IN_LINE_ATTRIBUTE",
                        "inlineAttributes": [
                            attr("ownerId", owner_id),
                            attr("documentId", document_id),
                        ],
                    },
                }
            ],
        )

    def index_state(self, s3_key: str) -> IndexState:
        resp = call(
            self._agent.get_knowledge_base_documents,
            knowledgeBaseId=self._kb,
            dataSourceId=self._ds,
            documentIdentifiers=[{"dataSourceType": "S3", "s3": {"uri": self._uri(s3_key)}}],
        )
        details = resp.get("documentDetails") or []
        if not details:
            return IndexState.NOT_FOUND
        return map_document_status(str(details[0].get("status", "")))

    def delete(self, s3_key: str) -> None:
        call(
            self._agent.delete_knowledge_base_documents,
            knowledgeBaseId=self._kb,
            dataSourceId=self._ds,
            documentIdentifiers=[{"dataSourceType": "S3", "s3": {"uri": self._uri(s3_key)}}],
        )

    def query(self, question: str) -> RagResult:
        resp = call(
            self._rt.retrieve_and_generate,
            input={"text": question},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": self._kb,
                    "modelArn": self._model,
                },
            },
        )
        return parse_retrieve_and_generate(resp)
