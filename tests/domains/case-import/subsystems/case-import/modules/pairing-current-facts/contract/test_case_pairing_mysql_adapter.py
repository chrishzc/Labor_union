from domains.anomalies.current_issue import RecheckScope, build_owner_lock_key
from infrastructure.mysql.case_pairing_current_issue_adapter import (
    MySqlCasePairingCurrentIssueAdapter,
)
from subsystems.case_import.pairing_current_facts import (
    CasePairingAcceptedMapping,
    CasePairingAcceptedLineage,
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
    snapshot = MySqlCasePairingCurrentIssueAdapter(_Connection([review])).read_owner_snapshot(
        _scope("IMPORT-003", "client:beclass-review:abc", "review:beclass-review:abc")
    )
    assert snapshot.facts[0].accepted_mapping_consistent is False
    assert snapshot.facts[0].predicate_active is True


class _ExactLineageReader:
    def __init__(self, mapping):
        self.mapping = mapping
        self.identities = []

    def read_accepted_mapping(self, review_identity):
        self.identities.append(review_identity)
        return self.mapping


def test_review_lineage_closes_only_with_explicit_cross_source_identity() -> None:
    review = {
        "id": 11,
        "source_event_identity": "beclass-workbook:" + "a" * 64 + ":row:3",
        "issue_codes": '["identity_conflict"]',
        "owner_version": 11,
    }
    lineage = CasePairingAcceptedLineage(
        "beclass-review:abc",
        "beclass-workbook:" + "b" * 64 + ":row:4",
        "client-beclass-apply-event:17",
    )
    reader = _ExactLineageReader(CasePairingAcceptedMapping(lineage, "CASE-1", 1))
    snapshot = MySqlCasePairingCurrentIssueAdapter(
        _Connection([review]), reader
    ).read_owner_snapshot(
        _scope("IMPORT-003", "client:beclass-review:abc", "review:beclass-review:abc")
    )
    assert reader.identities == ["beclass-review:abc"]
    assert snapshot.facts[0].accepted_mapping_consistent is True
    assert snapshot.facts[0].accepted_lineage == lineage
    assert snapshot.facts[0].predicate_active is False


def test_review_lineage_rejects_mapping_for_another_review() -> None:
    review = {
        "id": 11,
        "source_event_identity": "beclass-workbook:" + "a" * 64 + ":row:3",
        "issue_codes": '["identity_conflict"]',
        "owner_version": 11,
    }
    lineage = CasePairingAcceptedLineage(
        "beclass-review:other",
        "beclass-workbook:" + "b" * 64 + ":row:4",
        "client-beclass-apply-event:17",
    )
    snapshot = MySqlCasePairingCurrentIssueAdapter(
        _Connection([review]), _ExactLineageReader(CasePairingAcceptedMapping(lineage, "CASE-1", 1))
    ).read_owner_snapshot(
        _scope("IMPORT-003", "client:beclass-review:abc", "review:beclass-review:abc")
    )
    assert snapshot.facts[0].accepted_mapping_consistent is False
    assert snapshot.facts[0].predicate_active is True


def test_review_lineage_rejects_same_source_as_cross_source_proof() -> None:
    source = "beclass-workbook:" + "a" * 64 + ":row:3"
    review = {
        "id": 11,
        "source_event_identity": source,
        "issue_codes": '["identity_conflict"]',
        "owner_version": 11,
    }
    lineage = CasePairingAcceptedLineage(
        "beclass-review:abc", source, "client-beclass-apply-event:17"
    )
    snapshot = MySqlCasePairingCurrentIssueAdapter(
        _Connection([review]),
        _ExactLineageReader(CasePairingAcceptedMapping(lineage, "CASE-1", 1)),
    ).read_owner_snapshot(
        _scope("IMPORT-003", "client:beclass-review:abc", "review:beclass-review:abc")
    )
    assert snapshot.facts[0].accepted_mapping_consistent is False
    assert snapshot.facts[0].predicate_active is True
