"""Parsing of a Bedrock RetrieveAndGenerate response into a provider-neutral RagResult.

Response shape (confirmed live in spike P0-07, 2026-11-19):
  {"output": {"text": "..."},
   "citations": [{"retrievedReferences": [
       {"content": {"text": "..."}, "location": {"s3Location": {"uri": "s3://bucket/key"}}}]}]}
"""

from __future__ import annotations

from typing import Any

from ..models import RagResult, RetrievedReference


def parse_retrieve_and_generate(response: dict[str, Any]) -> RagResult:
    answer = str((response.get("output") or {}).get("text") or "")
    refs: list[RetrievedReference] = []
    for citation in response.get("citations") or []:
        for ref in citation.get("retrievedReferences") or []:
            text = (ref.get("content") or {}).get("text")
            uri = ((ref.get("location") or {}).get("s3Location") or {}).get("uri")
            if isinstance(text, str) and isinstance(uri, str):
                refs.append(RetrievedReference(s3_uri=uri, text=text))
    return RagResult(answer=answer, references=refs)
