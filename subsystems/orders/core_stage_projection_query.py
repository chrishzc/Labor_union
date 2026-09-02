"""
File: core_stage_projection_query.py
Description: 將既有 Orders 七階段／十一 SOP 唯讀投影轉成 Beta 專用十三核心階段契約。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Mapping

from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.orders.stage_projection_query import (
    AvailableAction,
    OrderOperationalTimeline,
    OrderOperationalTimelinePage,
    ProjectionNotice,
    SourceLineage,
    StageProjection,
    StageStatus,
)


CoreStageBranchType = Literal["normal", "historical", "cancelled"]
CoreStageCode = Literal[
    "intake_validation",
    "matching_pool",
    "caregiver_line_delivery",
    "caregiver_willingness_reply",
    "formal_recommendation",
    "caregiver_contract",
    "deposit_settlement",
    "client_contract",
    "confirmed_service_dates",
    "formal_service",
    "service_completion",
    "client_settlement",
    "staff_payout",
]


class CoreStageProjectionContractError(ValueError):
    """代表既有 operational timeline 無法安全轉成十三核心階段契約。"""


@dataclass(frozen=True)
class CoreStageProjection:
    ordinal: int
    code: CoreStageCode
    label: str
    owner: str
    status: StageStatus
    substatus_code: str
    source: SourceLineage
    occurred_at: datetime | None
    blockers: tuple[ProjectionNotice, ...]
    warnings: tuple[ProjectionNotice, ...]
    available_read_actions: tuple[AvailableAction, ...]
    availability_reason: str | None


@dataclass(frozen=True)
class OrderCoreStageTimeline:
    case_no: str
    base_revision: int
    lifecycle_status: OrderLifecycleStatus
    branch_type: CoreStageBranchType
    current_core_stage_code: CoreStageCode | None
    current_core_stage_ordinal: int | None
    core_stages: tuple[CoreStageProjection, ...]
    source_projection_digest: str


@dataclass(frozen=True)
class OrderCoreStageTimelinePage:
    items: tuple[OrderCoreStageTimeline, ...]
    next_cursor: str | None
    etag: str


_STAGE_META: tuple[tuple[int, CoreStageCode, str], ...] = (
    (1, "intake_validation", "進件與資料完整性驗證"),
    (2, "matching_pool", "建立候選月嫂池"),
    (3, "caregiver_line_delivery", "詢問月嫂接案意願"),
    (4, "caregiver_willingness_reply", "等待月嫂意願回覆"),
    (5, "formal_recommendation", "推薦月嫂給客戶確認"),
    (6, "caregiver_contract", "月嫂契約簽署"),
    (7, "deposit_settlement", "客戶定金核銷"),
    (8, "client_contract", "客戶契約簽署"),
    (9, "confirmed_service_dates", "正式服務日期確認"),
    (10, "formal_service", "正式排班與服務履約"),
    (11, "service_completion", "完工／服務完成確認"),
    (12, "client_settlement", "客戶端結算"),
    (13, "staff_payout", "月嫂端結算"),
)

_SOURCE_STAGE_BY_ORDINAL: Mapping[int, str] = {
    1: "intake_terms",
    2: "matching_willingness",
    3: "matching_willingness",
    4: "matching_willingness",
    5: "client_review",
    6: "contract_deposit",
    7: "contract_deposit",
    8: "contract_deposit",
    9: "date_confirmation",
    10: "active_service",
}

_SUBSTATUS_BY_CODE: Mapping[CoreStageCode, Mapping[StageStatus, str]] = {
    "intake_validation": {
        "not_started": "intake_pending",
        "in_progress": "intake_in_progress",
        "blocked": "intake_blocked",
        "completed": "data_complete",
        "unavailable": "intake_unavailable",
    },
    "matching_pool": {
        "not_started": "candidate_pool_pending",
        "in_progress": "candidate_pool_building",
        "blocked": "candidate_pool_blocked",
        "completed": "candidate_pool_ready",
        "unavailable": "candidate_pool_unavailable",
    },
    "caregiver_line_delivery": {
        "not_started": "contact_pending",
        "in_progress": "contact_in_progress",
        "blocked": "contact_blocked",
        "completed": "contact_completed",
        "unavailable": "contact_unavailable",
    },
    "caregiver_willingness_reply": {
        "not_started": "reply_pending",
        "in_progress": "reply_partial",
        "blocked": "reply_blocked",
        "completed": "reply_complete",
        "unavailable": "reply_unavailable",
    },
    "formal_recommendation": {
        "not_started": "recommendation_pending",
        "in_progress": "recommendation_in_progress",
        "blocked": "recommendation_blocked",
        "completed": "recommendation_completed",
        "unavailable": "recommendation_unavailable",
    },
    "caregiver_contract": {
        "not_started": "caregiver_contract_pending",
        "in_progress": "caregiver_contract_signing",
        "blocked": "caregiver_contract_blocked",
        "completed": "caregiver_contract_completed",
        "unavailable": "caregiver_contract_unavailable",
    },
    "deposit_settlement": {
        "not_started": "deposit_pending",
        "in_progress": "deposit_in_progress",
        "blocked": "deposit_blocked",
        "completed": "deposit_settled",
        "unavailable": "deposit_unavailable",
    },
    "client_contract": {
        "not_started": "client_contract_pending",
        "in_progress": "client_contract_signing",
        "blocked": "client_contract_blocked",
        "completed": "client_contract_completed",
        "unavailable": "client_contract_unavailable",
    },
    "confirmed_service_dates": {
        "not_started": "date_confirmation_pending",
        "in_progress": "date_confirmation_in_progress",
        "blocked": "date_confirmation_blocked",
        "completed": "date_confirmed",
        "unavailable": "date_confirmation_unavailable",
    },
    "formal_service": {
        "not_started": "waiting_to_start",
        "in_progress": "service_in_progress",
        "blocked": "service_blocked",
        "completed": "service_period_completed",
        "unavailable": "service_schedule_unavailable",
    },
    "service_completion": {
        "not_started": "completion_pending",
        "in_progress": "completion_in_progress",
        "blocked": "completion_blocked",
        "completed": "completion_confirmed",
        "unavailable": "completion_record_missing",
    },
    "client_settlement": {
        "not_started": "client_settlement_pending",
        "in_progress": "client_settlement_in_progress",
        "blocked": "client_balance_open",
        "completed": "client_settled",
        "unavailable": "client_settlement_unavailable",
    },
    "staff_payout": {
        "not_started": "staff_settlement_pending",
        "in_progress": "staff_settlement_in_progress",
        "blocked": "staff_payable_open",
        "completed": "staff_settled",
        "unavailable": "staff_settlement_unavailable",
    },
}

_HISTORICAL_STATUSES = frozenset(
    {
        OrderLifecycleStatus.HISTORICAL_UNSERVED,
        OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
    }
)


def project_core_stage_page(page: OrderOperationalTimelinePage) -> OrderCoreStageTimelinePage:
    if not isinstance(page, OrderOperationalTimelinePage):
        raise TypeError("page must be an OrderOperationalTimelinePage")
    return OrderCoreStageTimelinePage(
        items=tuple(project_core_stage_timeline(item) for item in page.items),
        next_cursor=page.next_cursor,
        etag=page.etag,
    )


def project_core_stage_timeline(timeline: OrderOperationalTimeline) -> OrderCoreStageTimeline:
    if not isinstance(timeline, OrderOperationalTimeline):
        raise TypeError("timeline must be an OrderOperationalTimeline")
    if len(timeline.stages) != 7 or len(timeline.sop_steps) != 11:
        raise CoreStageProjectionContractError("source projection shape is not canonical")

    stages_by_code = {stage.code: stage for stage in timeline.stages}
    if len(stages_by_code) != 7:
        raise CoreStageProjectionContractError("source stage identity is duplicate")

    first_ten = tuple(
        _core_from_step(timeline, ordinal, code, label, stages_by_code)
        for ordinal, code, label in _STAGE_META[:10]
    )
    settlement_stage = stages_by_code.get("settlement_payout")
    if settlement_stage is None:
        raise CoreStageProjectionContractError("settlement_payout source stage is missing")
    final_three = tuple(
        _core_from_settlement(settlement_stage, ordinal, code, label)
        for ordinal, code, label in _STAGE_META[10:]
    )
    core_stages = first_ten + final_three
    branch_type = _branch_type(timeline.lifecycle_status)
    current = _current_core_stage(branch_type, timeline.current_step_ordinal, core_stages)
    return OrderCoreStageTimeline(
        case_no=timeline.case_no,
        base_revision=timeline.base_revision,
        lifecycle_status=timeline.lifecycle_status,
        branch_type=branch_type,
        current_core_stage_code=current.code if current is not None else None,
        current_core_stage_ordinal=current.ordinal if current is not None else None,
        core_stages=core_stages,
        source_projection_digest=timeline.projection_digest,
    )


def _core_from_step(
    timeline: OrderOperationalTimeline,
    ordinal: int,
    code: CoreStageCode,
    label: str,
    stages_by_code: Mapping[str, StageProjection],
) -> CoreStageProjection:
    step = timeline.sop_steps[ordinal - 1]
    if step.ordinal != ordinal or step.code != code:
        raise CoreStageProjectionContractError("source SOP step identity is not canonical")
    source_stage = stages_by_code.get(_SOURCE_STAGE_BY_ORDINAL[ordinal])
    if source_stage is None:
        raise CoreStageProjectionContractError("source stage lineage is missing")
    actions = step.available_actions or source_stage.available_actions
    return CoreStageProjection(
        ordinal=ordinal,
        code=code,
        label=label,
        owner=step.owner,
        status=step.status,
        substatus_code=_substatus(code, step.status),
        source=source_stage.source,
        occurred_at=step.occurred_at,
        blockers=step.blockers,
        warnings=step.warnings,
        available_read_actions=actions,
        availability_reason=step.availability_reason,
    )


def _core_from_settlement(
    stage: StageProjection,
    ordinal: int,
    code: CoreStageCode,
    label: str,
) -> CoreStageProjection:
    parts = {part.code: part for part in stage.settlement}
    part = parts.get(code)
    if part is None:
        raise CoreStageProjectionContractError(f"{code} settlement source is missing")
    blockers = tuple(
        notice for notice in stage.blockers if notice.code.startswith(f"{code}_")
    )
    warnings = tuple(
        notice for notice in stage.warnings if notice.code.startswith(f"{code}_")
    )
    return CoreStageProjection(
        ordinal=ordinal,
        code=code,
        label=label,
        owner=part.source.owner,
        status=part.status,
        substatus_code=_substatus(code, part.status),
        source=part.source,
        occurred_at=part.occurred_at,
        blockers=blockers,
        warnings=warnings,
        available_read_actions=(),
        availability_reason=part.availability_reason,
    )


def _branch_type(status: OrderLifecycleStatus) -> CoreStageBranchType:
    if status is OrderLifecycleStatus.CANCELLED:
        return "cancelled"
    if status in _HISTORICAL_STATUSES:
        return "historical"
    return "normal"


def _current_core_stage(
    branch_type: CoreStageBranchType,
    source_current_step: int | None,
    stages: tuple[CoreStageProjection, ...],
) -> CoreStageProjection | None:
    if branch_type != "normal" or source_current_step is None:
        return None
    if 1 <= source_current_step <= 10:
        return stages[source_current_step - 1]
    if source_current_step != 11:
        raise CoreStageProjectionContractError("source current step is outside the closed contract")
    return next((stage for stage in stages[10:] if stage.status != "completed"), None)


def _substatus(code: CoreStageCode, status: StageStatus) -> str:
    try:
        return _SUBSTATUS_BY_CODE[code][status]
    except KeyError as exc:
        raise CoreStageProjectionContractError("core stage substatus mapping is incomplete") from exc


__all__ = [
    "CoreStageProjection",
    "CoreStageProjectionContractError",
    "OrderCoreStageTimeline",
    "OrderCoreStageTimelinePage",
    "project_core_stage_page",
    "project_core_stage_timeline",
]
