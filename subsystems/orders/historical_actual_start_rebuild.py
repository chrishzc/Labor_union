"""Rebuild official service facts after a supported historical actual-start assertion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from typing import Protocol

from domains.orders.actual_start import ActualStartCandidateError
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.orders.actual_start_workflow import (
    ActualStartApplyRequest,
    ActualStartWorkflow,
    ActualStartWorkflowError,
)


class HistoricalServiceDatePlanner(Protocol):
    def calculate(
        self, case_no: str, actual_start_date: date, *, for_update: bool
    ) -> tuple[date, ...]: ...


class HistoricalActualStartPreparationError(ValueError):
    """A historical source cannot yet support canonical Actual Start rebuilding."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class HistoricalActualStartRebuilder:
    """Delegate one adopted historical start assertion to the canonical writer."""

    actual_start_workflow: ActualStartWorkflow
    service_date_planner: HistoricalServiceDatePlanner

    def preview(
        self,
        *,
        case_no: str,
        actual_start_date: date,
        correlation_id: str,
        source_staff_ids: tuple[int, ...] = (),
    ) -> None:
        """Validate the same no-write prerequisites required by Apply."""
        try:
            service_dates = self.service_date_planner.calculate(
                case_no,
                actual_start_date,
                for_update=False,
            )
            preview_source_generation = getattr(
                self.service_date_planner,
                "preview_source_generation",
                None,
            )
            if preview_source_generation is not None:
                if source_staff_ids:
                    preview_source_generation(
                        case_no,
                        service_dates,
                        source_staff_ids=source_staff_ids,
                    )
                else:
                    preview_source_generation(case_no, service_dates)
            historical_preview = getattr(
                self.actual_start_workflow,
                "preview_historical_source",
                None,
            )
            if callable(historical_preview):
                historical_preview(
                    case_no,
                    actual_start_date,
                    recalculated_service_dates=service_dates,
                    source_staff_ids=source_staff_ids,
                )
                return
            self.actual_start_workflow.preview(
                case_no,
                actual_start_date,
                recalculated_service_dates=service_dates,
            )
        except HistoricalActualStartPreparationError as error:
            raise _preparation_blocked(error.code, correlation_id) from error
        except ActualStartCandidateError as error:
            raise _preparation_blocked(error.blocker.value, correlation_id) from error

    def apply_in_current_unit_of_work(
        self,
        *,
        case_no: str,
        actual_start_date: date,
        source_identity: str,
        actor: str,
        correlation_id: str,
        source_staff_ids: tuple[int, ...] = (),
    ) -> None:
        try:
            self._apply_in_current_unit_of_work(
                case_no=case_no,
                actual_start_date=actual_start_date,
                source_identity=source_identity,
                actor=actor,
                correlation_id=correlation_id,
                source_staff_ids=source_staff_ids,
            )
        except HistoricalActualStartPreparationError as error:
            raise _preparation_blocked(error.code, correlation_id) from error
        except ActualStartCandidateError as error:
            raise _preparation_blocked(error.blocker.value, correlation_id) from error

    def _apply_in_current_unit_of_work(
        self,
        *,
        case_no: str,
        actual_start_date: date,
        source_identity: str,
        actor: str,
        correlation_id: str,
        source_staff_ids: tuple[int, ...],
    ) -> None:
        service_dates = self.service_date_planner.calculate(
            case_no,
            actual_start_date,
            for_update=True,
        )
        idempotency_key = IdempotencyKey(_idempotency_key(source_identity))
        if (
            self.actual_start_workflow.replay_from_immutable_source(
                idempotency_key
            )
            is not None
        ):
            return
        prepare_source_generation = getattr(
            self.service_date_planner,
            "prepare_source_generation",
            None,
        )
        if prepare_source_generation is not None:
            prepare_source_generation(
                case_no,
                service_dates,
                source_identity=source_identity,
                actor=actor,
                correlation_id=correlation_id,
            )
        historical_preview = getattr(
            self.actual_start_workflow,
            "preview_historical_source",
            None,
        )
        historical_apply = getattr(
            self.actual_start_workflow,
            "apply_historical_source_in_current_unit_of_work",
            None,
        )
        if callable(historical_preview) and callable(historical_apply):
            preview = historical_preview(
                case_no,
                actual_start_date,
                recalculated_service_dates=service_dates,
                source_staff_ids=source_staff_ids,
            )
            request = ActualStartApplyRequest(
                case_no=case_no,
                new_actual_start_date=actual_start_date,
                expected_order_version=ExpectedVersion(preview.order_version),
                expected_scheduling_version=ExpectedVersion(
                    preview.scheduling_version
                ),
                expected_client_finance_version=ExpectedVersion(
                    preview.client_finance_version
                ),
                expected_payroll_version=ExpectedVersion(preview.payroll_version),
                preview_fingerprint=preview.fingerprint,
                idempotency_key=idempotency_key,
                actor=ActorContext(actor),
                reason="historical actual-start service-date rebuild",
                correlation_id=CorrelationId(correlation_id),
            )
            historical_apply(
                request,
                recalculated_service_dates=service_dates,
                source_staff_ids=source_staff_ids,
            )
            return
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
            idempotency_key=idempotency_key,
            actor=ActorContext(actor),
            reason="historical actual-start service-date rebuild",
            correlation_id=CorrelationId(correlation_id),
        )
        self.actual_start_workflow.apply_in_current_unit_of_work(
            request,
            recalculated_service_dates=service_dates,
        )


def _preparation_blocked(code: str, correlation_id: str) -> ActualStartWorkflowError:
    message = (
        "歷史服務日期與月嫂既有正式排班衝突，請先完成受控調度後再匯入。"
        if code == "historical_actual_start_staff_schedule_conflict"
        else "歷史訂單缺少重建實際開工所需的目前資料。"
    )
    return ActualStartWorkflowError(
        TypedError(
            ErrorCategory.DOMAIN_BLOCKED,
            code,
            message,
            CorrelationId(correlation_id),
            domain_blockers=(code,),
        )
    )


def _idempotency_key(source_identity: str) -> str:
    digest = sha256(source_identity.encode("utf-8")).hexdigest()
    return f"historical-actual-start:{digest}"


__all__ = [
    "HistoricalActualStartPreparationError",
    "HistoricalActualStartRebuilder",
    "HistoricalServiceDatePlanner",
]
