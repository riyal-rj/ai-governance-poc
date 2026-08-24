from __future__ import annotations

from collections.abc import Mapping
from typing import Any

class DomainError(Exception):
    """Base Error raised when a business invariant rejects an operation."""

    code ="domain_error"

    def __init__(self,message: str,*,
                 details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message=message
        self.details = dict(details or {})

class InvariantViloationError(DomainError):
    """Raised when supplied values violate an aggregate invariant."""

    code = "invariant_violation"

class IllegalStateTransitionError(DomainError):
    """Raised when an aggregate cannot legally move to the requested state."""
    code = "illegal_state_transition"

class BusinessRuleViolationError(DomainError):
    """Raised when a valid command is rejected by a named business rule."""

    code="business_rule_violation"