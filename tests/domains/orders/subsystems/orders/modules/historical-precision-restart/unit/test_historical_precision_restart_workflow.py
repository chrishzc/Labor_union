from dataclasses import replace
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from domains.orders.historical_precision_restart import (
    HistoricalPrecisionRestartAssignmentFacts,
    HistoricalPrecisionRestartFacts,
    HistoricalPrecisionRestartIntent,
)
from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.orders.historical_precision_restart_workflow import (
    ApplyHistoricalPrecisionRestart,
    HistoricalPrecisionRestartContext,
    HistoricalPrecisionRestartError,
    HistoricalPrecisionRestartWorkflow,
)
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey


class _Repository:
    def __init__(self, revision=0):
        self.context = HistoricalPrecisionRestartContext(
            HistoricalPrecisionRestartFacts(
                "CASE-1", OrderLifecycleStatus.HISTORICAL_UNSERVED,
                1, 2, 0, 3, 4, revision,
                date(2026, 5, 19), None, 1, 8, False,
                (HistoricalPrecisionRestartAssignmentFacts("assignment:9", 9, 3, "王月嫂", 1),),
                current_assignment_ids=(9,),
            ),
            SimpleNamespace(),
        )

    def load(self, case_no, *, for_update):
        return self.context

    def find_receipt(self, key):
        return None

    def claim(self, request, command_fingerprint):
        return None

    def preflight_staff_ids(self, case_no):
        return ()

    def persist(self, request, preview):
        pytest.fail("stale confirmed-service-date root must block before persist")


class _Unit:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def commit(self):
        pytest.fail("stale command must not commit")


def _workflow(repository):
    return HistoricalPrecisionRestartWorkflow(
        repository,
        lambda: pytest.fail("query/preview must not open a unit of work"),
        lambda: datetime(2026, 9, 1, tzinfo=ZoneInfo("Asia/Taipei")),
    )


def test_query_reports_restart_to_normal_flow_without_dates_or_money_impacts():
    result = _workflow(_Repository()).query("CASE-1")

    assert result.domain.blockers == ()
    assert result.domain.target_status is OrderLifecycleStatus.ESTABLISHED
    assert result.domain.actual_end_date is None
    assert result.domain.scheduling.assignments == ()
    assert result.client_finance_impact is None
    assert result.payroll_impact is None
    assert result.lifecycle_impact.actual_end_date is None


def test_preview_fails_closed_when_historical_accounting_already_exists():
    with pytest.raises(HistoricalPrecisionRestartError) as caught:
        _workflow(_Repository(revision=1)).preview(
            HistoricalPrecisionRestartIntent("CASE-1")
        )

    assert caught.value.error.code == "historical_precision_restart_accounting_bridge_required"
    assert caught.value.error.domain_blockers == (
        "historical_precision_restart_accounting_bridge_required",
    )


def test_apply_fails_stale_when_confirmed_service_date_root_changed_after_preview():
    repository = _Repository()
    repository.context = replace(
        repository.context,
        facts=replace(
            repository.context.facts,
            confirmed_service_date_version=1,
            confirmed_service_date_fingerprint="a" * 64,
        ),
    )
    workflow = HistoricalPrecisionRestartWorkflow(
        repository,
        _Unit,
        lambda: datetime(2026, 9, 1, tzinfo=ZoneInfo("Asia/Taipei")),
    )
    preview = workflow.preview(HistoricalPrecisionRestartIntent("CASE-1"))
    repository.context = replace(
        repository.context,
        facts=replace(
            repository.context.facts,
            confirmed_service_date_version=2,
            confirmed_service_date_fingerprint="b" * 64,
        ),
    )
    request = ApplyHistoricalPrecisionRestart(
        HistoricalPrecisionRestartIntent("CASE-1"),
        1, 2, 0, 1,
        preview.fingerprint,
        IdempotencyKey("restart-confirmed-date-race"),
        ActorContext("operator"),
        "重啟正常流程",
        CorrelationId("restart-confirmed-date-race"),
    )

    with pytest.raises(HistoricalPrecisionRestartError) as caught:
        workflow.apply(request)

    assert caught.value.error.code == "historical_precision_restart_candidate_stale"
