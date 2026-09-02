"""Owner-local tests for Historical Orders operational stage baselines."""

from __future__ import annotations

from dataclasses import replace
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
