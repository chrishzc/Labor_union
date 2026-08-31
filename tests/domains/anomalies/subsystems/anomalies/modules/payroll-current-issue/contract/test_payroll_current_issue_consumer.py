from domains.anomalies.current_issue import OwnerSnapshot, RecheckScope
from subsystems.anomalies.payroll_current_issue_consumer import PayrollCurrentIssueConsumer
from subsystems.payroll.current_anomaly_facts import (
    PAYROLL_ANOMALY_OWNER_DOMAIN,
    PAYROLL_ANOMALY_OWNER_ROOT_TYPE,
    PAYOUT_002_SUBJECT_TYPE,
    PayrollLateObligationCurrentFact,
)


def test_payout002_consumer_uses_payroll_typed_readback_and_closed_identity():
    fact = PayrollLateObligationCurrentFact(
        "obligation:1", "staff-obligation-event:7", "snapshot:1", 4, 1000, 1200, True
    )
    subject = "obligation:1:staff-obligation-event:7"
    scope = RecheckScope(
        PAYROLL_ANOMALY_OWNER_DOMAIN, PAYROLL_ANOMALY_OWNER_ROOT_TYPE,
        PAYOUT_002_SUBJECT_TYPE, (subject,), ("payroll:payroll_obligation:obligation:1",),
    )
    candidate = PayrollCurrentIssueConsumer(
        lambda code, identity: code + ":" + identity["obligation_identity"]
    ).detect(OwnerSnapshot(scope, "snapshot:1", 4, (fact,)))[0]

    assert candidate.definition_code == "PAYOUT-002"
    assert candidate.owner_domain == "payroll"
    assert candidate.subject_identity == {
        "obligation_identity": "obligation:1",
        "source_event_identity": "staff-obligation-event:7",
    }
    assert candidate.details["delta_amount_ntd"] == 200


def test_payout002_consumer_fails_closed_on_incomplete_owner_readback():
    fact = PayrollLateObligationCurrentFact(
        "obligation:1", "staff-obligation-event:7", "snapshot:1", 4, 1000, 1200, True,
        authoritative_complete=False,
    )
    scope = RecheckScope(
        PAYROLL_ANOMALY_OWNER_DOMAIN, PAYROLL_ANOMALY_OWNER_ROOT_TYPE,
        PAYOUT_002_SUBJECT_TYPE, ("obligation:1:staff-obligation-event:7",),
        ("payroll:payroll_obligation:obligation:1",),
    )
    consumer = PayrollCurrentIssueConsumer(lambda code, identity: "key")
    import pytest

    with pytest.raises(ValueError, match="incomplete"):
        consumer.detect(OwnerSnapshot(scope, "snapshot:1", 4, (fact,)))
