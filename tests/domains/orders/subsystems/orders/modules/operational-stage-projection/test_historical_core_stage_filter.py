"""Focused #88 tests for server-owned Historical Orders lifecycle facets."""

from datetime import datetime, timezone

import pytest

from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.orders.core_stage_filter_query import (
    CoreStageProjectionFilterQuery,
    query_core_stage_page,
)
from subsystems.orders.stage_projection_query import (
    OrderOperationalTimeline,
    OrderOperationalTimelinePage,
    SettlementProjection,
    SopStepProjection,
    SourceLineage,
    StageProjection,
)


_AT = datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc)
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


def _timeline(case_no: str, lifecycle: OrderLifecycleStatus) -> OrderOperationalTimeline:
    settlement = (
        SettlementProjection("service_completion", "completed", _source("Orders", f"completion:{case_no}"), _AT, None),
        SettlementProjection("client_settlement", "in_progress", _source("Client Finance", f"client:{case_no}"), _AT, None),
        SettlementProjection("staff_payout", "not_started", _source("Staff Payables", f"staff:{case_no}"), _AT, None),
    )
    stages = tuple(
        StageProjection(
            ordinal=index + 1,
            code=code,
            label=code,
            owner=f"owner-{code}",
            status="completed" if code != "settlement_payout" else "in_progress",
            source=_source(f"source-{code}", f"{code}:{case_no}"),
            occurred_at=_AT,
            blockers=(),
            warnings=(),
            available_actions=(),
            availability_reason=None,
            settlement=settlement if code == "settlement_payout" else (),
        )
        for index, code in enumerate(_STAGE_CODES)
    )
    current_step = {
        OrderLifecycleStatus.HISTORICAL_UNSERVED: 9,
        OrderLifecycleStatus.HISTORICAL_IN_SERVICE: 10,
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED: 11,
        OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED: 11,
        OrderLifecycleStatus.CANCELLED: None,
    }[lifecycle]
    steps = tuple(
        SopStepProjection(
            ordinal=index,
            code=_STEP_CODES[index - 1],
            label=_STEP_CODES[index - 1],
            owner=f"step-owner-{index}",
            status="completed" if current_step is None or index < current_step else "in_progress",
            occurred_at=_AT,
            blockers=(),
            warnings=(),
            available_actions=(),
            availability_reason=None,
        )
        for index in range(1, 12)
    )
    return OrderOperationalTimeline(
        case_no=case_no,
        base_revision=7,
        lifecycle_status=lifecycle,
        replacement_resume_step_ordinal=None,
        current_stage_code=None if current_step is None else "settlement_payout",
        current_step_ordinal=current_step,
        stages=stages,
        sop_steps=steps,
        projection_digest="a" * 64,
    )


class _Source:
    def __init__(self, items):
        self.items = tuple(items)

    def query(self, request):
        assert request.after_case_no is None
        return OrderOperationalTimelinePage(
            items=self.items,
            stage_counts={code: 0 for code in _STAGE_CODES},
            next_cursor=None,
            etag="b" * 64,
        )


def test_four_historical_lifecycles_have_stable_server_counts_and_independent_filters():
    source = _Source((
        _timeline("H-UNSERVED", OrderLifecycleStatus.HISTORICAL_UNSERVED),
        _timeline("H-SERVICE", OrderLifecycleStatus.HISTORICAL_IN_SERVICE),
        _timeline("H-COMPLETE", OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED),
        _timeline("H-ACCOUNTING", OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED),
    ))

    all_historical = query_core_stage_page(
        source,
        CoreStageProjectionFilterQuery(50, branch_type="historical"),
    )
    assert all_historical.historical_lifecycle_counts == {
        "unserved": 1,
        "in_service": 1,
        "service_completed": 1,
        "accounting_completed": 1,
    }

    for facet, case_no in {
        "unserved": "H-UNSERVED",
        "in_service": "H-SERVICE",
        "service_completed": "H-COMPLETE",
        "accounting_completed": "H-ACCOUNTING",
    }.items():
        page = query_core_stage_page(
            source,
            CoreStageProjectionFilterQuery(
                50,
                branch_type="historical",
                historical_lifecycle=facet,
            ),
        )
        assert [item.case_no for item in page.items] == [case_no]
        assert page.historical_lifecycle_counts == all_historical.historical_lifecycle_counts


def test_historical_lifecycle_filter_is_typed_and_never_accepts_date_driven_guessing():
    with pytest.raises(ValueError):
        CoreStageProjectionFilterQuery(50, branch_type="normal", historical_lifecycle="unserved")
    with pytest.raises(ValueError):
        CoreStageProjectionFilterQuery(
            50,
            branch_type="historical",
            historical_lifecycle="future_source_start",  # type: ignore[arg-type]
        )
