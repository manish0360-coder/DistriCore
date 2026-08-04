"""Domain exceptions.

Every error the API can return carries a stable machine-readable ``code`` that clients
branch on (05 §5). ``title`` and ``detail`` are for humans and may be reworded without
breaking a client.

Business rules raise these from ``services.py``. The delivery layer translates them
into RFC 9457 problem documents; it never invents its own errors.
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base for every expected, business-meaningful failure."""

    code: str = "DOMAIN_ERROR"
    title: str = "Domain error"
    status: int = 400

    def __init__(self, detail: str = "", **extra: Any) -> None:
        self.detail = detail or self.title
        self.extra = extra
        super().__init__(self.detail)


# --- authentication ---------------------------------------------------------
class InvalidCredentials(DomainError):
    code, title, status = "INVALID_CREDENTIALS", "Invalid credentials", 401


class AccountInactive(DomainError):
    code, title, status = "ACCOUNT_INACTIVE", "Account is inactive", 403


class OtpInvalid(DomainError):
    code, title, status = "OTP_INVALID", "Invalid code", 422


class OtpExpired(DomainError):
    code, title, status = "OTP_EXPIRED", "Code has expired", 422


class OtpAttemptsExceeded(DomainError):
    code, title, status = "OTP_ATTEMPTS_EXCEEDED", "Too many attempts", 429


class RefreshExpired(DomainError):
    code, title, status = "REFRESH_EXPIRED", "Session expired", 401


class OtpRateLimited(DomainError):
    code, title, status = "OTP_RATE_LIMITED", "Too many requests", 429


# --- authorisation and validation -------------------------------------------
class PermissionDenied(DomainError):
    code, title, status = "PERMISSION_DENIED", "Permission denied", 403


class ResourceNotFound(DomainError):
    """Also returned for a resource outside the caller's scope (05 §4.1).

    A 403 would confirm the resource exists, which is an information disclosure.
    Scope violations are indistinguishable from non-existence, deliberately.
    """

    code, title, status = "RESOURCE_NOT_FOUND", "Not found", 404


class ValidationFailed(DomainError):
    code, title, status = "VALIDATION_FAILED", "Validation failed", 422

    def __init__(self, detail: str = "", errors: list[dict[str, str]] | None = None) -> None:
        super().__init__(detail)
        self.errors = errors or []


# --- infrastructure ---------------------------------------------------------
class SmsDeliveryFailed(DomainError):
    code, title, status = "SMS_DELIVERY_FAILED", "Could not send the code", 503
