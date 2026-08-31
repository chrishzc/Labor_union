import pytest

from domains.anomalies.current_issue import OwnerSnapshot, RecheckScope, build_owner_lock_key
from subsystems.anomalies.scheduling_current_issue_consumer import SchedulingCurrentIssueConsumer
from subsystems.scheduling.current_anomaly_facts import (
    SchedulingCoverageCurrentFact,
    SchedulingCurrentIssueCode,
    SchedulingOverlapCurrentFact,
    SchedulingReplacementCurrentFact,
)


def _key(code, identity):
    return code + ":" + ":".join(identity.values())


def _scope():
    return RecheckScope(
        "scheduling",
        "scheduling_current_fact",
        SchedulingCurrentIssueCode.COVERAGE_INVALID.value,
        ("CASE-1:2",),
        (build_owner_lock_key("scheduling", "scheduling_current_fact", "case:CASE-1"),),
    )


def test_consumer_projects_only_owner_active_fact() -> None:
    fact = SchedulingCoverageCurrentFact("CASE-1", 2, "snapshot", 4, True, True, True, False, True, True, True)
    snapshot = OwnerSnapshot(_scope(), "snapshot", 4, (fact,), True)
    candidates = SchedulingCurrentIssueConsumer(_key).detect(snapshot)
    assert len(candidates) == 1
    assert candidates[0].definition_code == "SCHEDULE-006"
    assert candidates[0].subject_identity == {"case_no": "CASE-1", "generation": "2"}
    action = candidates[0].details["available_actions"][0]
    assert action == {
        "action_key": "rebuild_assignment_plan",
        "owning_domain": "scheduling",
        "preview_operation": "PreviewAssignmentPlan",
        "requires_preview": True,
        "label": "重建正式人力配置",
        "form_schema_key": "scheduling.assignment_plan.v1",
        "source_binding_keys": ("case_no", "source_version"),
        "source_bindings": {"case_no": "CASE-1", "source_version": 4},
        "required_operator_inputs": ("reason", "segments"),
        "apply_operation": "ApplyAssignmentPlan",
        "required_capability": None,
        "completion_predicate": "scheduling_effective_generation_complete",
        "action_contract_version": 1,
    }


def test_consumer_omits_terminal_fact() -> None:
    fact = SchedulingCoverageCurrentFact("CASE-1", 2, "snapshot", 4, True, True, True, True, True, True, True)
    snapshot = OwnerSnapshot(_scope(), "snapshot", 4, (fact,), True)
    assert SchedulingCurrentIssueConsumer(_key).detect(snapshot) == ()


def test_overlap_consumer_binds_existing_assignment_plan_action() -> None:
    scope = RecheckScope(
        "scheduling",
        "scheduling_current_fact",
        SchedulingCurrentIssueCode.ASSIGNMENT_OVERLAP.value,
        ("7:9",),
        tuple(
            sorted(
                (
                    build_owner_lock_key("scheduling", "scheduling_current_fact", "assignment:7"),
                    build_owner_lock_key("scheduling", "scheduling_current_fact", "assignment:9"),
                )
            )
        ),
    )
    fact = SchedulingOverlapCurrentFact(
        7,
        9,
        "CASE-7",
        "CASE-9",
        "snapshot-overlap",
        6,
        True,
        True,
    )
    candidate = SchedulingCurrentIssueConsumer(_key).detect(
        OwnerSnapshot(scope, "snapshot-overlap", 6, (fact,), True)
    )[0]

    action = candidate.details["available_actions"][0]
    assert action["preview_operation"] == "PreviewAssignmentPlan"
    assert action["apply_operation"] == "ApplyAssignmentPlan"
    assert action["source_bindings"] == {
        "assignment_id_a": 7,
        "assignment_id_b": 9,
        "case_no_a": "CASE-7",
        "case_no_b": "CASE-9",
        "source_version": 6,
    }
    assert action["required_operator_inputs"] == (
        "correction_case_no",
        "reason",
        "segments",
    )


@pytest.mark.parametrize(
    ("service_started", "action_key", "preview_operation", "apply_operation"),
    (
        (
            False,
            "rebuild_replacement_assignment_plan",
            "PreviewAssignmentPlan",
            "ApplyAssignmentPlan",
        ),
        (
            True,
            "complete_replacement_leave_substitution",
            "PreviewLeaveSubstitutionBatch",
            "ApplyLeaveSubstitutionBatch",
        ),
    ),
)
def test_replacement_consumer_selects_existing_owner_operation(
    service_started,
    action_key,
    preview_operation,
    apply_operation,
) -> None:
    scope = RecheckScope(
        "scheduling",
        "scheduling_current_fact",
        SchedulingCurrentIssueCode.REPLACEMENT_INCOMPLETE.value,
        ("7",),
        (build_owner_lock_key("scheduling", "scheduling_current_fact", "assignment:7"),),
    )
    fact = SchedulingReplacementCurrentFact(
        7,
        "CASE-7",
        service_started,
        "snapshot-replacement",
        8,
        True,
        False,
        False,
        False,
        False,
        False,
    )
    candidate = SchedulingCurrentIssueConsumer(_key).detect(
        OwnerSnapshot(scope, "snapshot-replacement", 8, (fact,), True)
    )[0]

    action = candidate.details["available_actions"][0]
    assert action["action_key"] == action_key
    assert action["preview_operation"] == preview_operation
    assert action["apply_operation"] == apply_operation
    assert action["source_bindings"] == {
        "assignment_id": 7,
        "case_no": "CASE-7",
        "source_version": 8,
    }


def test_consumer_rejects_incomplete_owner_snapshot() -> None:
    fact = SchedulingCoverageCurrentFact("CASE-1", 2, "snapshot", 4, False, True, True, True, True, True, True)
    snapshot = OwnerSnapshot(_scope(), "snapshot", 4, (fact,), False)
    with pytest.raises(ValueError, match="Scheduling owner facts are incomplete"):
        SchedulingCurrentIssueConsumer(_key).detect(snapshot)
