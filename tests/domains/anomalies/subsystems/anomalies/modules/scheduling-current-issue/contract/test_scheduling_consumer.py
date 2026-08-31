import pytest

from domains.anomalies.current_issue import OwnerSnapshot, RecheckScope, build_owner_lock_key
from subsystems.anomalies.scheduling_current_issue_consumer import SchedulingCurrentIssueConsumer
from subsystems.scheduling.current_anomaly_facts import SchedulingCoverageCurrentFact, SchedulingCurrentIssueCode


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


def test_consumer_omits_terminal_fact() -> None:
    fact = SchedulingCoverageCurrentFact("CASE-1", 2, "snapshot", 4, True, True, True, True, True, True, True)
    snapshot = OwnerSnapshot(_scope(), "snapshot", 4, (fact,), True)
    assert SchedulingCurrentIssueConsumer(_key).detect(snapshot) == ()


def test_consumer_rejects_incomplete_owner_snapshot() -> None:
    fact = SchedulingCoverageCurrentFact("CASE-1", 2, "snapshot", 4, False, True, True, True, True, True, True)
    snapshot = OwnerSnapshot(_scope(), "snapshot", 4, (fact,), False)
    with pytest.raises(ValueError, match="Scheduling owner facts are incomplete"):
        SchedulingCurrentIssueConsumer(_key).detect(snapshot)
