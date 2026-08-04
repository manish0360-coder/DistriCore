"""RFC 9457 problem+json for every error (AD-03).

The API never returns DRF's default shapes, which differ between validation errors
(a dict) and permission errors (a string) and push that inconsistency onto the client.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_handler

from core.context import get_request_id
from core.exceptions import DomainError, ResourceNotFound, ValidationFailed

logger = logging.getLogger("districore.api")

PROBLEM_CONTENT_TYPE = "application/problem+json"
TYPE_BASE = "https://districore.app/errors/"


def _problem(
    *,
    code: str,
    title: str,
    status: int,
    detail: str,
    instance: str,
    errors: list[Any] | None = None,
) -> Response:
    body: dict[str, Any] = {
        "type": f"{TYPE_BASE}{code.lower().replace('_', '-')}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": instance,
        "code": code,
        "request_id": get_request_id(),
        "errors": errors or [],
    }
    return Response(body, status=status, content_type=PROBLEM_CONTENT_TYPE)


def _flatten_drf_errors(detail: Any, prefix: str = "") -> list[dict[str, str]]:
    """Turn DRF's nested error structure into the flat, dotted-path shape of 05 §5.4."""
    out: list[dict[str, str]] = []
    if isinstance(detail, dict):
        for key, value in detail.items():
            out.extend(_flatten_drf_errors(value, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(detail, list):
        for index, value in enumerate(detail):
            if isinstance(value, (dict, list)):
                out.extend(_flatten_drf_errors(value, f"{prefix}[{index}]"))
            else:
                out.append(
                    {
                        "field": prefix or "non_field",
                        "code": getattr(value, "code", "INVALID").upper(),
                        "message": str(value),
                    }
                )
    else:
        out.append(
            {
                "field": prefix or "non_field",
                "code": getattr(detail, "code", "INVALID").upper(),
                "message": str(detail),
            }
        )
    return out


def problem_detail_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    request = context.get("request")
    instance = getattr(request, "path", "")

    # 1. Our own domain errors carry their own stable code.
    if isinstance(exc, DomainError):
        errors = getattr(exc, "errors", [])
        return _problem(
            code=exc.code,
            title=exc.title,
            status=exc.status,
            detail=exc.detail,
            instance=instance,
            errors=errors,
        )

    # 2. Scope violations look exactly like non-existence (05 §4.1).
    if isinstance(exc, (Http404, drf.NotFound)):
        not_found = ResourceNotFound()
        return _problem(
            code=not_found.code,
            title=not_found.title,
            status=not_found.status,
            detail=not_found.detail,
            instance=instance,
        )

    if isinstance(exc, (DjangoPermissionDenied, drf.PermissionDenied)):
        return _problem(
            code="PERMISSION_DENIED",
            title="Permission denied",
            status=403,
            detail="You do not have permission to perform this action.",
            instance=instance,
        )

    if isinstance(exc, drf.NotAuthenticated):
        return _problem(
            code="TOKEN_INVALID",
            title="Authentication required",
            status=401,
            detail="Authentication credentials were not supplied.",
            instance=instance,
        )

    if isinstance(exc, drf.AuthenticationFailed):
        code = "TOKEN_EXPIRED" if "expired" in str(exc.detail).lower() else "TOKEN_INVALID"
        return _problem(
            code=code,
            title="Authentication failed",
            status=401,
            detail=str(exc.detail),
            instance=instance,
        )

    if isinstance(exc, drf.Throttled):
        response = _problem(
            code="RATE_LIMITED",
            title="Too many requests",
            status=429,
            detail=f"Rate limit exceeded. Retry in {exc.wait or 60:.0f} seconds.",
            instance=instance,
        )
        response["Retry-After"] = str(int(exc.wait or 60))
        return response

    if isinstance(exc, drf.ValidationError):
        invalid = ValidationFailed()
        return _problem(
            code=invalid.code,
            title=invalid.title,
            status=422,  # 422, not 400: understood perfectly, values invalid (05 §4.1)
            detail="One or more fields are invalid.",
            instance=instance,
            errors=_flatten_drf_errors(exc.detail),
        )

    if isinstance(exc, drf.ParseError):
        return _problem(
            code="MALFORMED_REQUEST",
            title="Malformed request",
            status=400,
            detail="The request body could not be parsed.",
            instance=instance,
        )

    # 3. Anything else DRF understands.
    response = drf_handler(exc, context)
    if response is not None:
        return _problem(
            code="REQUEST_FAILED",
            title="Request failed",
            status=response.status_code,
            detail=str(getattr(exc, "detail", "")) or "The request could not be completed.",
            instance=instance,
        )

    # 4. Unhandled — logged with a stack trace, never disclosed (NFR-SEC-010).
    logger.exception("unhandled_exception", extra={"path": instance})
    return None
