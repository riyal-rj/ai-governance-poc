"""Request scoped correlation state backed by context variables."""

from __future__ import annotations

import re
from contextvars import ContextVar, Token
from uuid import uuid4

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_request_id: ContextVar[str] = ContextVar("request_id", default="unbound")

def new_request_id() -> str:
    """Create a a globally unique server generated correlation identifier."""
    return str(uuid4())

def normalize_request_id(candidate: str | None) -> str:
    """Accept a safe upstream ID or replace malformed input with a UUID"""

    if candidate and _REQUEST_ID_PATTERN.fullmatch(candidate.strip()):
        return candidate.strip()

    return new_request_id()

def bind_request_id(request_id: str) -> Token:
    """Bind a request ID to the current aync exceution context."""
    return _request_id.set(request_id)

def reset_request_id(token: Token[str]) -> None:
    """Restore the previous context after a request finishes."""

def get_request_id() -> str:
    """Return the ID associated with the current request or the task."""
    return _request_id.get()

