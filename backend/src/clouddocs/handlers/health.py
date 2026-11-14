"""Lambda handler for GET /health (non-sensitive, unauthenticated-safe)."""

from __future__ import annotations

from .common import Event, Response, json_response, wrap


def _route(event: Event, rid: str) -> Response:
    return json_response(200, {"status": "ok"}, rid)


handler = wrap(_route)
