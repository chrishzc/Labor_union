"""Cross-Domain candidates for an Assignment Plan replacement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from domains.client_finance.obligation_planning import build_client_finance_terms_impact
from domains.orders.lifecycle import build_terms_lifecycle_impact
from domains.scheduling.generation import SchedulingGenerationCandidate
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from subsystems.payroll.terms_impact import build_payroll_cancellation_impact
from subsystems.scheduling.assignment_plan_workflow import (
    AssignmentPlanWorkflowFacts,
    VersionedImpactCandidate,
)


@dataclass(frozen=True, slots=True)
class AssignmentPlanDomainImpact(VersionedImpactCandidate):
    expected_version: int
    resulting_version: int
    fingerprint: PreviewFingerprint
    blockers: tuple[str, ...]
    payload: Any


@dataclass(frozen=True, slots=True)
class OrdersAssignmentImpactPayload:
    lifecycle: Any
    client_settlement_fingerprint: PreviewFingerprint


def build_client_finance_assignment_impact(
    facts: AssignmentPlanWorkflowFacts,
    scheduling: SchedulingGenerationCandidate,
) -> AssignmentPlanDomainImpact:
    candidate = build_client_finance_terms_impact(
        facts.client_finance,
        facts.order_terms,
        scheduling,
        _change_identity(scheduling),
    )
    return AssignmentPlanDomainImpact(
        candidate.expected_account_version,
        candidate.resulting_account_version,
        candidate.fingerprint,
        candidate.blockers,
        candidate,
    )


def build_payroll_assignment_impact(
    facts: AssignmentPlanWorkflowFacts,
    scheduling: SchedulingGenerationCandidate,
) -> AssignmentPlanDomainImpact:
    candidate = build_payroll_cancellation_impact(
        facts.payroll,
        scheduling,
        facts.order_terms,
        _change_identity(scheduling),
    )
    return AssignmentPlanDomainImpact(
        candidate.expected_payroll_version,
        candidate.resulting_payroll_version,
        candidate.fingerprint,
        candidate.blockers,
        candidate,
    )


def build_orders_assignment_impact(
    facts: AssignmentPlanWorkflowFacts,
    scheduling: SchedulingGenerationCandidate,
    client_finance: VersionedImpactCandidate,
    evaluation_at: datetime,
) -> AssignmentPlanDomainImpact:
    settlement = client_finance.payload.settlement
    blockers = _assignment_plan_readiness_blockers(facts, settlement)
    lifecycle = _build_lifecycle_candidate(
        facts,
        scheduling,
        settlement,
        evaluation_at,
        blockers,
    )
    fingerprint = fingerprint_payload(
        {
            "lifecycle": None if lifecycle is None else lifecycle.fingerprint.value,
            "waiting_lock_ids": facts.assignment_plan.current_waiting_lock_ids,
            "waiting_lock_conversion_blockers": blockers,
        }
    )
    version = facts.assignment_plan.order_version
    return AssignmentPlanDomainImpact(
        version,
        version + 1,
        fingerprint,
        blockers,
        OrdersAssignmentImpactPayload(
            lifecycle,
            client_finance.payload.settlement.fingerprint,
        ),
    )


def _build_lifecycle_candidate(
    facts: AssignmentPlanWorkflowFacts,
    scheduling: SchedulingGenerationCandidate,
    settlement: Any,
    evaluation_at: datetime,
    blockers: tuple[str, ...],
) -> Any:
    if "waiting_lock_conversion.service_time_required" in blockers:
        return None
    return build_terms_lifecycle_impact(
        facts.lifecycle,
        facts.order_terms,
        scheduling,
        settlement,
        evaluation_at,
    )


def _assignment_plan_readiness_blockers(
    facts: AssignmentPlanWorkflowFacts,
    settlement: Any,
) -> tuple[str, ...]:
    waiting_lock_ids = facts.assignment_plan.current_waiting_lock_ids
    first_assignment = not facts.assignment_plan.effective_assignments
    if not first_assignment and not waiting_lock_ids:
        return ()
    if first_assignment and not waiting_lock_ids:
        return ("assignment_plan_bootstrap.waiting_lock_required",)
    blockers: list[str] = []
    if not facts.lifecycle.contract_completed:
        blockers.append("waiting_lock_conversion.contract_required")
    if not facts.order_terms.service_time.complete:
        blockers.append("waiting_lock_conversion.service_time_required")
    if not settlement.deposit_settled:
        blockers.append("waiting_lock_conversion.deposit_required")
    return tuple(blockers)


def _change_identity(scheduling: SchedulingGenerationCandidate) -> str:
    return f"assignment-plan:{scheduling.case_no}:generation:{scheduling.generation_number}"
