import pytest

from domains.anomalies.current_issue import OwnerSnapshot, RecheckScope, build_owner_lock_key
from subsystems.anomalies.government_subsidy_current_issue_consumer import (
    GovernmentSubsidyCurrentIssueConsumer,
)
from subsystems.government_subsidy.current_anomaly_facts import (
    GOVERNMENT_SUBSIDY_ANOMALY_OWNER_DOMAIN,
    GOVERNMENT_SUBSIDY_ANOMALY_OWNER_ROOT_TYPE,
    GovernmentSubsidyAllocationCurrentFact,
    GovernmentSubsidyReceiptCurrentFact,
    GovernmentSubsidyReversalCurrentFact,
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
        "bank-1", 11, "snapshot-1", 3, True, False, False, False
    )
    snapshot = OwnerSnapshot(_scope(), "snapshot-1", 3, (fact,), True)
    issues = GovernmentSubsidyCurrentIssueConsumer(
        lambda code, identity: "issue-" + code
    ).detect(snapshot)
    assert len(issues) == 1
    assert issues[0].subject_identity == {"bank_fact_identity": "bank-1"}
    action = issues[0].details["available_actions"][0]
    assert action["preview_operation"] == "PreviewGovernmentSubsidyReceipt"
    assert action["apply_operation"] == "ApplyGovernmentSubsidyReceipt"
    assert action["source_bindings"] == {
        "bank_fact_identity": "bank-1",
        "finance_import_row_id": 11,
        "source_version": 3,
    }


def test_consumer_rejects_incomplete_owner_snapshot() -> None:
    fact = GovernmentSubsidyReceiptCurrentFact(
        "bank-1", None, "snapshot-1", 3, False, True, True, True
    )
    snapshot = OwnerSnapshot(_scope(), "snapshot-1", 3, (fact,), False)
    with pytest.raises(ValueError, match="incomplete"):
        GovernmentSubsidyCurrentIssueConsumer(
            lambda code, identity: "issue-" + code
        ).detect(snapshot)


@pytest.mark.parametrize(
    ("code", "subject_id", "fact", "expected_bindings", "expected_apply"),
    (
        (
            "GOVSUB-002",
            "bank-1:5",
            GovernmentSubsidyAllocationCurrentFact(
                "bank-1", 5, 11, "snapshot-allocation", 4, True, False, True, True
            ),
            {
                "bank_fact_identity": "bank-1",
                "batch_id": 5,
                "finance_import_row_id": 11,
                "source_version": 4,
            },
            "ApplyGovernmentSubsidyReceipt",
        ),
        (
            "GOVSUB-004",
            "bank-out-1:91",
            GovernmentSubsidyReversalCurrentFact(
                "bank-out-1", 91, 12, "snapshot-reversal", 8, True, False, True, True, True
            ),
            {
                "finance_import_row_id": 12,
                "reversal_bank_fact_identity": "bank-out-1",
                "source_receipt_id": 91,
                "source_version": 8,
            },
            "ApplyGovernmentSubsidyReversal",
        ),
    ),
)
def test_consumer_binds_existing_receipt_and_reversal_actions(
    code,
    subject_id,
    fact,
    expected_bindings,
    expected_apply,
) -> None:
    scope = RecheckScope(
        GOVERNMENT_SUBSIDY_ANOMALY_OWNER_DOMAIN,
        GOVERNMENT_SUBSIDY_ANOMALY_OWNER_ROOT_TYPE,
        code,
        (subject_id,),
        (
            build_owner_lock_key(
                GOVERNMENT_SUBSIDY_ANOMALY_OWNER_DOMAIN,
                GOVERNMENT_SUBSIDY_ANOMALY_OWNER_ROOT_TYPE,
                subject_id,
            ),
        ),
    )
    candidate = GovernmentSubsidyCurrentIssueConsumer(
        lambda definition, _identity: "issue-" + definition
    ).detect(OwnerSnapshot(scope, "owner-snapshot", fact.owner_version, (fact,)))[0]

    action = candidate.details["available_actions"][0]
    assert action["source_bindings"] == expected_bindings
    assert action["apply_operation"] == expected_apply
