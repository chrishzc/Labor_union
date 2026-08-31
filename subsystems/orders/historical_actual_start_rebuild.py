"""Rebuild official service facts after a supported historical actual-start assertion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from typing import Protocol

from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.orders.actual_start_workflow import (
    ActualStartApplyRequest,
    ActualStartWorkflow,
)


class HistoricalServiceDatePlanner(Protocol):
    def calculate(
        self, case_no: str, actual_start_date: date, *, for_update: bool
    ) -> tuple[date, ...]: ...


@dataclass(frozen=True, slots=True)
class HistoricalActualStartRebuilder:
    """Delegate one adopted historical start assertion to the canonical writer."""

    actual_start_workflow: ActualStartWorkflow
    service_date_planner: HistoricalServiceDatePlanner

    def apply_in_current_unit_of_work(
        self,
        *,
        case_no: str,
        actual_start_date: date,
        source_identity: str,
        actor: str,
        correlation_id: str,
    ) -> None:
        service_dates = self.service_date_planner.calculate(
            case_no,
            actual_start_date,
            for_update=True,
        )
        preview = self.actual_start_workflow.preview(
            case_no,
            actual_start_date,
            recalculated_service_dates=service_dates,
        )
        request = ActualStartApplyRequest(
            case_no=case_no,
            new_actual_start_date=actual_start_date,
            expected_order_version=ExpectedVersion(preview.order_version),
            expected_scheduling_version=ExpectedVersion(preview.scheduling_version),
            expected_client_finance_version=ExpectedVersion(
                preview.client_finance_version
            ),
            expected_payroll_version=ExpectedVersion(preview.payroll_version),
            preview_fingerprint=preview.fingerprint,
            idempotency_key=IdempotencyKey(_idempotency_key(source_identity)),
            actor=ActorContext(actor),
            reason="historical actual-start service-date rebuild",
            correlation_id=CorrelationId(correlation_id),
        )
        self.actual_start_workflow.apply_in_current_unit_of_work(
            request,
            recalculated_service_dates=service_dates,
        )


def _idempotency_key(source_identity: str) -> str:
    digest = sha256(source_identity.encode("utf-8")).hexdigest()
    return f"historical-actual-start:{digest}"


__all__ = [
    "HistoricalActualStartRebuilder",
    "HistoricalServiceDatePlanner",
]
