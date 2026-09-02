"""Focused tests for the Order Workbench Beta terminal aggregate."""

from datetime import datetime, timezone

from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.orders.core_stage_projection_query import (
    CoreStageProjection,
    OrderCoreStageTimeline,
)
from subsystems.orders.government_subsidy_projection_query import (
    OrderGovernmentSubsidyProjection,
)
from subsystems.orders.stage_projection_query import ProjectionNotice, SourceLineage
from subsystems.orders.terminal_aggregate_query import project_terminal_aggregate


_AT = datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc)
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


def _core_stage(index: int, code: str, *, blocked: bool = False) -> CoreStageProjection:
    owner = f"owner-{code}"
    return CoreStageProjection(
        ordinal=index,
        code=code,  # type: ignore[arg-type]
        label=code,
        owner=owner,
        status="blocked" if blocked else "completed",
        substatus_code=f"{code}-blocked" if blocked else f"{code}-completed",
        source=SourceLineage(owner, f"{code}:1", 1),
        occurred_at=_AT,
        blockers=(
            ProjectionNotice(f"{code}_not_complete", f"{owner} 尚未完成。"),
        ) if blocked else (),
        warnings=(),
        available_read_actions=(),
        availability_reason=None,
    )


def _timeline(
    *,
    blocked_code: str | None = None,
    lifecycle_status: OrderLifecycleStatus = OrderLifecycleStatus.COMPLETED,
    branch_type: str = "normal",
) -> OrderCoreStageTimeline:
    stages = tuple(
        _core_stage(index, code, blocked=code == blocked_code)
        for index, code in enumerate(_CORE_CODES, start=1)
    )
    return OrderCoreStageTimeline(
        case_no="CASE-TERMINAL-001",
        base_revision=3,
        lifecycle_status=lifecycle_status,
        branch_type=branch_type,  # type: ignore[arg-type]
        current_core_stage_code=None,
        current_core_stage_ordinal=None,
        historical_current_owner_stage_code=None,
        historical_current_owner_stage_ordinal=None,
        core_stages=stages,
        source_projection_digest="a" * 64,
    )


def _subsidy(substatus_code: str) -> OrderGovernmentSubsidyProjection:
    return OrderGovernmentSubsidyProjection(
        case_no="CASE-TERMINAL-001",
        substatus_code=substatus_code,  # type: ignore[arg-type]
        identity_status="一般市民",
        source=SourceLineage("Government Subsidy", "claim-batch:1", 1),
        occurred_at=_AT,
        blockers=(),
        warnings=(),
        available_read_actions=(),
        claim_batch_id=1,
        claim_item_count=1,
        claimed_hours=80,
        unit_price_ntd=300,
        requested_amount_ntd=24000,
        approved_amount_ntd=24000,
        net_allocated_ntd=24000,
        overpayment_identity=None,
        overpayment_remaining_ntd=None,
    )


def test_normal_order_is_fully_closed_only_when_all_core_and_subsidy_components_complete():
    aggregate = project_terminal_aggregate(_timeline(), _subsidy("paid"))

    assert aggregate.applicable is True
    assert aggregate.fully_closed is True
    assert tuple(component.code for component in aggregate.components) == (
        *_CORE_CODES,
        "government_subsidy",
    )
    assert len(aggregate.components) == 14
    assert all(component.completed for component in aggregate.components)


def test_incomplete_core_owner_component_keeps_terminal_aggregate_open():
    aggregate = project_terminal_aggregate(
        _timeline(blocked_code="client_settlement"),
        _subsidy("paid"),
    )

    assert aggregate.fully_closed is False
    client = next(
        component for component in aggregate.components if component.code == "client_settlement"
    )
    assert client.owner == "owner-client_settlement"
    assert client.completed is False
    assert client.reason == "client_settlement_not_complete"


def test_nonterminal_government_subsidy_status_keeps_terminal_aggregate_open():
    aggregate = project_terminal_aggregate(_timeline(), _subsidy("submitted"))

    assert aggregate.fully_closed is False
    subsidy = aggregate.components[-1]
    assert subsidy.code == "government_subsidy"
    assert subsidy.owner == "Government Subsidy"
    assert subsidy.completed is False
    assert subsidy.reason == "submitted"


def test_historical_order_is_classified_outside_terminal_aggregate():
    aggregate = project_terminal_aggregate(
        _timeline(
            lifecycle_status=OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
            branch_type="historical",
        ),
        _subsidy("paid"),
    )

    assert aggregate.applicable is False
    assert aggregate.fully_closed is False
    assert aggregate.components == ()


def test_cancelled_order_is_classified_outside_terminal_aggregate():
    aggregate = project_terminal_aggregate(
        _timeline(
            lifecycle_status=OrderLifecycleStatus.CANCELLED,
            branch_type="cancelled",
        ),
        _subsidy("paid"),
    )

    assert aggregate.applicable is False
    assert aggregate.fully_closed is False
    assert aggregate.components == ()
