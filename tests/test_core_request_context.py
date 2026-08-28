from __future__ import annotations

import uuid

from src.core.request_context import (
    bind_request_id,
    get_request_id,
    new_request_id,
    normalize_request_id,
    reset_request_id,
)


def test_new_request_id_is_a_valid_uuid() -> None:
    value = new_request_id()
    assert uuid.UUID(value)


def test_normalize_accepts_well_formed_candidate() -> None:
    assert normalize_request_id("abc-123.XYZ:1") == "abc-123.XYZ:1"


def test_normalize_strips_whitespace() -> None:
    assert normalize_request_id("  abc123  ") == "abc123"


def test_normalize_replaces_none() -> None:
    value = normalize_request_id(None)
    assert uuid.UUID(value)


def test_normalize_replaces_empty_string() -> None:
    value = normalize_request_id("")
    assert uuid.UUID(value)


def test_normalize_replaces_malformed_candidate() -> None:
    # Contains a space, which is outside the allowed pattern.
    value = normalize_request_id("not a valid id!!")
    assert uuid.UUID(value)


def test_normalize_rejects_leading_disallowed_character() -> None:
    value = normalize_request_id("-leading-dash")
    assert uuid.UUID(value)


def test_bind_and_get_request_id_round_trip() -> None:
    token = bind_request_id("req-round-trip")
    try:
        assert get_request_id() == "req-round-trip"
    finally:
        reset_request_id(token)


def test_get_request_id_default_is_unbound() -> None:
    assert get_request_id() == "unbound"


def test_reset_restores_previous_value() -> None:
    outer_token = bind_request_id("outer")
    try:
        inner_token = bind_request_id("inner")
        assert get_request_id() == "inner"
        reset_request_id(inner_token)
        assert get_request_id() == "outer"
    finally:
        reset_request_id(outer_token)
