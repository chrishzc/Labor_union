"""Focused contract tests for the dry-run thirteen core-stage projection."""

from datetime import datetime, timezone

from fastapi import Response

from api.routes.orders_core_stage_projection import get_order_core_stage_timelines
from api.routes.orders_stage_projection import get_order_operational_timelines
from api.schemas.orders_core_stage_projection import OrderCoreStageTimelinePageView
from domains.orders.lifecycle import OrderLifecycleScope, OrderLifecycleStatus
from subsystems.orders.core_stage_projection_query import project_core_stage_page
from subsystems.orders.stage_projection_query import (
    AvailableAction,
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
_ETAG = "b" * 64
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
_STAGE_CODES = (
    "intake_terms",
    "matching_willingness",
    "client_review",
    "contract_deposit",
    "date_confirmation",
    "active_service",
    "settlement_payout",
)
_CORE_CODES = (
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


def _step(ordinal: int, status: str = "completed") -> SopStepProjection:
    return SopStepProjection(
        ordinal=ordinal,
        code=_STEP_CODES[ordinal - 1],
        label=_STEP_CODES[ordinal - 1],
        owner=f"step-owner-{ordinal}",
        status=status,
        occurred_at=_AT,
        blockers=(),
        warnings=(),
        available_actions=(),
        availability_reason=None,
    )


def _timeline(
    lifecycle: OrderLifecycleStatus = OrderLifecycleStatus.COMPLETED,
    current_step: int | None = 11,
) -> OrderOperationalTimeline:
    settlement = (
        SettlementProjection(
            "service_completion",
            "completed",
            _source("Orders", "service-completion:1"),
            _AT,
            None,
        ),
        SettlementProjection(
            "client_settlement",
            "blocked",
            _source("Client Finance", "client-settlement:1"),
            _AT,
            None,
        ),
        SettlementProjection(
            "staff_payout",
            "unavailable",
            SourceLineage("Staff Payables", None, 1),
            None,
            "obligation_projection_missing",
        ),
    )
    stages = tuple(
        _stage(index + 1, code, settlement=settlement if code == "settlement_payout" else ())
        for index, code in enumerate(_STAGE_CODES)
    )
    settlement_stage = stages[-1]
    stages = stages[:-1] + (
        StageProjection(
            ordinal=settlement_stage.ordinal,
            code=settlement_stage.code,
            label=settlement_stage.label,
            owner=settlement_stage.owner,
            status="blocked",
            source=settlement_stage.source,
            occurred_at=settlement_stage.occurred_at,
            blockers=(
                ProjectionNotice(
                    "client_settlement_not_complete",
                    "Client Finance 子投影尚未完成。",
                ),
            ),
            warnings=(),
            available_actions=(),
            availability_reason=None,
            settlement=settlement,
        ),
    )
    return OrderOperationalTimeline(
        case_no="CASE-CORE-001",
        base_revision=7,
        lifecycle_status=lifecycle,
        replacement_resume_step_ordinal=None,
        current_stage_code="settlement_payout" if current_step == 11 else "active_service",
        current_step_ordinal=current_step,
        stages=stages,
        sop_steps=tuple(_step(index + 1) for index in range(11)),
        projection_digest=_DIGEST,
    )


def _page(timeline: OrderOperationalTimeline) -> OrderOperationalTimelinePage:
    return OrderOperationalTimelinePage(
        items=(timeline,),
        stage_counts={code: 0 for code in _STAGE_CODES},
        next_cursor=None,
        etag=_ETAG,
    )


class _Application:
    def __init__(self, page: OrderOperationalTimelinePage) -> None:
        self.page = page
        self.queries = []

    def query(self, request):
        self.queries.append(request)
        return self.page


def test_core_stage_contract_has_exactly_thirteen_stages_and_uses_settlement_owner_facts():
    projected = project_core_stage_page(_page(_timeline()))
    view = OrderCoreStageTimelinePageView.model_validate(projected, from_attributes=True)

    item = view.items[0]
    assert item.branch_type == "normal"
    assert tuple(stage.code for stage in item.core_stages) == _CORE_CODES
    assert len(item.core_stages) == 13
    assert item.current_core_stage_ordinal == 12
    assert item.current_core_stage_code == "client_settlement"

    completion, client, staff = item.core_stages[10:]
    assert completion.source.owner == "Orders"
    assert completion.source.identity == "service-completion:1"
    assert completion.substatus_code == "completion_confirmed"
    assert client.source.owner == "Client Finance"
    assert client.status == "blocked"
    assert client.substatus_code == "client_balance_open"
    assert [notice.code for notice in client.blockers] == ["client_settlement_not_complete"]
    assert staff.source.owner == "Staff Payables"
    assert staff.source.identity is None
    assert staff.status == "unavailable"
    assert staff.availability_reason == "obligation_projection_missing"


def test_historical_and_cancelled_orders_are_explicit_branches_without_mainline_current_stage():
    historical = project_core_stage_page(
        _page(_timeline(OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED))
    ).items[0]
    cancelled = project_core_stage_page(
        _page(_timeline(OrderLifecycleStatus.CANCELLED, None))
    ).items[0]

    assert historical.branch_type == "historical"
    assert historical.current_core_stage_code is None
    assert historical.current_core_stage_ordinal is None
    assert cancelled.branch_type == "cancelled"
    assert cancelled.current_core_stage_code is None
    assert cancelled.current_core_stage_ordinal is None


def test_new_endpoint_is_independent_and_old_operational_timeline_contract_still_validates():
    source_page = _page(_timeline())
    application = _Application(source_page)

    new_response = Response()
    new_result = get_order_core_stage_timelines(
        new_response,
        page_size=50,
        after_case_no=None,
        lifecycle_scope=OrderLifecycleScope.ALL,
        if_none_match=None,
        principal=object(),
        application=application,
    )
    assert len(new_result.data.items[0].core_stages) == 13
    assert new_response.headers["etag"] == f'"{_ETAG}"'

    old_response = Response()
    old_result = get_order_operational_timelines(
        old_response,
        page_size=50,
        after_case_no=None,
        lifecycle_scope=OrderLifecycleScope.ALL,
        if_none_match=None,
        principal=object(),
        application=application,
    )
    assert len(old_result.data.items[0].stages) == 7
    assert len(old_result.data.items[0].sop_steps) == 11
    assert old_response.headers["etag"] == f'"{_ETAG}"'
