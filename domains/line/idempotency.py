"""Shared idempotency resolution rules for LINE application commands."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey, IdempotencyReceipt


class LineIdempotencyOutcome(StrEnum):
    CREATED = "created"
    EXISTING = "existing"


class LineIdempotencyConflict(ValueError):
    """Raised when an idempotency key is replayed with different content."""


@dataclass(frozen=True, slots=True)
class LineIdempotencyResolution:
    outcome: LineIdempotencyOutcome
    existing_result_reference: str | None = None


def resolve_line_idempotency(
    existing_receipt: IdempotencyReceipt | None,
    requested_key: IdempotencyKey,
    payload_fingerprint: PreviewFingerprint,
) -> LineIdempotencyResolution:
    if existing_receipt is None:
        return LineIdempotencyResolution(LineIdempotencyOutcome.CREATED)
    if existing_receipt.key != requested_key:
        raise ValueError("idempotency receipt does not belong to requested key")
    if existing_receipt.payload_fingerprint != payload_fingerprint:
        raise LineIdempotencyConflict("LINE idempotency payload conflict")
    return LineIdempotencyResolution(
        LineIdempotencyOutcome.EXISTING,
        existing_receipt.result_reference,
    )


__all__ = [
    "LineIdempotencyConflict",
    "LineIdempotencyOutcome",
    "LineIdempotencyResolution",
    "resolve_line_idempotency",
]
