import pytest

from domains.anomalies.current_issue import OwnerSnapshot, RecheckScope, build_owner_lock_key
from subsystems.anomalies.case_pairing_current_issue_consumer import CasePairingCurrentIssueConsumer
from subsystems.case_import.pairing_current_facts import HcmCounterpartCurrentFact


def _scope():
    return RecheckScope(
        "case_import", "case_pairing_current_fact", "BECLASS-001", ("CASE-1",),
        (build_owner_lock_key("case_import", "case_pairing_current_fact", "case:CASE-1"),),
    )


def test_consumer_projects_only_owner_active_fact() -> None:
    fact = HcmCounterpartCurrentFact("CASE-1", "snapshot-1", 1, True, 0, False)
    issues = CasePairingCurrentIssueConsumer(lambda code, identity: "issue-" + code).detect(
        OwnerSnapshot(_scope(), "snapshot-1", 1, (fact,), True)
    )
    assert issues[0].subject_identity == {"case_no": "CASE-1"}
    action = issues[0].details["available_actions"][0]
    assert action["preview_operation"] == "PreviewClientBeClassWorkbook"
    assert action["apply_operation"] == "ApplyClientBeClassWorkbook"
    assert action["source_bindings"] == {"case_no": "CASE-1", "source_version": 1}


def test_consumer_never_deletes_from_incomplete_readback() -> None:
    fact = HcmCounterpartCurrentFact("CASE-1", "snapshot-1", 1, False, 1, True)
    with pytest.raises(ValueError, match="incomplete"):
        CasePairingCurrentIssueConsumer(lambda code, identity: "issue-" + code).detect(
            OwnerSnapshot(_scope(), "snapshot-1", 1, (fact,), False)
        )
