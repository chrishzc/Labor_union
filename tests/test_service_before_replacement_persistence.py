"""
File: test_service_before_replacement_persistence.py
Description: 驗證服務前換人 owner persistence 的 typed successor、root digest 與交易邊界。
"""

from hashlib import sha256
from datetime import date
from dataclasses import replace
import json

import pytest

from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey


def test_matching_successor_adapter_persists_package_proposed_and_returns_numeric_fks():
    from infrastructure.mysql.matching_successor_persistence_adapter import (
        MatchingSuccessorPersistenceAdapter,
        MatchingSuccessorPersistenceRequest,
    )

    source = _canonical_source_snapshot()
    connection = _Connection(
        rows=[
            _stored_snapshot_row(source),
            _stored_parent_row(source),
            {"id": 501, "event_id": "matching:event:source", "case_no": "CASE-1",
             "criteria_snapshot_id": 7, "package_lineage_id": 11},
        ]
    )
    request = MatchingSuccessorPersistenceRequest(
        case_no="CASE-1",
        successor_package_identity="matching-package:CASE-1:4",
        successor_round_identity="successor-round:CASE-1:4",
        successor_matching_event_identity="matching-event:CASE-1:4",
        scenario="R-02",
        candidate_count=0,
        source_snapshot=source,
        actor=ActorContext("operator:1"),
        idempotency_key=IdempotencyKey("replacement:case-1:4"),
        correlation_id=CorrelationId("corr:case-1:4"),
    )

    result = MatchingSuccessorPersistenceAdapter(connection).persist_successor(request)

    assert result.package_lineage_id > 0
    assert result.matching_event_id > result.package_lineage_id
    assert result.package_identity == request.successor_package_identity
    assert result.event_identity == request.successor_matching_event_identity
    assert any("package_proposed" in str(params) for _, params in connection.statements)
    lineage_params = next(
        params for statement, params in connection.statements
        if statement.startswith("INSERT INTO matching_coordination_package_lineage")
    )
    from infrastructure.mysql.matching_coordination_repository import _package_from_payload
    loaded = _package_from_payload(json.loads(lineage_params[7]))
    assert loaded.state.value == "candidate_pool_open"
    assert loaded.candidate_results == ()
    assert connection.commit_count == 0
    assert connection.rollback_count == 0


def test_matching_successor_preflights_parent_before_any_insert():
    from infrastructure.mysql.matching_successor_persistence_adapter import (
        MatchingSuccessorPersistenceAdapter,
        MatchingSuccessorPersistenceError,
    )

    source = _canonical_source_snapshot()
    connection = _Connection(rows=[_stored_snapshot_row(source), None])
    with pytest.raises(MatchingSuccessorPersistenceError, match="parent package"):
        MatchingSuccessorPersistenceAdapter(connection).persist_successor(
            _request(source_snapshot=source)
        )
    assert connection.insert_count == 0
    assert connection.commit_count == 0
    assert connection.rollback_count == 0


def test_matching_successor_requires_fresh_source_event_binding_before_insert():
    from infrastructure.mysql.matching_successor_persistence_adapter import (
        MatchingSuccessorPersistenceAdapter,
        MatchingSuccessorPersistenceError,
    )

    source = _canonical_source_snapshot()
    connection = _Connection(
        rows=[
            _stored_snapshot_row(source),
            _stored_parent_row(source),
            None,
        ]
    )
    with pytest.raises(MatchingSuccessorPersistenceError, match="source event"):
        MatchingSuccessorPersistenceAdapter(connection).persist_successor(_request())
    assert connection.insert_count == 0


def test_matching_successor_rejects_abbreviated_source_tuple_before_insert():
    from infrastructure.mysql.matching_successor_persistence_adapter import (
        MatchingSuccessorPersistenceAdapter,
        MatchingSuccessorPersistenceError,
    )

    connection = _Connection(rows=[])
    with pytest.raises(MatchingSuccessorPersistenceError, match="source versions"):
        MatchingSuccessorPersistenceAdapter(connection).persist_successor(_legacy_request())
    assert connection.insert_count == 0


