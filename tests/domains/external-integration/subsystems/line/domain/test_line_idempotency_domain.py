"""Module tests for shared LINE idempotency replay rules."""

import pytest

from domains.line.idempotency import (
    LineIdempotencyConflict,
    LineIdempotencyOutcome,
    resolve_line_idempotency,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import IdempotencyKey, IdempotencyReceipt


def test_missing_receipt_allows_new_command() -> None:
    result = resolve_line_idempotency(
        None,
        IdempotencyKey("delivery:1"),
        fingerprint_payload({"message": "hello"}),
    )

    assert result.outcome is LineIdempotencyOutcome.CREATED


def test_same_key_and_payload_returns_existing_result() -> None:
    fingerprint = fingerprint_payload({"message": "hello"})
    key = IdempotencyKey("delivery:1")
    receipt = IdempotencyReceipt(key, fingerprint, "line-task:10")

    result = resolve_line_idempotency(receipt, key, fingerprint)

    assert result.outcome is LineIdempotencyOutcome.EXISTING
    assert result.existing_result_reference == "line-task:10"


def test_same_key_with_different_payload_is_conflict() -> None:
    key = IdempotencyKey("delivery:1")
    receipt = IdempotencyReceipt(
        key,
        fingerprint_payload({"message": "hello"}),
        "line-task:10",
    )

    with pytest.raises(LineIdempotencyConflict):
        resolve_line_idempotency(
            receipt,
            key,
            fingerprint_payload({"message": "changed"}),
        )
