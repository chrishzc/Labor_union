"""Regression for historical baselines that later progress through lifecycle facts."""

from datetime import date

from domains.orders.lifecycle import OrderLifecycleScope, OrderLifecycleStatus
from subsystems.orders.historical_stage_baseline_overlay import (
    HistoricalStageBaselineFacts,
    HistoricalStageBaselineOverlayService,
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


def _stage(ordinal: int, code: str) -> StageProjection:
    return StageProjection(
        ordinal,
        code,
        code,
        "owner",
        "unavailable",
        SourceLineage("owner", None, None),
        None,
        (),
        (),
        (),
        "missing",
        (),
    )


def _step(ordinal: int) -> SopStepProjection:
    return SopStepProjection(
        ordinal,
        f"step-{ordinal}",
        f"step-{ordinal}",
        "owner",
        "unavailable",
        None,
        (),
        (),
        (),
        "missing",
    )


class _Base:
    def query(self, _request):
        timeline = OrderOperationalTimeline(
            "CASE-1",
            9,
            "settlement_payout",
            tuple(_stage(index, code) for index, code in enumerate(_STAGE_CODES, start=1)),
            tuple(_step(index) for index in range(1, 12)),
            "base-digest",
            11,
            None,
        )
        return OrderOperationalTimelinePage(
            (timeline,),
            {code: int(code == "settlement_payout") for code in _STAGE_CODES},
            None,
            "base-etag",
        )


class _Facts:
    def fetch_for_cases(self, _case_nos):
        return (
            HistoricalStageBaselineFacts(
                "CASE-1",
                81,
                OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
                date(2026, 8, 8),
                selected_step=10,
            ),
        )


def test_completed_lifecycle_projection_advances_beyond_older_step_ten_baseline() -> None:
    result = HistoricalStageBaselineOverlayService(_Base(), _Facts()).query(
        StageProjectionQuery(10, lifecycle_scope=OrderLifecycleScope.ALL)
    ).items[0]

    assert result.current_stage_code == "settlement_payout"
    assert result.current_sop_step == 11
    assert result.stages[5].status == "completed"
    assert result.sop_steps[8].status == "completed"
    assert result.sop_steps[9].status == "unavailable"
    assert result.sop_steps[10].status == "unavailable"
