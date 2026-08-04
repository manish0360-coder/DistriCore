"""Request-scoped context.

A context variable rather than thread-local storage: it is correct under async and
under threads, and it is what lets a log line and an audit row share a request id
without threading it through every function signature.
"""

from __future__ import annotations

from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("request_id", default="")


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str:
    return _request_id.get()
