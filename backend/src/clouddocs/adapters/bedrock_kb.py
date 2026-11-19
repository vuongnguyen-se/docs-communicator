"""Bedrock Knowledge Base implementation of the KnowledgeBase port (Phase 3, D-006).

Formats proven in spike P0-07 (docs/spikes/2026-11-19-knowledge-base-spike.md):
- An S3 data source rejects inline metadata, so the owner and document id go in a
  sidecar object "<pdf key>.metadata.json" written by this Lambda (never the browser).
- Documents are added, checked and removed one at a time; no data-source sync.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ..models import IndexState, RagResult

if TYPE_CHECKING:
    from mypy_boto3_bedrock_agent.client import AgentsforBedrockClient
    from mypy_boto3_bedrock_agent.type_defs import DocumentIdentifierTypeDef
    from mypy_boto3_s3.client import S3Client

METADATA_SUFFIX = ".metadata.json"

# Bedrock document status -> our provider-neutral IndexState.
# Partial results count as FAILED: a chunk indexed without its userId metadata could
# escape the per-user filter, so "READY" must mean fully indexed with metadata.
_STATUS_MAP = {
    "INDEXED": IndexState.INDEXED,
    "NOT_FOUND": IndexState.NOT_FOUND,
    "FAILED": IndexState.FAILED,
    "PARTIALLY_INDEXED": IndexState.FAILED,
    "METADATA_PARTIALLY_INDEXED": IndexState.FAILED,
    "METADATA_UPDATE_FAILED": IndexState.FAILED,
    "IGNORED": IndexState.FAILED,
}


class IngestRejected(RuntimeError):
    """Bedrock refused the ingestion request for this document."""


def metadata_document(owner_id: str, document_id: str) -> bytes:
    return json.dumps(
        {"metadataAttributes": {"userId": owner_id, "documentId": document_id}}
    ).encode()


class BedrockKnowledgeBase:
    def __init__(
        self,
        agent: AgentsforBedrockClient,
        s3: S3Client,
        *,
        knowledge_base_id: str,
        data_source_id: str,
        bucket: str,
    ) -> None:
        self._agent, self._s3 = agent, s3
        self._kb, self._ds, self._bucket = knowledge_base_id, data_source_id, bucket

    def _uri(self, s3_key: str) -> str:
        return f"s3://{self._bucket}/{s3_key}"

    def _identifier(self, s3_key: str) -> DocumentIdentifierTypeDef:
        return {"dataSourceType": "S3", "s3": {"uri": self._uri(s3_key)}}

    def ingest(self, s3_key: str, owner_id: str, document_id: str) -> None:
        self._s3.put_object(
            Bucket=self._bucket,
            Key=s3_key + METADATA_SUFFIX,
            Body=metadata_document(owner_id, document_id),
            ContentType="application/json",
        )
        resp = self._agent.ingest_knowledge_base_documents(
            knowledgeBaseId=self._kb,
            dataSourceId=self._ds,
            documents=[
                {
                    "content": {
                        "dataSourceType": "S3",
                        "s3": {"s3Location": {"uri": self._uri(s3_key)}},
                    },
                    "metadata": {
                        "type": "S3_LOCATION",
                        "s3Location": {"uri": self._uri(s3_key + METADATA_SUFFIX)},
                    },
                }
            ],
        )
        details = resp.get("documentDetails") or []
        if not details or details[0].get("status") == "FAILED":
            reason = details[0].get("statusReason", "") if details else "no document details"
            raise IngestRejected(reason)

    def index_state(self, s3_key: str) -> IndexState:
        resp = self._agent.get_knowledge_base_documents(
            knowledgeBaseId=self._kb,
            dataSourceId=self._ds,
            documentIdentifiers=[self._identifier(s3_key)],
        )
        details = resp.get("documentDetails") or []
        if not details:
            return IndexState.NOT_FOUND
        return _STATUS_MAP.get(details[0]["status"], IndexState.IN_PROGRESS)

    def delete(self, s3_key: str) -> None:
        self._agent.delete_knowledge_base_documents(
            knowledgeBaseId=self._kb,
            dataSourceId=self._ds,
            documentIdentifiers=[self._identifier(s3_key)],
        )
        self._s3.delete_object(Bucket=self._bucket, Key=s3_key + METADATA_SUFFIX)

    def query(self, question: str) -> RagResult:
        # Phase 4 (P4-01/P4-02): RetrieveAndGenerate MUST be filtered by the caller's
        # userId. Refuse rather than ever run an unfiltered query.
        raise NotImplementedError("Chat is enabled in Phase 4 with a per-user retrieval filter")
