"""Consume committed M3 Customer Service handoffs through the ticket owner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from domains.customer_service.ticket import CustomerServiceCategory
from subsystems.customer_service.contracts import CreateCustomerServiceMessage


@dataclass(frozen=True, slots=True)
class MatchingCoordinationCustomerServiceFailure:
    reference_id: str
    case_no: str
    code: str


class MatchingCoordinationCustomerServiceWorker:
    """Create one typed ticket event per immutable M3 rejection handoff."""

    def __init__(
        self,
        unit_of_work_factory: Callable,
        worker_identity: str,
        *,
        batch_size: int = 25,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._worker_identity = worker_identity
        self._batch_size = batch_size
        self._failures: tuple[MatchingCoordinationCustomerServiceFailure, ...] = ()

    @property
    def failures(self) -> tuple[MatchingCoordinationCustomerServiceFailure, ...]:
        return self._failures

    def run_once(self) -> int:
        failures: list[MatchingCoordinationCustomerServiceFailure] = []
        with self._unit_of_work_factory() as unit_of_work:
            source = getattr(unit_of_work, "matching_coordination_customer_service", None)
            if source is None:
                return 0
            items = source.list_customer_service_intents(limit=self._batch_size)
        for item in items:
            try:
                with self._unit_of_work_factory() as unit_of_work:
                    unit_of_work.customer_service.create_or_append(
                        CreateCustomerServiceMessage(
                            line_user_id=item.line_user_id,
                            category=CustomerServiceCategory(item.category),
                            message=item.message,
                            event_key=item.reference_id,
                        )
                    )
                    unit_of_work.commit()
            except Exception as error:
                failures.append(
                    MatchingCoordinationCustomerServiceFailure(
                        item.reference_id,
                        item.case_no,
                        type(error).__name__,
                    )
                )
        self._failures = tuple(failures)
        return len(items)


__all__ = [
    "MatchingCoordinationCustomerServiceFailure",
    "MatchingCoordinationCustomerServiceWorker",
]
