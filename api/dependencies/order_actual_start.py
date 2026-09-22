"""Per-request construction for the Actual Start application workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.clock import SystemBusinessClock
from subsystems.orders.actual_start_workflow import (
    ActualStartApplyRequest,
    ActualStartDateOnlyApplyRequest,
    HistoricalActualStartSourceAssignment,
    ActualStartWorkflow,
    ActualStartWorkflowRepository,
)


class RestartedHistoricalActualStartSource(Protocol):
    def calculate(
        self, case_no: str, actual_start_date: date, *, for_update: bool
    ) -> tuple[date, ...]: ...

    def load_restart_source_assignments(
        self, case_no: str, *, for_update: bool
    ) -> tuple[HistoricalActualStartSourceAssignment, ...]: ...


@dataclass(slots=True)
class ActualStartApplication:
    repository: ActualStartWorkflowRepository
    workflow: ActualStartWorkflow
    restarted_historical_source: RestartedHistoricalActualStartSource | None = None

    def query(self, case_no: str):
        return self.repository.load_actual_start_query(case_no, for_update=False)

    def preview(self, case_no, new_actual_start_date):
        query = self.repository.load_actual_start_query(case_no, for_update=False)
        source = self._restarted_historical_source(query, new_actual_start_date)
        if source is not None:
            service_dates, assignments = source
            return self.workflow.preview_historical_source(
                case_no,
                new_actual_start_date,
                recalculated_service_dates=service_dates,
                source_staff_ids=tuple(item.staff_id for item in assignments),
                source_assignment_ids=tuple(
                    item.source_assignment_id for item in assignments
                ),
            )
        if not query.has_formal_assignments:
            return self.workflow.preview_date_only(query, new_actual_start_date)
        return self.workflow.preview(case_no, new_actual_start_date)

    def apply(self, request: ActualStartApplyRequest | ActualStartDateOnlyApplyRequest):
        if isinstance(request, ActualStartDateOnlyApplyRequest):
            return self.workflow.apply_date_only(request)
        if self._is_restarted_historical_tombstone(request.case_no):
            return self.workflow.apply_historical_source(
                request,
                source_loader=lambda: self._load_restarted_historical_source(
                    request.case_no,
                    request.new_actual_start_date,
                    for_update=True,
                ),
            )
        return self.workflow.apply(request)

    def _restarted_historical_source(self, query, actual_start_date):
        if not (
            self.restarted_historical_source is not None
            and query.historical_precision_restarted
            and not query.has_formal_assignments
        ):
            return None
        return self._load_restarted_historical_source(
            query.case_no,
            actual_start_date,
            for_update=False,
        )

    def _is_restarted_historical_tombstone(self, case_no):
        if self.restarted_historical_source is None:
            return False
        facts = self.repository.load_actual_start_query(case_no, for_update=False)
        return (
            facts.historical_precision_restarted
            and not facts.has_formal_assignments
        )

    def _load_restarted_historical_source(
        self,
        case_no,
        actual_start_date,
        *,
        for_update,
    ):
        planner = self.restarted_historical_source
        if planner is None:
            raise RuntimeError("restarted historical source is unavailable")
        return (
            planner.calculate(case_no, actual_start_date, for_update=for_update),
            planner.load_restart_source_assignments(case_no, for_update=for_update),
        )


def get_actual_start_application():
    from infrastructure.mysql.historical_actual_start_date_planner import (
        MySqlHistoricalActualStartDatePlanner,
    )
    from infrastructure.mysql.order_actual_start_repository import (
        MySqlOrderActualStartRepository,
    )

    connection = get_connection()
    repository = MySqlOrderActualStartRepository(connection)
    workflow = ActualStartWorkflow(
        repository,
        lambda: MySqlUnitOfWork(connection),
        SystemBusinessClock(),
    )
    try:
        yield ActualStartApplication(
            repository,
            workflow,
            MySqlHistoricalActualStartDatePlanner(connection),
        )
    finally:
        connection.close()
