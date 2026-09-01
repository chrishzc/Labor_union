"""Consume committed M3 intents into the existing LINE delivery task owner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from subsystems.line.matching_coordination_delivery import (
    MatchingCoordinationDeliveryApplication,
    MatchingCoordinationDeliveryError,
    MatchingCoordinationOutboxItem,
)
from shared_kernel.validation import require_canonical_text


@dataclass(frozen=True, slots=True)
class MatchingCoordinationDeliveryFailure:
    """Typed, queryable in-process fallback for one bad immutable source row."""

    reference_id: str
    case_no: str
    code: str
    fallback: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.reference_id, "matching delivery failure reference ID"),
            (self.case_no, "matching delivery failure case number"),
            (self.code, "matching delivery failure code"),
            (self.fallback, "matching delivery failure fallback"),
        ):
            require_canonical_text(value, label, 191)


class MatchingCoordinationDeliveryWorker:
    def __init__(
        self,
        unit_of_work_factory: Callable,
        worker_identity: str,
        now: Callable[[], datetime],
        *,
        batch_size: int = 25,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._worker_identity = worker_identity
        self._now = now
        self._batch_size = batch_size
        self._failures: tuple[MatchingCoordinationDeliveryFailure, ...] = ()

    @property
    def failures(self) -> tuple[MatchingCoordinationDeliveryFailure, ...]:
        return self._failures

    def run_once(self) -> int:
        failures: list[MatchingCoordinationDeliveryFailure] = []
        with self._unit_of_work_factory() as unit_of_work:
            source = getattr(unit_of_work, "matching_coordination_delivery", None)
            if source is None:
                return 0
            items = source.list_line_intents(limit=self._batch_size)
        application = MatchingCoordinationDeliveryApplication(
            self._unit_of_work_factory, self._now
        )
        for item in items:
            fallback = item.intent_payload.get("legacy_delivery_fallback")
            if isinstance(fallback, dict):
                failures.append(
                    MatchingCoordinationDeliveryFailure(
                        item.reference_id,
                        item.case_no,
                        str(fallback.get("code", "line_matching_legacy_delivery_fallback")),
                        str(fallback.get("fallback", "manual_review")),
                    )
                )
            try:
                application.consume(item)
            except MatchingCoordinationDeliveryError as error:
                failures.append(
                    MatchingCoordinationDeliveryFailure(
                        item.reference_id,
                        item.case_no,
                        error.code,
                        "manual_review",
                    )
                )
                continue
        self._failures = tuple(failures)
        return len(items)


__all__ = ["MatchingCoordinationDeliveryFailure", "MatchingCoordinationDeliveryWorker"]
