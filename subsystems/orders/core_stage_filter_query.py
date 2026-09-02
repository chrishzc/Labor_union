"""
File: core_stage_filter_query.py
Description: 在待辦看板 Beta query boundary 執行十三核心階段篩選、facet counts 與確定性 pagination。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Literal, Mapping, Protocol, cast

from domains.orders.lifecycle import OrderLifecycleScope
from shared_kernel.validation import require_canonical_text
from subsystems.orders.core_stage_projection_query import (
    CoreStageBranchType,
    CoreStageCode,
    CoreStageProjection,
    CoreStageProjectionContractError,
    OrderCoreStageTimeline,
    _SUBSTATUS_BY_CODE,
    project_core_stage_timeline,
)
from subsystems.orders.stage_projection_query import (
    MAXIMUM_PAGE_SIZE,
    OrderOperationalTimelinePage,
    StageProjectionQuery,
)


CoreStageSubstatusCode = Literal[
    "intake_pending", "intake_in_progress", "intake_blocked", "data_complete", "intake_unavailable",
    "candidate_pool_pending", "candidate_pool_building", "candidate_pool_blocked", "candidate_pool_ready", "candidate_pool_unavailable",
    "contact_pending", "contact_in_progress", "contact_blocked", "contact_completed", "contact_unavailable",
    "reply_pending", "reply_partial", "reply_blocked", "reply_complete", "reply_unavailable",
    "recommendation_pending", "recommendation_in_progress", "recommendation_blocked", "recommendation_completed", "recommendation_unavailable",
    "caregiver_contract_pending", "caregiver_contract_signing", "caregiver_contract_blocked", "caregiver_contract_completed", "caregiver_contract_unavailable",
    "deposit_pending", "deposit_in_progress", "deposit_blocked", "deposit_settled", "deposit_unavailable",
    "client_contract_pending", "client_contract_signing", "client_contract_blocked", "client_contract_completed", "client_contract_unavailable",
    "date_confirmation_pending", "date_confirmation_in_progress", "date_confirmation_blocked", "date_confirmed", "date_confirmation_unavailable",
    "waiting_to_start", "service_in_progress", "service_blocked", "service_period_completed", "service_schedule_unavailable",
    "completion_pending", "completion_in_progress", "completion_blocked", "completion_confirmed", "completion_record_missing",
    "client_settlement_pending", "client_settlement_in_progress", "client_balance_open", "client_settled", "client_settlement_unavailable",
    "staff_settlement_pending", "staff_settlement_in_progress", "staff_payable_open", "staff_settled", "staff_settlement_unavailable",
]

_CORE_STAGE_CODES: tuple[CoreStageCode, ...] = (
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
)
_VALID_SUBSTATUSES = frozenset(
    value for mapping in _SUBSTATUS_BY_CODE.values() for value in mapping.values()
)


class OperationalTimelineQueryPort(Protocol):
    def query(self, request: StageProjectionQuery) -> OrderOperationalTimelinePage: ...


@dataclass(frozen=True)
class CoreStageProjectionFilterQuery:
    page_size: int
    after_case_no: str | None = None
    lifecycle_scope: OrderLifecycleScope = OrderLifecycleScope.ALL
    stage: CoreStageCode | None = None
    substatus_code: CoreStageSubstatusCode | None = None
    case_no_search: str | None = None
    blocker_only: bool = False
    warning_only: bool = False
    branch_type: CoreStageBranchType | None = None

    def __post_init__(self) -> None:
        StageProjectionQuery(self.page_size, self.after_case_no, self.lifecycle_scope)
        if self.stage is not None and self.stage not in _CORE_STAGE_CODES:
            raise ValueError("stage is outside the core-stage contract")
        if self.substatus_code is not None:
            if self.substatus_code not in _VALID_SUBSTATUSES:
                raise ValueError("substatus_code is outside the core-stage contract")
            if self.stage is None:
                raise ValueError("stage is required when substatus_code is provided")
            if self.substatus_code not in _SUBSTATUS_BY_CODE[self.stage].values():
                raise ValueError("substatus_code does not belong to stage")
        if self.case_no_search is not None:
            require_canonical_text(self.case_no_search, "case_no_search", 50)
        if not isinstance(self.blocker_only, bool):
            raise TypeError("blocker_only must be a bool")
        if not isinstance(self.warning_only, bool):
            raise TypeError("warning_only must be a bool")
        if self.branch_type not in {None, "normal", "historical", "cancelled"}:
            raise ValueError("branch_type is outside the core-stage contract")


@dataclass(frozen=True)
class OrderCoreStageTimelineFilteredPage:
    items: tuple[OrderCoreStageTimeline, ...]
    stage_counts: Mapping[CoreStageCode, int]
    substatus_counts: Mapping[CoreStageSubstatusCode, int]
    next_cursor: str | None
    etag: str


def query_core_stage_page(
    source: OperationalTimelineQueryPort,
    request: CoreStageProjectionFilterQuery,
) -> OrderCoreStageTimelineFilteredPage:
    if not isinstance(request, CoreStageProjectionFilterQuery):
        raise TypeError("request must be a CoreStageProjectionFilterQuery")

    stage_counts: dict[CoreStageCode, int] = {code: 0 for code in _CORE_STAGE_CODES}
    substatus_counts: dict[CoreStageSubstatusCode, int] = {}
    if request.stage is not None:
        substatus_counts = {
            cast(CoreStageSubstatusCode, code): 0
            for code in _SUBSTATUS_BY_CODE[request.stage].values()
        }

    selected: list[OrderCoreStageTimeline] = []
    has_more = False
    source_cursor: str | None = None
    last_source_key: str | None = None
    single_source_etag: str | None = None
    source_page_count = 0
    requested_cursor_key = request.after_case_no.casefold() if request.after_case_no else None

    while True:
        source_page = source.query(
            StageProjectionQuery(
                page_size=MAXIMUM_PAGE_SIZE,
                after_case_no=source_cursor,
                lifecycle_scope=request.lifecycle_scope,
            )
        )
        _validate_source_page(source_page, source_cursor)
        source_page_count += 1
        if source_page_count == 1 and source_page.next_cursor is None:
            single_source_etag = source_page.etag
        else:
            single_source_etag = None

        for source_item in source_page.items:
            item = project_core_stage_timeline(source_item)
            identity_key = item.case_no.casefold()
            if last_source_key is not None and identity_key <= last_source_key:
                raise CoreStageProjectionContractError(
                    "source pages are duplicate or unordered"
                )
            last_source_key = identity_key

            if not _matches_common_filters(item, request):
                continue
            current_stage = _current_stage(item)
            if current_stage is not None:
                stage_counts[current_stage.code] += 1
                if request.stage == current_stage.code:
                    substatus = cast(CoreStageSubstatusCode, current_stage.substatus_code)
                    substatus_counts[substatus] += 1

            if requested_cursor_key is not None and identity_key <= requested_cursor_key:
                continue
            if not _matches_stage_filters(current_stage, request):
                continue
            if len(selected) < request.page_size:
                selected.append(item)
            else:
                has_more = True

        if source_page.next_cursor is None:
            break
        source_cursor = source_page.next_cursor

    items = tuple(selected)
    next_cursor = items[-1].case_no if has_more and items else None
    etag = _response_etag(items, stage_counts, substatus_counts, next_cursor)
    if _can_reuse_single_source_etag(request, items, single_source_etag):
        etag = cast(str, single_source_etag)
    return OrderCoreStageTimelineFilteredPage(
        items=items,
        stage_counts=stage_counts,
        substatus_counts=substatus_counts,
        next_cursor=next_cursor,
        etag=etag,
    )


def _validate_source_page(page: object, previous_cursor: str | None) -> None:
    if not isinstance(page, OrderOperationalTimelinePage):
        raise CoreStageProjectionContractError(
            "source query did not return an operational timeline page"
        )
    if len(page.items) > MAXIMUM_PAGE_SIZE:
        raise CoreStageProjectionContractError("source page is not bounded")
    if page.next_cursor is None:
        return
    if not page.items:
        raise CoreStageProjectionContractError("source page cursor has no anchor item")
    if page.next_cursor.casefold() != page.items[-1].case_no.casefold():
        raise CoreStageProjectionContractError("source page cursor is not the last item")
    if previous_cursor is not None and page.next_cursor.casefold() <= previous_cursor.casefold():
        raise CoreStageProjectionContractError("source page cursor did not advance")


def _matches_common_filters(
    item: OrderCoreStageTimeline,
    request: CoreStageProjectionFilterQuery,
) -> bool:
    if request.branch_type is not None and item.branch_type != request.branch_type:
        return False
    if (
        request.case_no_search is not None
        and request.case_no_search.casefold() not in item.case_no.casefold()
    ):
        return False
    if request.blocker_only and not any(stage.blockers for stage in item.core_stages):
        return False
    if request.warning_only and not any(stage.warnings for stage in item.core_stages):
        return False
    return True


def _current_stage(item: OrderCoreStageTimeline) -> CoreStageProjection | None:
    if item.current_core_stage_code is None:
        return None
    for stage in item.core_stages:
        if stage.code == item.current_core_stage_code:
            return stage
    raise CoreStageProjectionContractError("current core stage is missing from timeline")


def _matches_stage_filters(
    current_stage: CoreStageProjection | None,
    request: CoreStageProjectionFilterQuery,
) -> bool:
    if request.stage is None:
        return True
    if current_stage is None or current_stage.code != request.stage:
        return False
    return (
        request.substatus_code is None
        or current_stage.substatus_code == request.substatus_code
    )


def _response_etag(
    items: tuple[OrderCoreStageTimeline, ...],
    stage_counts: Mapping[CoreStageCode, int],
    substatus_counts: Mapping[CoreStageSubstatusCode, int],
    next_cursor: str | None,
) -> str:
    payload = {
        "items": tuple((item.case_no, item.source_projection_digest) for item in items),
        "stage_counts": stage_counts,
        "substatus_counts": substatus_counts,
        "next_cursor": next_cursor,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _can_reuse_single_source_etag(
    request: CoreStageProjectionFilterQuery,
    items: tuple[OrderCoreStageTimeline, ...],
    source_etag: str | None,
) -> bool:
    return (
        source_etag is not None
        and request.after_case_no is None
        and request.stage is None
        and request.substatus_code is None
        and request.case_no_search is None
        and not request.blocker_only
        and not request.warning_only
        and request.branch_type is None
        and len(items) <= request.page_size
    )


__all__ = [
    "CoreStageProjectionFilterQuery",
    "CoreStageSubstatusCode",
    "OrderCoreStageTimelineFilteredPage",
    "query_core_stage_page",
]
