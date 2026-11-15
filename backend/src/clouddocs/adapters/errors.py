"""Translate botocore errors into application errors with client-safe messages."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from ..errors import UpstreamUnavailable

_TRANSIENT = {
    "ThrottlingException",
    "TooManyRequestsException",
    "ServiceUnavailableException",
    "InternalServerException",
    "ModelTimeoutException",
    "ProvisionedThroughputExceededException",
    "RequestLimitExceeded",
    "SlowDown",
    "ServiceUnavailable",
    "InternalError",
}


def aws_error_code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


def call[T](fn: Callable[..., T], **kwargs: Any) -> T:
    """Invoke a boto3 method; map transient/connection failures to UpstreamUnavailable.

    Other ClientErrors propagate unchanged so callers can handle specific codes.
    """
    try:
        return fn(**kwargs)
    except ClientError as exc:
        if aws_error_code(exc) in _TRANSIENT:
            raise UpstreamUnavailable("Upstream service is busy; retry later") from exc
        raise
    except BotoCoreError as exc:
        raise UpstreamUnavailable("Upstream service is unreachable; retry later") from exc


def call_retry_conflict[T](
    fn: Callable[..., T],
    *,
    attempts: int = 3,
    delay: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> T:
    """Like call(), but retries ConflictException (e.g. an overlapping sync) with backoff.

    After the last attempt the conflict becomes UpstreamUnavailable so callers can retry later.
    """
    for attempt in range(attempts):
        try:
            return call(fn, **kwargs)
        except ClientError as exc:
            if aws_error_code(exc) != "ConflictException":
                raise
            if attempt == attempts - 1:
                raise UpstreamUnavailable("Index is busy; retry later") from exc
            sleep(delay * 2**attempt)
    raise AssertionError("unreachable")  # pragma: no cover
