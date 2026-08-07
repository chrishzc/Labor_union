from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from subsystems.scheduling.assignment_plan_impacts import (
    _assignment_plan_readiness_blockers,
)
from subsystems.scheduling.assignment_plan_workflow import AssignmentPlanWorkflowFacts


def _facts(*, assignments=(), waiting_lock_ids=(), completed=True, service_complete=True):
    return AssignmentPlanWorkflowFacts(
        SimpleNamespace(
            effective_assignments=assignments,
            current_waiting_lock_ids=waiting_lock_ids,
        ),
        SimpleNamespace(service_time=SimpleNamespace(complete=service_complete)),
        object(),
        object(),
        SimpleNamespace(contract_completed=completed),
    )


def test_assignment_plan_impacts_is_readable_source_without_bytecode_bridge():
    source = Path("subsystems/scheduling/assignment_plan_impacts.py").read_text(encoding="utf-8")
    assert "load_preserved_module" not in source
    assert "_bytecode_bridge" not in source


def test_existing_assignment_without_waiting_lock_has_no_conversion_blocker():
    blockers = _assignment_plan_readiness_blockers(
        _facts(assignments=(object(),)),
        SimpleNamespace(deposit_settled=False),
    )

    assert blockers == ()


def test_first_assignment_requires_waiting_lock_before_domain_impacts():
    blockers = _assignment_plan_readiness_blockers(
        _facts(),
        SimpleNamespace(deposit_settled=True),
    )

    assert blockers == ("assignment_plan_bootstrap.waiting_lock_required",)


def test_waiting_lock_conversion_reports_each_missing_business_root():
    blockers = _assignment_plan_readiness_blockers(
        _facts(waiting_lock_ids=(8,), completed=False, service_complete=False),
        SimpleNamespace(deposit_settled=False),
    )

    assert blockers == (
        "waiting_lock_conversion.contract_required",
        "waiting_lock_conversion.service_time_required",
        "waiting_lock_conversion.deposit_required",
    )
