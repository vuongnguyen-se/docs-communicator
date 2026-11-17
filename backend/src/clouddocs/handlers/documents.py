"""Lambda handler for /documents routes."""

from __future__ import annotations

from ..container import get_services
from ..errors import NotFound
from ..models import UploadUrlRequest
from .common import Event, Response, json_response, parse_body, user_id_from_event, wrap


def _route(event: Event, rid: str) -> Response:
    user = user_id_from_event(event)
    svc = get_services().documents
    route = event.get("routeKey", "")
    params = event.get("pathParameters") or {}

    if route == "POST /documents/upload-url":
        doc, post = svc.request_upload(user, parse_body(event, UploadUrlRequest))
        return json_response(
            201,
            {
                "document": doc.public(),
                "upload": post.model_dump(),
                "expiresInSeconds": get_services().settings.upload_url_ttl_seconds,
            },
            rid,
        )
    if route == "POST /documents/{id}/complete":
        return json_response(
            202, {"document": svc.complete_upload(user, params.get("id", "")).public()}, rid
        )
    if route == "GET /documents":
        return json_response(
            200, {"documents": [d.public() for d in svc.list_documents(user)]}, rid
        )
    if route == "GET /documents/{id}":
        return json_response(
            200, {"document": svc.get_document(user, params.get("id", "")).public()}, rid
        )
    if route == "DELETE /documents/{id}":
        remaining = svc.delete_document(user, params.get("id", ""))
        if remaining is None:
            return json_response(204, None, rid)
        return json_response(202, {"document": remaining.public()}, rid)
    raise NotFound("Route not found")


handler = wrap(_route)
