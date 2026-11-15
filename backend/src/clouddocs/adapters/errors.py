"""Translate botocore errors into application errors with client-safe messages."""

from __future__ import annotations

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