def test_matching_successor_rejects_stored_snapshot_content_drift_before_insert():
    from infrastructure.mysql.matching_successor_persistence_adapter import (
        MatchingSuccessorPersistenceAdapter,
        MatchingSuccessorPersistenceError,
    )

    source = _canonical_source_snapshot()
    stored = _stored_snapshot_row(source)
    stored["criteria_snapshot"] = json.dumps({"service_days": 99})
    connection = _Connection(rows=[stored])
    with pytest.raises(MatchingSuccessorPersistenceError, match="snapshot drift"):
        MatchingSuccessorPersistenceAdapter(connection).persist_successor(
            _request(source_snapshot=source)
        )
    assert connection.insert_count == 0


def test_matching_successor_rejects_parent_source_tuple_drift_before_insert():
    from infrastructure.mysql.matching_successor_persistence_adapter import (
        MatchingSuccessorPersistenceAdapter,
        MatchingSuccessorPersistenceError,
    )

    source = _canonical_source_snapshot()
    parent = _stored_parent_row(source)
    drifted = json.loads(parent["source_version_tuple"])
    drifted[0]["fingerprint"] = "f" * 64
    parent["source_version_tuple"] = json.dumps(drifted)
    connection = _Connection(rows=[_stored_snapshot_row(source), parent])
    with pytest.raises(MatchingSuccessorPersistenceError, match="parent package binding drift"):
        MatchingSuccessorPersistenceAdapter(connection).persist_successor(
            _request(source_snapshot=source)
        )
    assert connection.insert_count == 0


def test_matching_successor_rejects_fresh_parent_identity_drift_before_insert():
    from infrastructure.mysql.matching_successor_persistence_adapter import (
        MatchingSuccessorPersistenceAdapter,
        MatchingSuccessorPersistenceError,
    )

    source = _canonical_source_snapshot()
    stored_parent = _stored_parent_row(source)
    source["parent_package"] = replace(
        source["parent_package"],
        package_id="matching-package:CASE-1:other",
        fingerprint=None,
    )
    connection = _Connection(rows=[_stored_snapshot_row(source), stored_parent])
    with pytest.raises(MatchingSuccessorPersistenceError, match="parent package binding drift"):
        MatchingSuccessorPersistenceAdapter(connection).persist_successor(
            _request(source_snapshot=source)
        )
    assert connection.insert_count == 0


def test_matching_successor_reuses_only_complete_typed_package_facts():
    from domains.scheduling.matching_coordination import (
        CandidateEligibility,
        MatchingCandidateResult,
        MatchingPackage,
        MatchingPackageMode,
        MatchingSegment,
        MatchingSourceVersion,
    )
    from infrastructure.mysql.matching_successor_persistence_adapter import (
        MatchingSuccessorPersistenceAdapter,
    )

    source = _canonical_source_snapshot()
    versions = tuple(MatchingSourceVersion(**item) for item in source["source_versions"])
    service_day = date(2026, 9, 1)
    source["reuse_package"] = MatchingPackage(
        package_id="matching-package:CASE-1:reuse-source",
        version=4,
        mode=MatchingPackageMode.SINGLE,
        segments=(MatchingSegment(22, (service_day,), 1),),
        required_service_dates=(service_day,),
        candidate_results=(MatchingCandidateResult(
            "candidate:22", 22, CandidateEligibility.ELIGIBLE, (),
            coverage_evidence=(service_day,), willingness="willing",
        ),),
        criteria_snapshot_id=source["snapshot_id"],
        source_versions=versions,
    )
    connection = _Connection(rows=[
        _stored_snapshot_row(source),
        _stored_parent_row(source),
        {"id": 501, "event_id": "matching:event:source", "case_no": "CASE-1",
         "criteria_snapshot_id": 7, "package_lineage_id": 11},
    ])

    result = MatchingSuccessorPersistenceAdapter(connection).persist_successor(
        _request(source_snapshot=source, candidate_count=1)
    )

    assert result.candidate_count == 1
    lineage_params = next(
        params for statement, params in connection.statements
        if statement.startswith("INSERT INTO matching_coordination_package_lineage")
    )
    payload = json.loads(lineage_params[7])
    assert payload["candidate_results"][0]["staff_id"] == 22
    assert payload["segments"][0]["service_dates"] == ["2026-09-01"]


