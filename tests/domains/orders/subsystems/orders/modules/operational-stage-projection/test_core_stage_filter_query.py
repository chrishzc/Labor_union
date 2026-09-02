"""Focused tests for Beta core-stage server-side filters, counts, and pagination."""

from datetime import datetime, timezone

import pytest

from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.orders.core_stage_filter_query import (
    CoreStageProjectionFilterQuery,
    query_core_stage_page,
)
from subsystems.orders.stage_projection_query import (
    AvailableAction,
    MAXIMUM_PAGE_SIZE,
    OrderOperationalTimeline,
    OrderOperationalTimelinePage,
    ProjectionNotice,
    SettlementProjection,
    SopStepProjection,
    SourceLineage,
    StageProjection,
)


_AT = datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc)
_DIGEST = "a" * 64
_STAGE_CODES = (
    "intake_terms",
    "matching_willingness",
    "client_review",
    "contract_deposit",
    "date_confirmation",
    "active_service",
    "settlement_payout",
)
_STEP_CODES = (
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
    "settlement_close",
)


def _source(owner: str, identity: str) -> SourceLineage:
    return SourceLineage(owner, identity, 1)


def _stage(ordinal: int, code: str, *, settlement=()) -> StageProjection:
    return StageProjection(
        ordinal=ordinal,
        code=code,
        label=code,
        owner=f"owner-{code}",
        status="completed",
        source=_source(f"source-{code}", f"{code}:1"),
        occurred_at=_AT,
        blockers=(),
        warnings=(),
        available_actions=(AvailableAction(f"read.{code}", "GET", f"/read/{code}"),),
        availability_reason=None,
        settlement=settlement,
    )


def _step(
    ordinal: int,
    *,
    status: str = "completed",
    blockers: tuple[ProjectionNotice, ...] = (),
    warnings: tuple[ProjectionNotice, ...] = (),
) -> SopStepProjection:
    return SopStepProjection(
        ordinal=ordinal,
        code=_STEP_CODES[ordinal - 1],
        label=_STEP_CODES[ordinal - 1],
        owner=f"step-owner-{ordinal}",
        status=status,
        occurred_at=_AT,
        blockers=blockers,
        warnings=warnings,
        available_actions=(),
        availability_reason=None,
    )


def _timeline(
    case_no: str,
    *,
    lifecycle: OrderLifecycleStatus = OrderLifecycleStatus.IN_SERVICE,
    current_step: int | None = 10,
    step10_status: str = "in_progress",
    step10_blockers: tuple[ProjectionNotice, ...] = (),
    step10_warnings: tuple[ProjectionNotice, ...] = (),
) -> OrderOperationalTimeline:
    settlement = (
        SettlementProjection(
            "service_completion",
            "completed",
            _source("Orders", f"service-completion:{case_no}"),
            _AT,
            None,
        ),
        SettlementProjection(
            "client_settlement",
            "completed",
            _source("Client Finance", f"client-settlement:{case_no}"),
            _AT,
            None,
        ),
        SettlementProjection(
            "staff_payout",
            "completed",
            _source("Staff Payables", f"staff-payout:{case_no}"),
            _AT,
            None,
        ),
    )
    stages = tuple(
        _stage(index + 1, code, settlement=settlement if code == "settlement_payout" else ())
        for index, code in enumerate(_STAGE_CODES)
    )
    steps = tuple(
        _step(
            index,
            status=step10_status if index == 10 else "completed",
            blockers=step10_blockers if index == 10 else (),
            warnings=step10_warnings if index == 10 else (),
        )
        for index in range(1, 12)
    )
    return OrderOperationalTimeline(
        case_no=case_no,
        base_revision=1,
        lifecycle_status=lifecycle,
        replacement_resume_step_ordinal=None,
        current_stage_code="active_service" if current_step == 10 else None,
        current_step_ordinal=current_step,
        stages=stages,
        sop_steps=steps,
        projection_digest=_DIGEST,
    )


def _page(
    *items: OrderOperationalTimeline,
    next_cursor: str | None = None,
    etag: str = "b" * 64,
) -> OrderOperationalTimelinePage:
    return OrderOperationalTimelinePage(
        items=tuple(items),
        stage_counts={code: 0 for code in _STAGE_CODES},
        next_cursor=next_cursor,
        etag=etag,
    )


class _Source:
    def __init__(self, pages: dict[str | None, OrderOperationalTimelinePage]) -> None:
        self.pages = pages
        self.requests = []

    def query(self, request):
        self.requests.append(request)
        return self.pages[request.after_case_no]


