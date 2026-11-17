"""Lambda handler for GET /me: echoes the caller's identity from the verified JWT.

Used to prove end-to-end auth (Cognito -> API Gateway JWT authorizer -> Lambda)
before any data endpoints exist. Returns only the opaque user id.
"""

from __future__ import annotations

from .common import Event, Response, json_response, user_id_from_event, wrap


def _route(event: Event, rid: str) -> Response:
    return json_response(200, {"userId": user_id_from_event(event)}, rid)


handler = wrap(_route)