def test_repository_rejects_descriptor_drift_and_noncanonical_ordinals():
    from infrastructure.mysql.service_before_replacement_repository import (
        MySqlServiceBeforeReplacementRepository,
        ServiceBeforeReplacementPersistenceError,
    )

    connection = _Connection(
        rows=[
            {
                "id": 1,
                "case_no": "CASE-1",
                "replacement_generation_identity": "generation:new",
                "replacement_event_identity": "event:new",
                "resulting_generation_version": 2,
                "resulting_event_version": 2,
                "resulting_aggregate_version": 2,
                "successor_round_identity": "round:new",
                "successor_id": 3,
                "matching_package_lineage_id": 4,
                "matching_event_id": 5,
                "outbox_identity": "outbox:new",
                "retained_root_set_digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "retained_root_count": 0,
                "superseded_root_set_digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "superseded_root_count": 0,
                "created_root_set_digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "created_root_count": 0,
            },
            [
                {
                    "root_identity": "root:new",
                    "disposition": "created",
                    "canonical_ordinal": 2,
                    "owner_domain": "matching",
                    "root_kind": "successor_round",
                    "owner_descriptor_identity": "service-before-replacement.matching.successor_round",
                    "owner_descriptor_version": 1,
                    "owner_descriptor_fingerprint": "b" * 64,
                }
            ],
        ]
    )
    with pytest.raises(ServiceBeforeReplacementPersistenceError):
        MySqlServiceBeforeReplacementRepository(connection).load_owner_readback("CASE-1", for_update=False)


def test_replay_readback_requires_outbox_and_matching_numeric_fks():
    from subsystems.scheduling.service_before_replacement_workflow import (
        ReplacementReceipt,
        _receipt_readback_matches,
    )

    receipt = _receipt_for_replay()
    matching = _readback_for_replay(receipt)
    assert _receipt_readback_matches(matching, receipt)
    assert not _receipt_readback_matches(
        _readback_for_replay(receipt, outbox_identity="outbox:wrong"), receipt
    )
    assert not _receipt_readback_matches(
        _readback_for_replay(receipt, matching_event_id=999), receipt
    )


def test_repository_generation_transition_is_explicit_and_same_transaction():
    from infrastructure.mysql.service_before_replacement_repository import (
        MySqlServiceBeforeReplacementRepository,
    )

    connection = _Connection(rows=[
        {"aggregate_version": 1, "generation_counter": 1, "effective_generation_id": 10},
    ])
    repository = MySqlServiceBeforeReplacementRepository(connection)
    _, generation_id = repository.create_replacement_generation(
        case_no="CASE-1", expected_generation_version=1,
        resulting_generation_version=2, expected_aggregate_version=1,
        resulting_aggregate_version=2, actor_id="operator:1", reason="replace",
    )
    assert generation_id > 0
    assert connection.commit_count == 0
    assert connection.rollback_count == 0
    assert any("INSERT INTO scheduling_generations" in statement for statement, _ in connection.statements)
    assert any("UPDATE scheduling_aggregates" in statement for statement, _ in connection.statements)


