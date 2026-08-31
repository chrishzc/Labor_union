"""Overlay immutable Historical Orders baselines onto the operational timeline.

Historical evidence may complete predecessor steps, but it never fabricates an
owning Domain root.  Once a baseline exists, the selected baseline step remains
immutable while current/future owner facts decide normal forward progression.
A concrete non-terminal predecessor owner fact may also move the current step
backward; a merely unavailable predecessor remains a historical gap and is not
interpreted as a new invalidation.
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
    selected_step: int | None = None
    baseline_event_identity: str | None = None
    baseline_event_version: int | None = None


class HistoricalStageBaselineRepository(Protocol):
    def fetch_for_cases(
        self, case_nos: tuple[str, ...]
    ) -> tuple[HistoricalStageBaselineFacts, ...]: ...


class OperationalTimelineQueryPort(Protocol):
    def query(self, request: StageProjectionQuery) -> OrderOperationalTimelinePage: ...


class HistoricalStageBaselineOverlayService:
    """Keep immutable historical predecessors and fresh owner progression together."""

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
                    (
                        item.case_no,
                        item.base_revision,
                        item.current_stage_code,
                        item.projection_digest,
                    )
                    for item in items
                ),
                "next_cursor": page.next_cursor,
            }
        )
        return OrderOperationalTimelinePage(items, counts, page.next_cursor, etag)


def historical_baseline_step(facts: HistoricalStageBaselineFacts) -> int | None:
    """Return the immutable selected step, falling back only for legacy adoption rows."""

    if facts.selected_step is not None:
        if isinstance(facts.selected_step, bool) or not 1 <= facts.selected_step <= 11:
            raise ValueError("historical_stage_baseline_step_invalid")
        return facts.selected_step
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
    if facts.selected_step is None and facts.lifecycle_status is OrderLifecycleStatus.CANCELLED:
        return _cancelled_timeline(timeline, facts)
    selected_step = historical_baseline_step(facts)
    if selected_step is None:
        return timeline

    current_step = _current_step(timeline.sop_steps, selected_step)
    historical_cutoff = min(selected_step, current_step)
    current_stage_ordinal = _stage_ordinal_for_step(current_step)

    steps = tuple(
        _baseline_step(step, facts)
        if step.ordinal < historical_cutoff and step.status != "completed"
        else step
        for step in timeline.sop_steps
    )
    stages = tuple(
        _baseline_stage(stage, facts)
        if stage.ordinal < current_stage_ordinal and stage.status != "completed"
        else stage
        for stage in timeline.stages
    )
    current_stage_code = timeline.stages[current_stage_ordinal - 1].code
    return _with_projection_digest(
        timeline,
        current_stage_code=current_stage_code,
        stages=stages,
        steps=steps,
    )


def _current_step(
    steps: tuple[SopStepProjection, ...],
    selected_step: int,
) -> int:
    """Project current work without treating old missing history as a new regression.

    Before the immutable baseline, only a concrete current owner state
    (not_started/in_progress/blocked) may reopen a step.  ``unavailable`` alone
    remains an allowed historical predecessor gap because H-06 requires a typed
    owner invalidation rather than inference from missing lineage.  From the
    selected step onward, the first non-completed owner projection is current.
    """

    if tuple(step.ordinal for step in steps) != tuple(range(1, 12)):
        raise ValueError("historical_stage_baseline_steps_invalid")
    for step in steps:
        if step.ordinal < selected_step:
            if step.status in {"not_started", "in_progress", "blocked"}:
                return step.ordinal
            continue
        if step.status != "completed":
            return step.ordinal
    return 11


def _stage_ordinal_for_step(step: int) -> int:
    if step == 1:
        return 1
    if 2 <= step <= 4:
        return 2
    if step == 5:
        return 3
    if 6 <= step <= 8:
        return 4
    if step == 9:
        return 5
    if step == 10:
        return 6
    if step == 11:
        return 7
    raise ValueError("historical_stage_baseline_step_invalid")


def _baseline_source(facts: HistoricalStageBaselineFacts) -> SourceLineage:
    if facts.baseline_event_identity is not None:
        return SourceLineage(
            "Historical Orders",
            facts.baseline_event_identity,
            facts.baseline_event_version,
        )
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
