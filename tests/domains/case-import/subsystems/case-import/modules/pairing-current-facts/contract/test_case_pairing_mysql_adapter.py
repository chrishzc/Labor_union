from domains.anomalies.current_issue import RecheckScope, build_owner_lock_key
from infrastructure.mysql.case_pairing_current_issue_adapter import (
    MySqlCasePairingCurrentIssueAdapter,
)


class _Cursor:
    def __init__(self, responses):
        self.responses = responses
        self.current = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, *_):
        self.current = self.responses.pop(0)

    def fetchone(self):
        return self.current


class _Connection:
    def __init__(self, responses):
        self.responses = list(responses)

    def cursor(self):
        return _Cursor(self.responses)


def _scope(code, subject, root):
    return RecheckScope(
        "case_import", "case_pairing_current_fact", code, (subject,),
        (build_owner_lock_key("case_import", "case_pairing_current_fact", root),),
    )


def test_hcm_readback_uses_exact_bound_case_mapping() -> None:
    row = {"hcm_count": 1, "beclass_count": 1, "consistent_mapping_count": 1, "owner_version": 4}
    snapshot = MySqlCasePairingCurrentIssueAdapter(_Connection([row])).read_owner_snapshot(
        _scope("BECLASS-001", "CASE-1", "case:CASE-1")
    )
    assert snapshot.authoritative_complete is True
    assert snapshot.facts[0].predicate_active is False


def test_synthetic_beclass_counterpart_closes_only_with_bound_hcm() -> None:
    row = {"id": 7, "bound_case_no": "CASE-1", "hcm_count": 1, "owner_version": 7}
    snapshot = MySqlCasePairingCurrentIssueAdapter(_Connection([row])).read_owner_snapshot(
        _scope("IMPORT-003", "client_counterpart:counterpart:source-1", "review:counterpart:source-1")
    )
    assert snapshot.facts[0].accepted_mapping_consistent is True
    assert snapshot.facts[0].predicate_active is False


def test_review_lineage_requires_exact_accepted_source_receipt() -> None:
    review = {"id": 11, "source_event_identity": "beclass-workbook:" + "a" * 64 + ":row:3", "issue_codes": '["identity_conflict"]', "owner_version": 11}
    accepted = {"id": 17, "bound_case_no": "CASE-1", "hcm_count": 1}
    snapshot = MySqlCasePairingCurrentIssueAdapter(_Connection([review, accepted])).read_owner_snapshot(
        _scope("IMPORT-003", "client:beclass-review:abc", "review:beclass-review:abc")
    )
    assert snapshot.facts[0].accepted_mapping_consistent is True
    assert snapshot.facts[0].predicate_active is False