def test_typed_query_rejects_unknown_or_cross_stage_substatus():
    with pytest.raises(ValueError):
        CoreStageProjectionFilterQuery(50, stage="unknown")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        CoreStageProjectionFilterQuery(
            50,
            stage="formal_service",
            substatus_code="unknown",
        )  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        CoreStageProjectionFilterQuery(
            50,
            stage="formal_service",
            substatus_code="intake_pending",
        )
    with pytest.raises(ValueError):
        CoreStageProjectionFilterQuery(50, substatus_code="waiting_to_start")


def test_formal_service_planned_and_active_filters_share_consistent_facet_counts():
    planned = _timeline("CASE-001", step10_status="not_started")
    active = _timeline("CASE-002", step10_status="in_progress")
    source = _Source({None: _page(planned, active)})

    stage_page = query_core_stage_page(
        source,
        CoreStageProjectionFilterQuery(50, stage="formal_service"),
    )
    assert [item.case_no for item in stage_page.items] == ["CASE-001", "CASE-002"]
    assert stage_page.stage_counts["formal_service"] == 2
    assert stage_page.substatus_counts["waiting_to_start"] == 1
    assert stage_page.substatus_counts["service_in_progress"] == 1

    planned_page = query_core_stage_page(
        source,
        CoreStageProjectionFilterQuery(
            50,
            stage="formal_service",
            substatus_code="waiting_to_start",
        ),
    )
    assert [item.case_no for item in planned_page.items] == ["CASE-001"]
    assert planned_page.stage_counts["formal_service"] == 2
    assert planned_page.substatus_counts["waiting_to_start"] == 1
    assert planned_page.substatus_counts["service_in_progress"] == 1


def test_blocker_warning_case_search_and_branch_filters_are_server_side():
    blocker = ProjectionNotice("service_blocked", "服務根事實有 blocker。")
    warning = ProjectionNotice("service_warning", "服務根事實有 warning。")
    source = _Source(
        {
            None: _page(
                _timeline("CASE-BLOCK", step10_status="blocked", step10_blockers=(blocker,)),
                _timeline(
                    "CASE-CANCEL",
                    lifecycle=OrderLifecycleStatus.CANCELLED,
                    current_step=None,
                ),
                _timeline(
                    "CASE-HIST",
                    lifecycle=OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
                    current_step=10,
                ),
                _timeline("CASE-WARN", step10_warnings=(warning,)),
            )
        }
    )

    blocker_page = query_core_stage_page(
        source,
        CoreStageProjectionFilterQuery(50, blocker_only=True),
    )
    assert [item.case_no for item in blocker_page.items] == ["CASE-BLOCK"]

    warning_page = query_core_stage_page(
        source,
        CoreStageProjectionFilterQuery(50, warning_only=True),
    )
    assert [item.case_no for item in warning_page.items] == ["CASE-WARN"]

    historical_page = query_core_stage_page(
        source,
        CoreStageProjectionFilterQuery(50, branch_type="historical"),
    )
    assert [item.case_no for item in historical_page.items] == ["CASE-HIST"]

    cancelled_page = query_core_stage_page(
        source,
        CoreStageProjectionFilterQuery(50, branch_type="cancelled"),
    )
    assert [item.case_no for item in cancelled_page.items] == ["CASE-CANCEL"]

    search_page = query_core_stage_page(
        source,
        CoreStageProjectionFilterQuery(50, case_no_search="warn"),
    )
    assert [item.case_no for item in search_page.items] == ["CASE-WARN"]


def test_filtered_pagination_has_no_duplicates_or_gaps_and_counts_ignore_cursor():
    source = _Source(
        {
            None: _page(
                _timeline("CASE-001", step10_status="not_started"),
                _timeline("CASE-002", step10_status="in_progress"),
                next_cursor="CASE-002",
            ),
            "CASE-002": _page(
                _timeline("CASE-003", step10_status="not_started"),
                _timeline("CASE-004", step10_status="in_progress"),
            ),
        }
    )

    first = query_core_stage_page(
        source,
        CoreStageProjectionFilterQuery(2, stage="formal_service"),
    )
    second = query_core_stage_page(
        source,
        CoreStageProjectionFilterQuery(
            2,
            after_case_no=first.next_cursor,
            stage="formal_service",
        ),
    )

    assert [item.case_no for item in first.items] == ["CASE-001", "CASE-002"]
    assert first.next_cursor == "CASE-002"
    assert [item.case_no for item in second.items] == ["CASE-003", "CASE-004"]
    assert second.next_cursor is None
    assert first.stage_counts["formal_service"] == 4
    assert second.stage_counts["formal_service"] == 4
    assert first.substatus_counts == second.substatus_counts
    assert first.etag != second.etag
    assert all(request.page_size == MAXIMUM_PAGE_SIZE for request in source.requests)
