"""Typed bounded-scan and failed-projector retry contracts."""

from __future__ import annotations

from dataclasses import dataclass

from domains.anomalies.root_fact_projection import FinanceManualReviewRootFact
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_MAXIMUM_SCAN_SIZE = 100


@dataclass(frozen=True, slots=True)
class ScanAnomalyDefinitionRequest:
    definition_code: str
    maximum_items: int = 50
    after_source_id: int = 0

    def __post_init__(self) -> None:
        require_canonical_text(
            self.definition_code,
            "anomaly definition code",
            191,
        )
        _require_bounded_size(self.maximum_items)
        require_nonnegative_integer(
            self.after_source_id,
            "scan source cursor",
        )


@dataclass(frozen=True, slots=True)
class AnomalyDefinitionScanPage:
    root_facts: tuple[FinanceManualReviewRootFact, ...]
    next_after_source_id: int | None


@dataclass(frozen=True, slots=True)
class ScanAnomalyDefinitionResult:
    definition_code: str
    scanned_count: int
    active_count: int
    inactive_count: int
    next_after_source_id: int | None

    @property
    def completed(self) -> bool:
        return self.next_after_source_id is None


@dataclass(frozen=True, slots=True)
class RetryAnomalyProjectorRequest:
    maximum_events: int = 50

    def __post_init__(self) -> None:
        _require_bounded_size(self.maximum_events)


@dataclass(frozen=True, slots=True)
class RetryAnomalyProjectorResult:
    projector_identity: str
    requeued_event_ids: tuple[int, ...]

    @property
    def requeued_count(self) -> int:
        return len(self.requeued_event_ids)


def _require_bounded_size(value: int) -> None:
    require_positive_integer(value, "bounded operation size")
    if value > _MAXIMUM_SCAN_SIZE:
        raise ValueError("bounded operation size exceeds maximum")


__all__ = [
    "AnomalyDefinitionScanPage",
    "RetryAnomalyProjectorRequest",
    "RetryAnomalyProjectorResult",
    "ScanAnomalyDefinitionRequest",
    "ScanAnomalyDefinitionResult",
]
