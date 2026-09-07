"""Focused tests for the Orders terminal aggregate."""

from datetime import datetime, timezone

import pytest

from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.orders.government_subsidy_projection_query import (
    OrderGovernmentSubsidyProjection,
)
from subsystems.orders.stage_projection_query import (
    OrderOperationalTimeline,
    ProjectionNotice,
    SettlementProjection,
    SopStepProjection,
    SourceLineage,
    StageProjection,
    _steps,
)
from subsystems.orders.terminal_aggregate_query import (
    TerminalAggregateContractError,
    project_terminal_aggregate,
)


_AT = datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc)
_SOP_COMPONENT_CODES = (
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
)
_SETTLEMENT_COMPONENT_CODES = (
    "service_completion",
    "client_settlement",
    "staff_payout",
)
_INDEPENDENT_GAP_CASES = (
    *((code, "sop", f"{code}_not_complete") for code in _SOP_COMPONENT_CODES if code != "matching_pool"),
    *((code, "settlement", f"{code}_not_complete") for code in _SETTLEMENT_COMPONENT_CODES),
    ("government_subsidy", "subsidy", "submitted"),
)


def _step(index: int, code: str, *, blocked: bool = False) -> SopStepProjection:
    owner = f"owner-{code}"
    return SopStepProjection(
        ordinal=index,
        code=code,
        label=code,
        owner=owner,
        status="blocked" if blocked else "completed",
        occurred_at=_AT,
        blockers=(
            ProjectionNotice(f"{code}_not_complete", f"{owner} 尚未完成。"),
        ) if blocked else (),
        warnings=(),
        available_actions=(),
        availability_reason=None,
    )


def _settlement_stage(*, blocked_code: str | None = None) -> StageProjection:
    parts = tuple(
        SettlementProjection(
            code=code,  # type: ignore[arg-type]
            status="blocked" if code == blocked_code else "completed",
            source=SourceLineage(f"owner-{code}", f"{code}:1", 1),
            occurred_at=_AT,
            availability_reason=None,
        )
        for code in _SETTLEMENT_COMPONENT_CODES
    )
    blockers = (
        ProjectionNotice(
            f"{blocked_code}_not_complete",
            f"owner-{blocked_code} 尚未完成。",
        ),
    ) if blocked_code is not None else ()
    return StageProjection(
        ordinal=7,
        code="settlement_payout",
        label="settlement_payout",
        owner="Orders / Client Finance / Staff Payables",
        status="blocked" if blocked_code is not None else "completed",
        source=SourceLineage("Cross-domain read coordinator", "settlement:1", 1),
        occurred_at=_AT,
        blockers=blockers,
        warnings=(),
        available_actions=(),
        availability_reason=None,
        settlement=parts,
    )


def _timeline(
    *,
    blocked_step_code: str | None = None,
    blocked_settlement_code: str | None = None,
    lifecycle_status: OrderLifecycleStatus = OrderLifecycleStatus.COMPLETED,
) -> OrderOperationalTimeline:
    stage_codes = (
        "intake_terms",
        "matching_willingness",
        "client_review",
        "contract_deposit",
        "date_confirmation",
        "active_service",
    )
    stages = tuple(
        StageProjection(
            ordinal=index,
            code=code,
            label=code,
            owner=f"owner-{code}",
            status="completed",
            source=SourceLineage(f"owner-{code}", f"{code}:1", 1),
            occurred_at=_AT,
            blockers=(),
            warnings=(),
            available_actions=(),
            availability_reason=None,
        )
        for index, code in enumerate(stage_codes, start=1)
    ) + (_settlement_stage(blocked_code=blocked_settlement_code),)
    steps = tuple(
        _step(index, code, blocked=code == blocked_step_code)
        for index, code in enumerate(_SOP_COMPONENT_CODES, start=1)
    ) + (_step(11, "settlement_close"),)
    return OrderOperationalTimeline(
        case_no="CASE-TERMINAL-001",
        base_revision=3,
        lifecycle_status=lifecycle_status,
        replacement_resume_step_ordinal=None,
        current_stage_code=None,
        current_step_ordinal=None,
        stages=stages,
        sop_steps=steps,
        projection_digest="a" * 64,
    )


