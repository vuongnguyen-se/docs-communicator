"""Lambda handler for POST /chat/query."""

from __future__ import annotations

from ..container import get_services
from ..errors import NotFound
from ..models import ChatRequest
from .common import Event, Response, json_response, parse_body, user_id_from_event, wrap


def _route(event: Event, rid: str) -> Response:
    if event.get("routeKey") != "POST /chat/query":
        raise NotFound("Route not found")
    user = user_id_from_event(event)
    answer, citations = get_services().chat.query(user, parse_body(event, ChatRequest))
    return json_response(
        200,
        {
            "answer": answer,
            "citations": [c.model_dump(by_alias=True) for c in citations],
            "requestId": rid,
        },
        rid,
    )


handler = wrap(_route)