def test_repository_generation_transition_requires_prior_effective_generation():
    from infrastructure.mysql.service_before_replacement_repository import (
        MySqlServiceBeforeReplacementRepository,
        ServiceBeforeReplacementPersistenceError,
    )

    connection = _Connection(rows=[
        {"aggregate_version": 1, "generation_counter": 1, "effective_generation_id": None},
    ])
    repository = MySqlServiceBeforeReplacementRepository(connection)
    with pytest.raises(ServiceBeforeReplacementPersistenceError, match="effective generation"):
        repository.create_replacement_generation(
            case_no="CASE-1", expected_generation_version=1,
            resulting_generation_version=2, expected_aggregate_version=1,
            resulting_aggregate_version=2, actor_id="operator:1", reason="replace",
        )
    assert connection.insert_count == 0


def test_repository_rejects_existing_prior_replacement_event_for_wrong_generation():
    from infrastructure.mysql.service_before_replacement_repository import (
        MySqlServiceBeforeReplacementRepository,
        ServiceBeforeReplacementPersistenceError,
    )

    connection = _Connection(rows=[{
        "id": 14,
        "replacement_generation_id": 99,
    }])
    repository = MySqlServiceBeforeReplacementRepository(connection)

    with pytest.raises(ServiceBeforeReplacementPersistenceError, match="generation binding drift"):
        repository._prior_replacement_event_id(
            "replacement-event:CASE-1:14",
            "CASE-1",
            expected_generation_id=10,
        )


def _request(*, source_snapshot=None, candidate_count=0):
    from infrastructure.mysql.matching_successor_persistence_adapter import MatchingSuccessorPersistenceRequest

    return MatchingSuccessorPersistenceRequest(
        case_no="CASE-1",
        successor_package_identity="matching-package:CASE-1:4",
        successor_round_identity="successor-round:CASE-1:4",
        successor_matching_event_identity="matching-event:CASE-1:4",
        scenario="R-02",
        candidate_count=candidate_count,
        source_snapshot=source_snapshot or _canonical_source_snapshot(),
        actor=ActorContext("operator:1"),
        idempotency_key=IdempotencyKey("replacement:case-1:4"),
        correlation_id=CorrelationId("corr:case-1:4"),
    )


def _legacy_request():
    source = _canonical_source_snapshot()
    source["source_versions"] = [{"source_kind": "orders_terms", "version": 3}]
    return _request(source_snapshot=source)


def _canonical_source_snapshot():
    from domains.scheduling.matching_coordination import (
        CandidateEligibility,
        MatchingCandidateResult,
        MatchingPackage,
        MatchingPackageMode,
        MatchingSegment,
        MatchingSourceVersion,
        SOURCE_KINDS,
    )
    from shared_kernel.fingerprints import fingerprint_payload

    versions = [
        {
            "source_kind": kind,
            "source_id": f"{kind}:CASE-1:3",
            "version": 3,
            "fingerprint": sha256(kind.encode("utf-8")).hexdigest(),
        }
        for kind in SOURCE_KINDS
    ]
    criteria = {"service_days": 2}
    digest = fingerprint_payload({
        "case_no": "CASE-1",
        "criteria": criteria,
        "criteria_version": 3,
        "source_versions": [
            (item["source_kind"], item["source_id"], item["version"], item["fingerprint"])
            for item in versions
        ],
    }).value
    typed_versions = tuple(MatchingSourceVersion(**item) for item in versions)
    service_day = date(2026, 9, 1)
    parent_package = MatchingPackage(
        package_id="matching-package:CASE-1:3",
        version=4,
        mode=MatchingPackageMode.SINGLE,
        segments=(MatchingSegment(11, (service_day,), 1),),
        required_service_dates=(service_day,),
        candidate_results=(MatchingCandidateResult(
            "candidate:11", 11, CandidateEligibility.ELIGIBLE, (),
            coverage_evidence=(service_day,), willingness="willing",
        ),),
        criteria_snapshot_id="snapshot:CASE-1:3",
        source_versions=typed_versions,
    )
    return {
        "snapshot_id": "snapshot:CASE-1:3",
        "case_no": "CASE-1",
        "criteria_version": 3,
        "criteria": criteria,
        "source_versions": versions,
        "criteria_digest": digest,
        "parent_package": parent_package,
        "source_event_identity": "matching:event:source",
    }


