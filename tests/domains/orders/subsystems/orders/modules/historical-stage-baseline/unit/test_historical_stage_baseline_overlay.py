"""Owner-local tests for Historical Orders operational stage baselines."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from unittest.mock import Mock
import pytest

from subsystems.orders.historical_completion_oracle import (
    CompletionOwner, HistoricalOrdersCompletionReadback, HistoricalSettlementReadback,
    HistoricalSettlementSourceVersion, SettlementSourceKind,
)
from subsystems.orders.historical_completion_query import HistoricalCompletionQueryWorkflow

from domains.orders.lifecycle import OrderLifecycleScope, OrderLifecycleStatus
from subsystems.orders.historical_stage_baseline_overlay import (
    HistoricalStageBaselineFacts,
    HistoricalStageBaselineOverlayService,
    historical_baseline_step,
)
from subsystems.orders.stage_projection_query import (
    OrderOperationalTimeline,
    OrderOperationalTimelinePage,
    SettlementProjection,
    SopStepProjection,
    SourceLineage,
    StageProjection,
    StageProjectionQuery,
)


_STAGE_CODES = (
    "intake_terms",
    "matching_willingness",
    "client_review",
    "contract_deposit",
    "date_confirmation",
    "active_service",
    "settlement_payout",
)


@pytest.mark.parametrize("status", [OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED, OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED])
@pytest.mark.parametrize("condition,expected", [
    ("settled", ("completed", "completed", "completed")),
    ("client_open", ("completed", "blocked", "completed")),
    ("staff_open", ("completed", "completed", "blocked")),
    ("staff_unavailable", ("completed", "completed", "unavailable")),
    ("service_missing", ("blocked", "completed", "completed")),
    ("stale_order", ("unavailable", "unavailable", "unavailable")),
])
def test_historical_settlement_uses_fresh_owner_evidence(status, condition, expected):
    orders = HistoricalOrdersCompletionReadback(
        "CASE-1", 4 if condition == "stale_order" else 3, status,
        None if condition == "service_missing" else "lifecycle:3",
        date(2026, 9, 1), None, (), 10, False,
        historical_service_day_count_identity="days:1",
        historical_assignment_day_counts=(("assignment:1", 1, 10),),
    )
    client = HistoricalSettlementReadback(
        "CASE-1", CompletionOwner.CLIENT_FINANCE, 2, "client-payment:1", 1,
        int(condition == "client_open"), "client-link:1",
    )
    staff = HistoricalSettlementReadback(
        "CASE-1", CompletionOwner.STAFF_PAYABLES, None, "staff-payment:1", 1,
        int(condition == "staff_open"), "staff-link:1",
        tuple(sorted(HistoricalSettlementSourceVersion(kind, f"{kind.value}:1", 1) for kind in (
            SettlementSourceKind.PAYROLL_CASE_ACCOUNT, SettlementSourceKind.STAFF_OBLIGATION,
            SettlementSourceKind.STAFF_OBLIGATION_EVENT, SettlementSourceKind.STAFF_PAYABLE_ACCOUNT,
            SettlementSourceKind.HISTORICAL_STAFF_PAYOUT_PROJECTION,
            SettlementSourceKind.HISTORICAL_STAFF_PAYOUT_EVENT, SettlementSourceKind.HISTORICAL_STAFF_PAYOUT_LINK,
        ))),
    )
    ports = [Mock(), Mock(), Mock()]
    for port, readback in zip(ports, (orders, client, None if condition == "staff_unavailable" else staff)):
        port.load_completion_readback.return_value = readback
    original = _timeline(lifecycle_status=status, current_step_ordinal=11, current_stage_code="settlement_payout")
    service = HistoricalStageBaselineOverlayService(
        _Base(original), _Facts(HistoricalStageBaselineFacts("CASE-1", 1, status, date(2026, 9, 1))),
        HistoricalCompletionQueryWorkflow(*ports),
    )
    page = service.query(StageProjectionQuery(10))
    settlement = page.items[0].stages[-1]
    assert tuple(part.status for part in settlement.settlement) == expected
    assert page.items[0].sop_steps[-1].status == settlement.status
    assert page.items[0].projection_digest != original.projection_digest
    for port in ports:
        port.load_completion_readback.assert_called_once_with("CASE-1", for_update=False)

def test_normal_lifecycle_does_not_consume_historical_settlement():
    completion = Mock()
    original = _timeline(lifecycle_status=OrderLifecycleStatus.COMPLETED)
    repository = Mock()
    repository.fetch_for_cases.return_value = ()
    page = HistoricalStageBaselineOverlayService(_Base(original), repository, completion).query(StageProjectionQuery(10))
    assert page.items == (original,)
    completion.query.assert_not_called()


class _Base:
    def __init__(self, timeline):
        self.timeline = timeline

    def query(self, _request):
        return OrderOperationalTimelinePage(
            (self.timeline,),
            {code: int(code == self.timeline.current_stage_code) for code in _STAGE_CODES},
            None,
            "base-etag",
        )


class _Facts:
    def __init__(self, facts):
        self.facts = facts

    def fetch_for_cases(self, _case_nos):
        return (self.facts,)


def _stage(ordinal: int, code: str, status: str = "unavailable") -> StageProjection:
    return StageProjection(
        ordinal,
        code,
        code,
        "owner",
        status,
        SourceLineage("owner", None, None),
        None,
        (),
        (),
        (),
        "missing" if status == "unavailable" else None,
        (),
    )


def _step(ordinal: int, status: str = "unavailable") -> SopStepProjection:
    return SopStepProjection(
        ordinal,
        f"step-{ordinal}",
        f"step-{ordinal}",
        "owner",
        status,
        None,
        (),
        (),
        (),
        "missing" if status == "unavailable" else None,
    )


def _timeline(
    *,
    settlement_status: str = "blocked",
    lifecycle_status: OrderLifecycleStatus = OrderLifecycleStatus.DISCUSSION,
    replacement_resume_step_ordinal: int | None = None,
    current_stage_code: str | None = None,
    current_step_ordinal: int | None = None,
) -> OrderOperationalTimeline:
    stages = tuple(
        _stage(index, code, settlement_status if index == 7 else "unavailable")
        for index, code in enumerate(_STAGE_CODES, start=1)
    )
    steps = tuple(
        _step(index, settlement_status if index == 11 else "unavailable")
        for index in range(1, 12)
    )
    return OrderOperationalTimeline(
        "CASE-1",
        3,
        lifecycle_status,
        replacement_resume_step_ordinal,
        current_stage_code,
        current_step_ordinal,
        stages,
        steps,
        "before",
    )


def _timeline_with_statuses(
    *,
    step_statuses: dict[int, str],
    stage_statuses: dict[int, str] | None = None,
    lifecycle_status: OrderLifecycleStatus = OrderLifecycleStatus.DISCUSSION,
    replacement_resume_step_ordinal: int | None = None,
    current_stage_code: str | None = None,
    current_step_ordinal: int | None = None,
) -> OrderOperationalTimeline:
    original = _timeline(
        lifecycle_status=lifecycle_status,
        replacement_resume_step_ordinal=replacement_resume_step_ordinal,
        current_stage_code=current_stage_code,
        current_step_ordinal=current_step_ordinal,
    )
    steps = tuple(
        replace(
            item,
            status=step_statuses.get(item.ordinal, item.status),
            availability_reason=(
                "missing"
                if step_statuses.get(item.ordinal, item.status) == "unavailable"
                else None
            ),
        )
        for item in original.sop_steps
    )
    stages = tuple(
        replace(
            item,
            status=(stage_statuses or {}).get(item.ordinal, item.status),
            availability_reason=(
                "missing"
                if (stage_statuses or {}).get(item.ordinal, item.status) == "unavailable"
                else None
            ),
        )
        for item in original.stages
    )
    return replace(original, sop_steps=steps, stages=stages)


def _query(facts, timeline=None):
    service = HistoricalStageBaselineOverlayService(
        _Base(timeline or _timeline()),
        _Facts(facts),
    )
    return service.query(StageProjectionQuery(10, lifecycle_scope=OrderLifecycleScope.ALL)).items[0]


def test_completed_historical_order_enters_step_11_without_completing_settlement() -> None:
    facts = HistoricalStageBaselineFacts(
        "CASE-1", 101, OrderLifecycleStatus.COMPLETED, date(2025, 1, 2)
    )

    result = _query(facts)

    assert historical_baseline_step(facts) == 11
    assert result.current_stage_code == "settlement_payout"
    assert all(stage.status == "completed" for stage in result.stages[:6])
    assert result.stages[6].status == "blocked"
    assert all(step.status == "completed" for step in result.sop_steps[:10])
    assert result.sop_steps[10].status == "blocked"
    assert result.sop_steps[0].warnings[0].code == "historical_baseline_completed"


def test_deposit_paid_historical_order_enters_date_confirmation() -> None:
    facts = HistoricalStageBaselineFacts(
        "CASE-1", 105, OrderLifecycleStatus.ESTABLISHED, None
    )

    result = _query(facts)

    assert historical_baseline_step(facts) == 9
    assert result.current_stage_code == "date_confirmation"
    assert all(stage.status == "completed" for stage in result.stages[:4])
    assert result.stages[4].status == "unavailable"
    assert all(step.status == "completed" for step in result.sop_steps[:8])
    assert result.sop_steps[8].status == "unavailable"


def test_deposit_paid_with_actual_start_enters_formal_service() -> None:
    facts = HistoricalStageBaselineFacts(
        "CASE-1", 106, OrderLifecycleStatus.ESTABLISHED, date(2025, 2, 3)
    )

    result = _query(facts)

    assert historical_baseline_step(facts) == 10
    assert result.current_stage_code == "active_service"
    assert all(stage.status == "completed" for stage in result.stages[:5])
    assert result.stages[5].status == "unavailable"
    assert all(step.status == "completed" for step in result.sop_steps[:9])
    assert result.sop_steps[9].status == "unavailable"


def test_in_service_status_keeps_historical_predecessors_completed() -> None:
    facts = HistoricalStageBaselineFacts(
        "CASE-1", 107, OrderLifecycleStatus.IN_SERVICE, date(2025, 2, 3)
    )

    result = _query(facts)

    assert historical_baseline_step(facts) == 10
    assert result.current_stage_code == "active_service"
    assert all(stage.status == "completed" for stage in result.stages[:5])


def test_discussion_with_actual_start_enters_formal_service() -> None:
    facts = HistoricalStageBaselineFacts(
        "CASE-1", 102, OrderLifecycleStatus.DISCUSSION, date(2025, 2, 3)
    )

    result = _query(facts)

    assert historical_baseline_step(facts) == 10
    assert result.current_stage_code == "active_service"
    assert all(stage.status == "completed" for stage in result.stages[:5])
    assert result.stages[5].status == "unavailable"
    assert all(step.status == "completed" for step in result.sop_steps[:9])
    assert result.sop_steps[9].status == "unavailable"


def test_formal_baseline_step_is_immutable_while_owner_roots_progress_forward() -> None:
    facts = HistoricalStageBaselineFacts(
        "CASE-1",
        108,
        OrderLifecycleStatus.COMPLETED,
        date(2025, 2, 3),
        selected_step=9,
        baseline_event_identity="historical-operational-baseline-event:abc",
        baseline_event_version=41,
    )
    timeline = _timeline_with_statuses(
        step_statuses={9: "completed", 10: "in_progress", 11: "unavailable"},
        stage_statuses={5: "completed", 6: "in_progress", 7: "unavailable"},
        lifecycle_status=OrderLifecycleStatus.IN_SERVICE,
        current_stage_code="active_service",
        current_step_ordinal=10,
    )

    result = _query(facts, timeline)

    assert historical_baseline_step(facts) == 9
    assert result.current_stage_code == "active_service"
    assert all(step.status == "completed" for step in result.sop_steps[:9])
    assert result.sop_steps[9].status == "in_progress"
    assert result.sop_steps[0].owner == "Historical Orders"
    assert result.stages[0].source.identity == "historical-operational-baseline-event:abc"
    assert result.stages[0].source.version == 41


def test_predecessor_status_without_typed_reentry_does_not_regress_baseline() -> None:
    facts = HistoricalStageBaselineFacts(
        "CASE-1",
        109,
        OrderLifecycleStatus.IN_SERVICE,
        date(2025, 2, 3),
        selected_step=10,
        baseline_event_identity="historical-operational-baseline-event:def",
        baseline_event_version=42,
    )
    timeline = _timeline_with_statuses(
        step_statuses={9: "blocked", 10: "in_progress", 11: "unavailable"},
        stage_statuses={5: "blocked", 6: "in_progress", 7: "unavailable"},
        lifecycle_status=OrderLifecycleStatus.IN_SERVICE,
        current_stage_code="active_service",
        current_step_ordinal=10,
    )

    result = _query(facts, timeline)

    assert historical_baseline_step(facts) == 10
    assert result.current_stage_code == "active_service"
    assert result.current_step_ordinal == 10
    assert result.sop_steps[8].status == "completed"
    assert result.sop_steps[9].status == "in_progress"


def test_service_before_replacement_resume_step_is_typed_reentry_evidence() -> None:
    facts = HistoricalStageBaselineFacts(
        "CASE-1",
        112,
        OrderLifecycleStatus.IN_SERVICE,
        date(2025, 2, 3),
        selected_step=10,
        baseline_event_identity="historical-operational-baseline-event:replacement",
        baseline_event_version=44,
    )
    timeline = _timeline_with_statuses(
        step_statuses={2: "completed", 3: "in_progress", 10: "unavailable"},
        stage_statuses={2: "in_progress", 6: "unavailable"},
        lifecycle_status=OrderLifecycleStatus.ESTABLISHED,
        replacement_resume_step_ordinal=3,
        current_stage_code="matching_willingness",
        current_step_ordinal=3,
    )

    result = _query(facts, timeline)

    assert result.current_stage_code == "matching_willingness"
    assert result.current_step_ordinal == 3
    assert result.sop_steps[0].status == "completed"
    assert result.sop_steps[2].status == "in_progress"


def test_unavailable_predecessor_does_not_fake_h06_invalidation() -> None:
    facts = HistoricalStageBaselineFacts(
        "CASE-1",
        110,
        OrderLifecycleStatus.IN_SERVICE,
        date(2025, 2, 3),
        selected_step=10,
        baseline_event_identity="historical-operational-baseline-event:ghi",
        baseline_event_version=43,
    )
    timeline = _timeline_with_statuses(
        step_statuses={9: "unavailable", 10: "in_progress", 11: "unavailable"},
        stage_statuses={5: "unavailable", 6: "in_progress", 7: "unavailable"},
        lifecycle_status=OrderLifecycleStatus.IN_SERVICE,
        current_stage_code="active_service",
        current_step_ordinal=10,
    )

    result = _query(facts, timeline)

    assert historical_baseline_step(facts) == 10
    assert result.current_stage_code == "active_service"
    assert result.sop_steps[8].status == "completed"
    assert result.sop_steps[9].status == "in_progress"


def test_discussion_without_actual_start_keeps_normal_projection() -> None:
    facts = HistoricalStageBaselineFacts(
        "CASE-1", 103, OrderLifecycleStatus.DISCUSSION, None
    )
    original = _timeline()

    result = _query(facts, original)

    assert historical_baseline_step(facts) is None
    assert result == original


def test_current_cancellation_is_not_resurrected_by_old_historical_baseline() -> None:
    facts = HistoricalStageBaselineFacts(
        "CASE-1",
        111,
        OrderLifecycleStatus.ESTABLISHED,
        None,
        selected_step=9,
    )
    original = _timeline(lifecycle_status=OrderLifecycleStatus.CANCELLED)

    result = _query(facts, original)

    assert result == original
    assert result.current_stage_code is None
    assert result.current_step_ordinal is None


def test_historical_cancel_has_no_active_operational_stage() -> None:
    facts = HistoricalStageBaselineFacts(
        "CASE-1", 104, OrderLifecycleStatus.CANCELLED, None
    )

    result = _query(facts)

    assert result.current_stage_code is None
    assert all(stage.status == "unavailable" for stage in result.stages)
    assert all(step.status == "unavailable" for step in result.sop_steps)
    assert result.stages[0].availability_reason == "historical_order_cancelled"


def test_historical_cancel_preserves_settlement_owner_projection() -> None:
    facts = HistoricalStageBaselineFacts(
        "CASE-1", 104, OrderLifecycleStatus.CANCELLED, None
    )
    settlement = (
        SettlementProjection(
            "service_completion",
            "completed",
            SourceLineage("Orders", "completion:1", 1),
            None,
            None,
        ),
        SettlementProjection(
            "client_settlement",
            "blocked",
            SourceLineage("Client Finance", "client-settlement:1", 2),
            None,
            None,
        ),
        SettlementProjection(
            "staff_payout",
            "unavailable",
            SourceLineage("Staff Payables", None, None),
            None,
            "obligation_projection_missing",
        ),
    )
    original = _timeline(lifecycle_status=OrderLifecycleStatus.CANCELLED)
    original = replace(
        original,
        stages=original.stages[:-1]
        + (replace(original.stages[-1], settlement=settlement),),
    )

    result = _query(facts, original)

    assert result.stages[-1].status == "unavailable"
    assert result.stages[-1].settlement == settlement
