from types import SimpleNamespace

from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.scheduling.assignment_plan_workflow import (
    AssignmentPlanApplyRequest,
    AssignmentPlanReceipt,
    AssignmentPlanWorkflow,
)
from subsystems.scheduling.leave_substitution_workflow import LeaveSubstitutionWorkflow


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

    def persist_leave_substitution(self, *_):
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


def test_assignment_plan_persists_overlap_replacement_and_coverage_rechecks() -> None:
    class Repository(_Repository):
        def replace_scheduling_generation(self, *_):
            return SimpleNamespace(
                assignment_resolution=SimpleNamespace(
                    assignment_id_by_candidate_key={"new:1": 12}
                )
            )

    fingerprint = fingerprint_payload({"preview": "assignment-plan-all-rechecks"})
    request = AssignmentPlanApplyRequest(
        "CASE-1",
        SimpleNamespace(),
        ExpectedVersion(1),
        ExpectedVersion(2),
        ExpectedVersion(3),
        ExpectedVersion(4),
        fingerprint,
        IdempotencyKey("assignment-plan-current-anomaly-all"),
        ActorContext("admin"),
        "repair assignment facts",
        CorrelationId("assignment-plan-current-anomaly-all"),
    )
    receipt = AssignmentPlanReceipt(
        "CASE-1", 2, 5, 3, 4, 5, (9,), ("new:1",), fingerprint
    )
    preview = SimpleNamespace(
        fingerprint=fingerprint,
        order_version=1,
        candidate=SimpleNamespace(
            waiting_lock_ids=(),
            scheduling=SimpleNamespace(
                assignments=(SimpleNamespace(staff_id=7),)
            ),
        ),
        client_finance_impact=object(),
        payroll_impact=object(),
        orders_impact=object(),
    )
    sink = _Sink()
    workflow = AssignmentPlanWorkflow(
        Repository(), _Port(), _Port(), _Port(), lambda: None, sink
    )

    workflow._persist(request, preview, fingerprint, receipt)

    assert [item.__class__.__name__ for item in sink.intents] == [
        "SchedulingOverlapRecheckRequest",
        "SchedulingAnomalyRecheckRequest",
        "SchedulingAnomalyRecheckRequest",
    ]
    assert sink.intents[0].affected_assignment_ids == (9, 12)
    assert sink.intents[1].definition_code.value == "SCHEDULE-002"
    assert sink.intents[1].subject_ids == ("9",)
    assert sink.intents[2].definition_code.value == "SCHEDULE-006"


def test_leave_substitution_persists_all_scheduling_rechecks_before_commit() -> None:
    class Repository:
        def replace_scheduling_generation(self, *_):
            return SimpleNamespace(
                assignment_resolution=SimpleNamespace(
                    assignment_id_by_candidate_key={"replacement": 12}
                )
            )

        def append_batch_outcomes(self, *_):
            return (101,)

        def save_receipt(self, *_):
            return None

    fingerprint = fingerprint_payload({"preview": "leave-substitution-rechecks"})
    request = SimpleNamespace(
        case_no="CASE-1",
        intent=SimpleNamespace(original_assignment_id=9),
        idempotency_key=IdempotencyKey("leave-substitution-rechecks"),
        actor=ActorContext("admin"),
        reason="replace started service",
        correlation_id=CorrelationId("leave-substitution-rechecks"),
    )
    preview = SimpleNamespace(
        fingerprint=fingerprint,
        order_version=1,
        candidate=SimpleNamespace(
            scheduling=SimpleNamespace(
                generation_number=5,
                resulting_aggregate_version=3,
                assignments=(SimpleNamespace(staff_id=7),),
            )
        ),
        client_finance_impact=SimpleNamespace(resulting_version=4),
        payroll_impact=SimpleNamespace(resulting_version=5),
        orders_impact=SimpleNamespace(resulting_version=2),
    )
    sink = _Sink()
    workflow = LeaveSubstitutionWorkflow(
        Repository(),
        _Port(),
        _Port(),
        _Port(),
        SimpleNamespace(),
        lambda: None,
        anomaly_rechecks=sink,
    )

    workflow._persist(request, preview, fingerprint, None)

    assert [item.__class__.__name__ for item in sink.intents] == [
        "SchedulingOverlapRecheckRequest",
        "SchedulingAnomalyRecheckRequest",
        "SchedulingAnomalyRecheckRequest",
    ]
    assert sink.intents[0].affected_assignment_ids == (9, 12)
    assert sink.intents[1].definition_code.value == "SCHEDULE-002"
    assert sink.intents[2].definition_code.value == "SCHEDULE-006"
