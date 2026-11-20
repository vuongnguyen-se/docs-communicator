"""Application errors. Messages are safe to return to clients."""

from __future__ import annotations


class AppError(Exception):
    status = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str = "Internal error") -> None:
        super().__init__(message)
        self.message = message


class ValidationFailed(AppError):
    status = 400
    code = "VALIDATION_ERROR"


class Unauthorized(AppError):
    status = 401
    code = "UNAUTHORIZED"


class NotFound(AppError):
    status = 404
    code = "NOT_FOUND"


class Conflict(AppError):
    status = 409
    code = "CONFLICT"


class LimitExceeded(AppError):
    status = 409
    code = "LIMIT_EXCEEDED"


class ServiceBusy(AppError):
    status = 503
    code = "SERVICE_BUSY"


class UpstreamUnavailable(AppError):
    status = 503
    code = "UPSTREAM_UNAVAILABLE"
