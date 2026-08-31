import pytest

from domains.anomalies.current_issue import OwnerSnapshot, RecheckScope, build_owner_lock_key
from subsystems.anomalies.government_subsidy_current_issue_consumer import (
    GovernmentSubsidyCurrentIssueConsumer,
)
from subsystems.government_subsidy.current_anomaly_facts import (
    GOVERNMENT_SUBSIDY_ANOMALY_OWNER_DOMAIN,
    GOVERNMENT_SUBSIDY_ANOMALY_OWNER_ROOT_TYPE,
    GovernmentSubsidyReceiptCurrentFact,
)


def _scope():
    return RecheckScope(
        GOVERNMENT_SUBSIDY_ANOMALY_OWNER_DOMAIN,
        GOVERNMENT_SUBSIDY_ANOMALY_OWNER_ROOT_TYPE,
        "GOVSUB-001",
        ("bank-1",),
        (build_owner_lock_key(GOVERNMENT_SUBSIDY_ANOMALY_OWNER_DOMAIN, GOVERNMENT_SUBSIDY_ANOMALY_OWNER_ROOT_TYPE, "bank:bank-1"),),
    )


def test_consumer_only_projects_owner_active_predicate() -> None:
    fact = GovernmentSubsidyReceiptCurrentFact(
        "bank-1", "snapshot-1", 3, True, False, False, False
    )
    snapshot = OwnerSnapshot(_scope(), "snapshot-1", 3, (fact,), True)
    issues = GovernmentSubsidyCurrentIssueConsumer(
        lambda code, identity: "issue-" + code
    ).detect(snapshot)
    assert len(issues) == 1
    assert issues[0].subject_identity == {"bank_fact_identity": "bank-1"}


def test_consumer_rejects_incomplete_owner_snapshot() -> None:
    fact = GovernmentSubsidyReceiptCurrentFact(
        "bank-1", "snapshot-1", 3, False, True, True, True
    )
    snapshot = OwnerSnapshot(_scope(), "snapshot-1", 3, (fact,), False)
    with pytest.raises(ValueError, match="incomplete"):
        GovernmentSubsidyCurrentIssueConsumer(
            lambda code, identity: "issue-" + code
        ).detect(snapshot)
