from __future__ import annotations

from src.domain.errors import (
    BusinessRuleViolationError,
    DomainError,
    IllegalStateTransitionError,
    InvariantViolationError,
)


def test_domain_error_defaults() -> None:
    err = DomainError("something failed")
    assert err.code == "domain_error"
    assert err.message == "something failed"
    assert err.details == {}
    assert str(err) == "something failed"


def test_domain_error_copies_details() -> None:
    details = {"field": "x"}
    err = DomainError("failed", details=details)
    details["field"] = "mutated"
    assert err.details == {"field": "x"}


def test_invariant_violation_error_code() -> None:
    assert InvariantViolationError("bad value").code == "invariant_violation"


def test_illegal_state_transition_error_code() -> None:
    assert IllegalStateTransitionError("bad transition").code == "illegal_state_transition"


def test_business_rule_violation_error_code() -> None:
    assert BusinessRuleViolationError("limit exceeded").code == "business_rule_violation"