def _stored_snapshot_row(source):
    return {
        "id": 7,
        "snapshot_id": source["snapshot_id"],
        "case_no": source["case_no"],
        "criteria_version": source["criteria_version"],
        "criteria_snapshot": json.dumps(source["criteria"]),
        "source_version_tuple": json.dumps(source["source_versions"]),
        "criteria_digest": source["criteria_digest"],
    }


def _stored_parent_row(source):
    from infrastructure.mysql.matching_coordination_repository import _json_dump

    parent = source["parent_package"]
    return {
        "id": 11,
        "package_id": parent.package_id,
        "package_version": parent.version,
        "criteria_snapshot_id": 7,
        "package_state": parent.state.value,
        "package_snapshot": _json_dump(parent),
        "source_version_tuple": json.dumps(source["source_versions"]),
        "package_digest": parent.fingerprint.value,
    }


def _receipt_for_replay():
    from shared_kernel.fingerprints import fingerprint_payload
    from infrastructure.mysql.service_before_replacement_repository import root_set_digest
    from subsystems.scheduling.service_before_replacement_workflow import ReplacementReceipt

    return ReplacementReceipt(
        "CASE-1", "receipt:1", IdempotencyKey("replacement:case-1:4"),
        fingerprint_payload({"command": "1"}), fingerprint_payload({"preview": "1"}),
        "generation:new", "event:new", "round:new", 2, 2, 2, "outbox:new",
        (), (), (),
        root_set_digest(()), 0, root_set_digest(()), 0, root_set_digest(()), 0,
        matching_package_lineage_id=4, matching_event_id=5,
    )


def _readback_for_replay(receipt, *, outbox_identity=None, matching_event_id=None):
    from infrastructure.mysql.service_before_replacement_repository import root_set_digest
    from subsystems.scheduling.service_before_replacement_workflow import ReplacementOwnerReadback

    return ReplacementOwnerReadback(
        receipt.case_no, receipt.replacement_generation_identity,
        receipt.replacement_event_identity, receipt.successor_round_identity,
        receipt.resulting_generation_version, receipt.resulting_event_version,
        receipt.resulting_aggregate_version, (), (), (), True,
        (root_set_digest(()), root_set_digest(()), root_set_digest(())), (0, 0, 0),
        outbox_identity or receipt.outbox_identity,
        receipt.matching_package_lineage_id,
        matching_event_id if matching_event_id is not None else receipt.matching_event_id,
    )


def test_root_set_digest_uses_sorted_newline_and_empty_sha256():
    from infrastructure.mysql.service_before_replacement_repository import (
        root_set_digest,
    )

    assert root_set_digest(()) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert root_set_digest(("root:b", "root:a")) == sha256(b"root:a\nroot:b").hexdigest()


def test_repository_requires_matching_source_before_persisting():
    from infrastructure.mysql.service_before_replacement_repository import (
        MySqlServiceBeforeReplacementRepository,
        ServiceBeforeReplacementPersistenceError,
    )

    repository = MySqlServiceBeforeReplacementRepository(_Connection(rows=[]), matching_adapter=None)
    with pytest.raises(ServiceBeforeReplacementPersistenceError, match="matching source"):
        repository.require_matching_source(None)


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.lastrowid = 100 + len(connection.statements)
        self.rowcount = 1
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        self.connection.statements.append((sql, params))
        if sql.lstrip().upper().startswith("INSERT"):
            self.connection.insert_count += 1
        if sql.lstrip().upper().startswith("SELECT"):
            self._row = self.connection.rows.pop(0) if self.connection.rows else None

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._row if isinstance(self._row, list) else []

    def close(self):
        return None


class _Connection:
    def __init__(self, rows):
        self.rows = list(rows)
        self.statements = []
        self.insert_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    def cursor(self):
        return _Cursor(self)


__all__ = ["_Connection"]