def _matching_pool_cascade_timeline() -> OrderOperationalTimeline:
    """Build the matching-pool gap from current owner root-fact derivation."""
    baseline = _timeline()
    root_facts = {
        "matching_plan_id": 1,
        "candidate_pool_id": None,
        "candidate_pool_candidate_count": 0,
        "candidate_pool_contacted_count": 0,
        "candidate_pool_replied_count": 0,
        "candidate_pool_contacted_at": None,
        "candidate_pool_replied_at": None,
        "willingness_contact_attempt_count": 0,
        "willingness_count": 0,
        "willingness_replied_count": 0,
        "willingness_accepted_count": 0,
        "resume_attempt_count": 1,
        "resume_sent_count": 1,
        "matching_segment_count": 1,
        "staff_contract_sent_count": 1,
        "staff_contract_signed_count": 1,
        "client_contract_sent_count": 1,
        "client_contract_signed_count": 1,
        "deposit_obligation_count": 1,
        "deposit_open_count": 0,
        "matching_created_at": None,
        "staff_contract_signed_at": _AT,
        "staff_contract_sent_at": _AT,
        "client_contract_signed_at": _AT,
        "client_contract_sent_at": _AT,
        "deposit_updated_at": _AT,
    }
    steps = _steps(root_facts, baseline.case_no, baseline.stages)
    return OrderOperationalTimeline(
        case_no=baseline.case_no,
        base_revision=baseline.base_revision,
        lifecycle_status=baseline.lifecycle_status,
        replacement_resume_step_ordinal=baseline.replacement_resume_step_ordinal,
        current_stage_code=baseline.current_stage_code,
        current_step_ordinal=baseline.current_step_ordinal,
        stages=baseline.stages,
        sop_steps=steps,
        projection_digest=baseline.projection_digest,
    )


def _subsidy(substatus_code: str, *, case_no: str = "CASE-TERMINAL-001") -> OrderGovernmentSubsidyProjection:
    return OrderGovernmentSubsidyProjection(
        case_no=case_no,
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


def test_normal_order_is_fully_closed_only_when_all_owner_components_complete():
    aggregate = project_terminal_aggregate(_timeline(), _subsidy("paid"))

    assert aggregate.applicable is True
    assert aggregate.fully_closed is True
    assert tuple(component.code for component in aggregate.components) == (
        *_SOP_COMPONENT_CODES,
        *_SETTLEMENT_COMPONENT_CODES,
        "government_subsidy",
    )
    assert len(aggregate.components) == 14
    assert all(component.completed for component in aggregate.components)


@pytest.mark.parametrize(
    ("component_code", "gap_kind", "expected_reason"),
    _INDEPENDENT_GAP_CASES,
)
def test_legal_independent_owner_gap_matrix_keeps_terminal_aggregate_open(
    component_code,
    gap_kind,
    expected_reason,
):
    timeline = _timeline(
        blocked_step_code=component_code if gap_kind == "sop" else None,
        blocked_settlement_code=component_code if gap_kind == "settlement" else None,
    )
    subsidy = _subsidy("submitted" if gap_kind == "subsidy" else "paid")

    aggregate = project_terminal_aggregate(timeline, subsidy)

    incomplete = tuple(item for item in aggregate.components if not item.completed)
    assert aggregate.applicable is True
    assert aggregate.fully_closed is False
    assert len(aggregate.components) == 14
    assert len(incomplete) == 1
    component = incomplete[0]
    assert component.code == component_code
    assert component.reason == expected_reason
    if gap_kind == "sop":
        source = next(item for item in timeline.sop_steps if item.code == component_code)
        assert component.owner == source.owner
    elif gap_kind == "settlement":
        settlement = next(stage for stage in timeline.stages if stage.code == "settlement_payout")
        source = next(item for item in settlement.settlement if item.code == component_code)
        assert component.owner == source.source.owner
    else:
        assert component.owner == subsidy.source.owner


def test_matching_pool_gap_uses_current_owner_cascade_instead_of_contradictory_state():
    aggregate = project_terminal_aggregate(
        _matching_pool_cascade_timeline(),
        _subsidy("paid"),
    )

    incomplete = tuple(
        (item.code, item.owner, item.reason)
        for item in aggregate.components
        if not item.completed
    )
    assert aggregate.fully_closed is False
    assert incomplete == (
        (
            "matching_pool",
            "Assignments / Scheduling",
            "matching_plan_lineage_missing",
        ),
        (
            "caregiver_line_delivery",
            "Assignments / LINE Delivery",
            "candidate_contact_pool_missing",
        ),
        (
            "caregiver_willingness_reply",
            "Assignments / LINE",
            "candidate_contact_pool_missing",
        ),
    )


@pytest.mark.parametrize(
    "lifecycle_status",
    [
        OrderLifecycleStatus.CANCELLED,
        OrderLifecycleStatus.HISTORICAL_UNSERVED,
        OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
    ],
)
def test_non_normal_order_is_classified_outside_terminal_aggregate(lifecycle_status):
    aggregate = project_terminal_aggregate(
        _timeline(lifecycle_status=lifecycle_status),
        _subsidy("paid"),
    )

    assert aggregate.applicable is False
    assert aggregate.fully_closed is False
    assert aggregate.components == ()


def test_terminal_aggregate_rejects_cross_order_owner_facts():
    with pytest.raises(TerminalAggregateContractError):
        project_terminal_aggregate(_timeline(), _subsidy("paid", case_no="CASE-OTHER"))
