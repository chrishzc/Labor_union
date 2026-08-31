from types import SimpleNamespace

from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.scheduling.assignment_plan_workflow import (
    AssignmentPlanApplyRequest,
    AssignmentPlanReceipt,
    AssignmentPlanWorkflow,
)


class _Repository:
    def replace_scheduling_generation(self, *_):
        return SimpleNamespace(
            assignment_resolution=SimpleNamespace(
                assignment_id_by_candidate_key={}
            )
        )

    def save_receipt(self, *_):
        return None


class _Port:
    def persist_assignment_plan(self, *_):
        return None


class _Sink:
    def __init__(self):
        self.intents = []

    def append_scheduling_recheck(self, request):
        self.intents.append(request)

    def append_scheduling_overlap_rechecks(self, request):
        self.intents.append(request)


def test_assignment_plan_persists_exact_coverage_recheck_in_owner_transaction() -> None:
    fingerprint = fingerprint_payload({"preview": "assignment-plan"})
    request = AssignmentPlanApplyRequest(
        "CASE-1",
        SimpleNamespace(),
        ExpectedVersion(1),
        ExpectedVersion(2),
        ExpectedVersion(3),
        ExpectedVersion(4),
        fingerprint,
        IdempotencyKey("assignment-plan-current-anomaly-1"),
        ActorContext("admin"),
        "repair coverage",
        CorrelationId("assignment-plan-current-anomaly-1"),
    )
    receipt = AssignmentPlanReceipt("CASE-1", 2, 5, 3, 4, 5, (), ("new:1",), fingerprint)
    preview = SimpleNamespace(
        fingerprint=fingerprint,
        order_version=1,
        candidate=SimpleNamespace(
            waiting_lock_ids=(), scheduling=SimpleNamespace(assignments=())
        ),
        client_finance_impact=object(),
        payroll_impact=object(),
        orders_impact=object(),
    )
    sink = _Sink()
    workflow = AssignmentPlanWorkflow(_Repository(), _Port(), _Port(), _Port(), lambda: None, sink)

    workflow._persist(request, preview, fingerprint, receipt)

    assert len(sink.intents) == 1
    request = sink.intents[0]
    assert request.definition_code.value == "SCHEDULE-006"
    assert request.subject_ids == ("CASE-1:5",)
    assert request.owner_version == 3
