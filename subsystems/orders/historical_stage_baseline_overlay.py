"""Overlay immutable historical-order terminal assertions onto the operational timeline.

This is intentionally query-only.  It never fabricates Matching, Contract,
Finance, or Scheduling owner roots; it only marks missing predecessor stages as
historically bypassed when an adopted historical order already proves a later
operational position.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
import hashlib
import json
from typing import Mapping, Protocol

from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.orders.stage_projection_query import (
    OrderOperationalTimeline,
    OrderOperationalTimelinePage,
    ProjectionNotice,
    SopStepProjection,
    SourceLineage,
    StageProjection,
    StageProjectionQuery,
)


@dataclass(frozen=True, slots=True)
class HistoricalStageBaselineFacts:
    case_no: str
    adoption_receipt_id: int
    lifecycle_status: OrderLifecycleStatus
    actual_start_date: date | None


class HistoricalStageBaselineRepository(Protocol):
    def fetch_for_cases(
        self, case_nos: tuple[str, ...]
    ) -> tuple[HistoricalStageBaselineFacts, ...]: ...


class OperationalTimelineQueryPort(Protocol):
    def query(self, request: StageProjectionQuery) -> OrderOperationalTimelinePage: ...


class HistoricalStageBaselineOverlayService:
    """Keep the normal timeline intact and fill only historical predecessor gaps."""

    def __init__(
        self,
        base: OperationalTimelineQueryPort,
        repository: HistoricalStageBaselineRepository,
    ) -> None:
        self._base = base
        self._repository = repository

    def query(self, request: StageProjectionQuery) -> OrderOperationalTimelinePage:
        page = self._base.query(request)
        facts = {
            item.case_no: item
            for item in self._repository.fetch_for_cases(
                tuple(item.case_no for item in page.items)
            )
        }
        items = tuple(_overlay(item, facts.get(item.case_no)) for item in page.items)
        counts = {code: 0 for code in page.stage_counts}
        for item in items:
            if item.current_stage_code is not None:
                counts[item.current_stage_code] += 1
        etag = _digest(
            {
                "items": tuple(
                    (item.case_no, item.base_revision, item.current_stage_code, item.projection_digest)
                    for item in items
                ),
                "next_cursor": page.next_cursor,
            }
        )
        return OrderOperationalTimelinePage(items, counts, page.next_cursor, etag)


def historical_baseline_step(facts: HistoricalStageBaselineFacts) -> int | None:
    """Map only unambiguous historical states to a current operational step."""

    if facts.lifecycle_status is OrderLifecycleStatus.COMPLETED:
        return 11
    if (
        facts.actual_start_date is not None
        and facts.lifecycle_status
        in {
            OrderLifecycleStatus.DISCUSSION,
            OrderLifecycleStatus.ESTABLISHED,
            OrderLifecycleStatus.IN_SERVICE,
        }
    ):
        return 10
    if facts.lifecycle_status is OrderLifecycleStatus.ESTABLISHED:
        return 9
    return None


def _overlay(
    timeline: OrderOperationalTimeline,
    facts: HistoricalStageBaselineFacts | None,
) -> OrderOperationalTimeline:
    if facts is None:
        return timeline
    if facts.lifecycle_status is OrderLifecycleStatus.CANCELLED:
        return _cancelled_timeline(timeline, facts)
    selected_step = historical_baseline_step(facts)
    if selected_step is None:
        return timeline

    selected_stage = {9: 5, 10: 6, 11: 7}[selected_step]
    stages = tuple(
        _baseline_stage(stage, facts)
        if stage.ordinal < selected_stage and stage.status != "completed"
        else stage
        for stage in timeline.stages
    )
    steps = tuple(
        _baseline_step(step, facts)
        if step.ordinal < selected_step and step.status != "completed"
        else step
        for step in timeline.sop_steps
    )
    current_stage_code = {
        9: "date_confirmation",
        10: "settlement_payout" if stages[5].status == "completed" else "active_service",
        11: "settlement_payout",
    }[selected_step]
    return _with_projection_digest(
        timeline,
        current_stage_code=current_stage_code,
        stages=stages,
        steps=steps,
    )


def _baseline_source(facts: HistoricalStageBaselineFacts) -> SourceLineage:
    return SourceLineage(
        "Historical Orders",
        f"historical-order-adoption-receipt:{facts.adoption_receipt_id}",
        facts.adoption_receipt_id,
    )


def _baseline_notice() -> ProjectionNotice:
    return ProjectionNotice(
        "historical_baseline_completed",
        "歷史訂單已略過此前置作業；未補造原流程 owner 事件。",
    )


def _baseline_stage(
    stage: StageProjection, facts: HistoricalStageBaselineFacts
) -> StageProjection:
    return replace(
        stage,
        owner="Historical Orders",
        status="completed",
        source=_baseline_source(facts),
        blockers=(),
        warnings=(_baseline_notice(),),
        availability_reason=None,
    )


def _baseline_step(
    step: SopStepProjection, facts: HistoricalStageBaselineFacts
) -> SopStepProjection:
    return replace(
        step,
        owner="Historical Orders",
        status="completed",
        blockers=(),
        warnings=(_baseline_notice(),),
        availability_reason=None,
    )


def _cancelled_timeline(
    timeline: OrderOperationalTimeline,
    facts: HistoricalStageBaselineFacts,
) -> OrderOperationalTimeline:
    notice = ProjectionNotice(
        "historical_order_cancelled",
        "歷史訂單已取消；前置作業不要求補齊。",
    )
    stages = tuple(
        replace(
            stage,
            owner="Historical Orders",
            status="unavailable",
            source=_baseline_source(facts),
            blockers=(),
            warnings=(notice,),
            availability_reason="historical_order_cancelled",
            settlement=(),
        )
        for stage in timeline.stages
    )
    steps = tuple(
        replace(
            step,
            owner="Historical Orders",
            status="unavailable",
            blockers=(),
            warnings=(notice,),
            availability_reason="historical_order_cancelled",
        )
        for step in timeline.sop_steps
    )
    return _with_projection_digest(
        timeline,
        current_stage_code=None,
        stages=stages,
        steps=steps,
    )


def _with_projection_digest(
    timeline: OrderOperationalTimeline,
    *,
    current_stage_code: str | None,
    stages: tuple[StageProjection, ...],
    steps: tuple[SopStepProjection, ...],
) -> OrderOperationalTimeline:
    payload = {
        "case_no": timeline.case_no,
        "base_revision": timeline.base_revision,
        "current_stage_code": current_stage_code,
        "stages": tuple(asdict(stage) for stage in stages),
        "sop_steps": tuple(asdict(step) for step in steps),
    }
    return OrderOperationalTimeline(
        timeline.case_no,
        timeline.base_revision,
        current_stage_code,
        stages,
        steps,
        _digest(payload),
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=_json_default,
        ).encode("utf-8")
    ).hexdigest()


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, OrderLifecycleStatus):
        return value.value
    raise TypeError(f"unsupported historical baseline value: {type(value).__name__}")


__all__ = [
    "HistoricalStageBaselineFacts",
    "HistoricalStageBaselineOverlayService",
    "HistoricalStageBaselineRepository",
    "OperationalTimelineQueryPort",
    "historical_baseline_step",
]
