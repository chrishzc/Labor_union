from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from domains.scheduling.assignment_plan import (
    AssignmentPlanFacts,
    AssignmentPlanIntent,
    AssignmentPlanSegmentIntent,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.scheduling.assignment_plan_workflow import (
    AssignmentPlanApplyEvidence,
    AssignmentPlanApplyRequest,
    AssignmentPlanPreviewRequest,
    AssignmentPlanReceipt,
    AssignmentPlanWorkflow,
    AssignmentPlanWorkflowFacts,
    CommandClaimState,
    StoredAssignmentPlanReceipt,
    _command_fingerprint,
)


@dataclass(frozen=True)
class _Impact:
    expected_version: int
    resulting_version: int
    fingerprint: object
    blockers: tuple[str, ...] = ()


class _PreviewPort:
    def __init__(self, impact: _Impact) -> None:
        self.impact = impact
        self.preview_calls = 0

    def preview_assignment_plan(self, *_args):
        self.preview_calls += 1
        return self.impact

    def persist_assignment_plan(self, *_args):
        raise AssertionError("replay must not persist")


class _ReplayRepository:
    def __init__(self, facts, stored) -> None:
        self.facts = facts
        self.stored = stored

    def load_for_query(self, case_no):
        return self.facts

    def load_for_preview(self, case_no, intent):
        return self.facts

    def preflight_impacted_staff_ids(self, case_no, intent):
        return (1,)

    def load_for_apply(self, request, preflight, fingerprint):
        return AssignmentPlanApplyEvidence(self.facts, CommandClaimState.MATCHED, self.stored)


class _UnitOfWork:
    def __init__(self) -> None:
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        self.committed = True


def _facts() -> AssignmentPlanWorkflowFacts:
    assignment = AssignmentPlanFacts(
        "CASE-1", 3, 4, 2, 5, 6, 1, 8, False
    )
    return AssignmentPlanWorkflowFacts(assignment, object(), object(), object(), object())


def _intent() -> AssignmentPlanIntent:
    service_date = date(2026, 8, 3)
    return AssignmentPlanIntent(
        (AssignmentPlanSegmentIntent(1, service_date, service_date, (service_date,)),)
    )


def _ports():
    return tuple(
        _PreviewPort(_Impact(version, version + 1, fingerprint_payload({"port": name})))
        for name, version in (("client", 5), ("payroll", 6), ("orders", 3))
    )


def test_assignment_plan_workflow_is_readable_source_without_bytecode_bridge():
    source = Path("subsystems/scheduling/assignment_plan_workflow.py").read_text(encoding="utf-8")
    assert "load_preserved_module" not in source
    assert "_bytecode_bridge" not in source


def test_preview_combines_domain_and_downstream_fingerprints():
    client, payroll, orders = _ports()
    workflow = AssignmentPlanWorkflow(_ReplayRepository(_facts(), None), client, payroll, orders, _UnitOfWork)

    preview = workflow.preview(AssignmentPlanPreviewRequest("CASE-1", _intent(), CorrelationId("preview-1")))

    assert preview.order_version == 3
    assert preview.candidate.scheduling.case_no == "CASE-1"
    assert len(preview.fingerprint.value) == 64
    assert (client.preview_calls, payroll.preview_calls, orders.preview_calls) == (1, 1, 1)


def test_apply_returns_matching_idempotent_receipt_without_repersisting():
    receipt = AssignmentPlanReceipt("CASE-1", 4, 3, 5, 6, 7, (), ("assignment:1",), fingerprint_payload({"preview": 1}))
    request = AssignmentPlanApplyRequest(
        "CASE-1", _intent(), ExpectedVersion(3), ExpectedVersion(4), ExpectedVersion(5), ExpectedVersion(6), receipt.preview_fingerprint,
        IdempotencyKey("assignment-plan-replay-1"), ActorContext("admin"), "replay", CorrelationId("apply-1"),
    )
    stored = StoredAssignmentPlanReceipt(_command_fingerprint(request), receipt)
    client, payroll, orders = _ports()
    repository = _ReplayRepository(_facts(), stored)
    unit_of_work = _UnitOfWork()
    workflow = AssignmentPlanWorkflow(repository, client, payroll, orders, lambda: unit_of_work)

    result = workflow.apply(request)

    assert result == receipt
    assert unit_of_work.committed is True
