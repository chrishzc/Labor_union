"""Owner-local tests for Historical Orders operational stage baselines."""

from __future__ import annotations

from datetime import date

from domains.orders.lifecycle import OrderLifecycleScope, OrderLifecycleStatus
from subsystems.orders.historical_stage_baseline_overlay import (
    HistoricalStageBaselineFacts,
    HistoricalStageBaselineOverlayService,
    historical_baseline_step,
)
from subsystems.orders.stage_projection_query import (
    OrderOperationalTimeline,
    OrderOperationalTimelinePage,
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


def _timeline(*, settlement_status: str = "blocked") -> OrderOperationalTimeline:
    stages = tuple(
        _stage(index, code, settlement_status if index == 7 else "unavailable")
        for index, code in enumerate(_STAGE_CODES, start=1)
    )
    steps = tuple(
        _step(index, settlement_status if index == 11 else "unavailable")
        for index in range(1, 12)
    )
    return OrderOperationalTimeline("CASE-1", 3, None, stages, steps, "before")


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


def test_discussion_without_actual_start_keeps_normal_projection() -> None:
    facts = HistoricalStageBaselineFacts(
        "CASE-1", 103, OrderLifecycleStatus.DISCUSSION, None
    )
    original = _timeline()

    result = _query(facts, original)

    assert historical_baseline_step(facts) is None
    assert result == original


def test_historical_cancel_has_no_active_operational_stage() -> None:
    facts = HistoricalStageBaselineFacts(
        "CASE-1", 104, OrderLifecycleStatus.CANCELLED, None
    )

    result = _query(facts)

    assert result.current_stage_code is None
    assert all(stage.status == "unavailable" for stage in result.stages)
    assert all(step.status == "unavailable" for step in result.sop_steps)
    assert result.stages[0].availability_reason == "historical_order_cancelled"
