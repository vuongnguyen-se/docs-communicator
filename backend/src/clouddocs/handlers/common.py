"""Shared HTTP plumbing for API Gateway HTTP API (payload v2) Lambda handlers."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from ..errors import AppError, ServiceBusy, Unauthorized, ValidationFailed

log = logging.getLogger("clouddocs.http")

Event = dict[str, Any]
Response = dict[str, Any]
MAX_BODY_BYTES = 16 * 1024

# AWS error codes that mean "busy or briefly unavailable": safe to tell the user to retry (P5-05).
_RETRYABLE = {
    "ThrottlingException",
    "TooManyRequestsException",
    "ProvisionedThroughputExceededException",
    "RequestLimitExceeded",
    "ServiceQuotaExceededException",
    "ServiceUnavailableException",
    "ServiceUnavailable",
    "SlowDown",
    "InternalServerException",
}


def aws_error_code(exc: BaseException) -> str | None:
    """The AWS error code of a botocore ClientError (duck-typed: no botocore import here)."""
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = (response.get("Error") or {}).get("Code")
        return str(code) if code else None
    return None


def request_id(event: Event) -> str:
    return str((event.get("requestContext") or {}).get("requestId") or "unknown")


def user_id_from_event(event: Event) -> str:
    """Identity comes only from the validated JWT authorizer context, never from the request."""
    claims = (((event.get("requestContext") or {}).get("authorizer") or {}).get("jwt") or {}).get(
        "claims"
    ) or {}
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise Unauthorized("Authentication required")
    return sub


def parse_body[T: BaseModel](event: Event, model: type[T]) -> T:
    raw = event.get("body") or ""
    if len(raw.encode("utf-8")) > MAX_BODY_BYTES:
        raise ValidationFailed("Request body too large")
    try:
        return model.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValidationFailed("Invalid request body") from exc


def json_response(status: int, body: dict[str, Any] | None, rid: str) -> Response:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json", "x-request-id": rid},
        "body": json.dumps(body, ensure_ascii=False) if body is not None else "",
    }


def error_response(err: AppError, rid: str) -> Response:
    return json_response(
        err.status, {"error": {"code": err.code, "message": err.message}, "requestId": rid}, rid
    )


def wrap(fn: Callable[[Event, str], Response]) -> Callable[[Event, Any], Response]:
    """Map exceptions to structured, non-sensitive errors and log with the request id."""

    def handler(event: Event, context: Any) -> Response:
        rid = request_id(event)
        try:
            return fn(event, rid)
        except AppError as err:
            log.info(json.dumps({"requestId": rid, "errorCode": err.code}))
            return error_response(err, rid)
        except Exception as exc:
            code = aws_error_code(exc)
            if code in _RETRYABLE:
                log.warning(
                    json.dumps({"requestId": rid, "errorCode": "SERVICE_BUSY", "aws": code})
                )
                busy = ServiceBusy("The service is busy right now. Wait a moment and try again.")
                return error_response(busy, rid)
            # Details (incl. AWS code) go to the logs only; the client gets a generic message.
            log.exception(
                json.dumps({"requestId": rid, "errorCode": "INTERNAL_ERROR", "aws": code})
            )
            return error_response(AppError("Internal error"), rid)

    return handler
