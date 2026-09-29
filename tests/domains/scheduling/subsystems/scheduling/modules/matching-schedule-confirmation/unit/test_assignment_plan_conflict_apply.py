from dataclasses import replace
from datetime import date
import pytest
from domains.scheduling.assignment_plan import StaffOccupancyFact
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.scheduling.assignment_plan_workflow import (
    AssignmentPlanWorkflow, AssignmentPlanPreviewRequest, AssignmentPlanApplyRequest,
    AssignmentPlanApplyEvidence, AssignmentPlanWorkflowError, CommandClaimState,
)
from tests.test_assignment_plan_workflow import _ports, _ReplayRepository, _facts, _intent, _UnitOfWork


def test_actual_conflict_appearing_after_preview_rejects_apply_without_commit():
    client, payroll, orders = _ports()
    repository = _ReplayRepository(_facts(), None)
    repository.load_for_apply = lambda *_args: AssignmentPlanApplyEvidence(repository.facts, CommandClaimState.CREATED, None)
    unit_of_work = _UnitOfWork()
    workflow = AssignmentPlanWorkflow(repository, client, payroll, orders, lambda: unit_of_work)
    preview = workflow.preview(AssignmentPlanPreviewRequest("CASE-1", _intent(), CorrelationId("preview")))
    repository.facts = replace(repository.facts, assignment_plan=replace(
        repository.facts.assignment_plan,
        external_occupancy=(StaffOccupancyFact(1, date(2026, 8, 3), "OTHER-CASE"),),
    ))
    request = AssignmentPlanApplyRequest(
        "CASE-1", _intent(), ExpectedVersion(3), ExpectedVersion(4), ExpectedVersion(5), ExpectedVersion(6),
        preview.fingerprint, IdempotencyKey("actual-conflict"), ActorContext("admin"), "confirm", CorrelationId("apply"),
    )
    with pytest.raises(AssignmentPlanWorkflowError) as error:
        workflow.apply(request)
    assert error.value.error.code == "staff_occupancy_conflict"
    assert unit_of_work.committed is False


def test_proposed_buffer_overlapping_other_actual_service_does_not_block_preview():
    client, payroll, orders = _ports()
    facts = _facts()
    facts = replace(facts, assignment_plan=replace(facts.assignment_plan,
        external_occupancy=(StaffOccupancyFact(1, date(2026, 8, 4), "OTHER-CASE"),)))
    workflow = AssignmentPlanWorkflow(_ReplayRepository(facts, None), client, payroll, orders, _UnitOfWork)
    preview = workflow.preview(AssignmentPlanPreviewRequest("CASE-1", _intent(), CorrelationId("buffer-preview")))
    assert preview.candidate.scheduling.buffers[0].active is True
