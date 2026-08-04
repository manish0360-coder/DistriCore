"""Request correlation (00 §12).

Accepts an inbound ``X-Request-Id`` (so a mobile client can correlate its own retry
chain) or generates one, and echoes it on the response. The value appears on every log
line and on every audit row written during the request.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from core.context import set_request_id

HEADER = "X-Request-Id"
_MAX_LEN = 64


class RequestIdMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get(HEADER, "")
        # Never trust an unbounded client-supplied value into a log field.
        request_id = incoming[:_MAX_LEN] if incoming.isascii() and incoming else uuid.uuid4().hex
        set_request_id(request_id)
        request.request_id = request_id  # type: ignore[attr-defined]
        response = self.get_response(request)
        response[HEADER] = request_id
        return response
