"""
File: test_service_before_replacement_mysql_adapter.py
Description: 在指定 1012 測試庫驗證服務前換人的單一交易、重播、readback 與 immutable evidence。
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import os
from uuid import uuid4

import pymysql
import pytest

from domains.scheduling.matching_coordination import (
    CandidateEligibility,
    MatchingCandidateResult,
    MatchingPackage,
    MatchingPackageMode,
    MatchingSegment,
    MatchingSourceVersion,
    SOURCE_KINDS,
)
from domains.scheduling.service_before_replacement import (
    ActualServiceProof,
    ReplacementRootIdentity,
    ReplacementRootKind,
    ReplacementScenario,
    ServiceBeforeReplacementFacts,
)
from infrastructure.mysql.matching_successor_persistence_adapter import (
    MatchingSuccessorPersistenceAdapter,
    _package_storage_payload,
)
from infrastructure.mysql.service_before_replacement_repository import (
    MySqlServiceBeforeReplacementRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.scheduling.service_before_replacement_workflow import (
    ApplyServiceBeforeReplacement,
    ReplacementApplyStatus,
    ServiceBeforeReplacementQueryRequest,
    ServiceBeforeReplacementWorkflow,
)


_EXPECTED_DATABASE = "lu_test_task96_ldu_candidate_1012_r1"
_DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE", "").strip()
pytestmark = pytest.mark.skipif(
    not _DATABASE,
    reason="requires explicit LABOR_UNION_TEST_MYSQL_* configuration",
)


def test_r02_apply_replay_and_exact_mysql_readback() -> None:
    connection = _connection()
    case_no = f"RPRE-{uuid4().hex[:20]}"
    try:
        _assert_target(connection)
        source = _seed_prerequisites(connection, case_no)
        facts = _facts(case_no)
        repository = MySqlServiceBeforeReplacementRepository(
            connection,
            MatchingSuccessorPersistenceAdapter(connection),
            facts_loader=lambda _request, _for_update: facts,
            matching_source_loader=lambda _request, _for_update: source,
        )
        workflow = ServiceBeforeReplacementWorkflow(
            repository, lambda: MySqlUnitOfWork(connection)
        )
        preview = workflow.preview(ServiceBeforeReplacementQueryRequest(
            case_no, ReplacementScenario.R02, CorrelationId(f"correlation:{case_no}")
        ))
        command = _command(case_no, preview.fingerprint)

        applied = workflow.apply(command)
        replayed = workflow.apply(command)

        assert applied.status is ReplacementApplyStatus.APPLIED
        assert replayed.status is ReplacementApplyStatus.REPLAYED
        assert applied.receipt == replayed.receipt
        assert applied.readback is not None
        assert applied.readback.matching_package_lineage_id > 0
        assert applied.readback.matching_event_id > 0
        assert _owned_counts(connection, case_no) == (1, 5, 1, 1, 1)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT aggregate_version,generation_counter FROM scheduling_aggregates "
                "WHERE case_no=%s",
                (case_no,),
            )
            aggregate = cursor.fetchone()
            cursor.execute(
                "SELECT status,effective_marker FROM scheduling_generations "
                "WHERE case_no=%s ORDER BY generation_number",
                (case_no,),
            )
            generations = tuple(cursor.fetchall())
        assert aggregate == {"aggregate_version": 9, "generation_counter": 9}
        assert generations[0]["status"] == "cancelled"
        assert generations[1] == {"status": "effective", "effective_marker": 1}
        print(f"retained RPRE evidence scenario: {case_no}")
    finally:
        connection.rollback()
        connection.close()


def _connection() -> pymysql.Connection:
    if os.getenv("APP_ENV") != "development":
        pytest.fail("RPRE integration test requires APP_ENV=development")
    if _DATABASE != _EXPECTED_DATABASE or not _DATABASE.startswith("lu_test_"):
        pytest.fail("RPRE integration test refuses every non-approved database")
    return pymysql.connect(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=_DATABASE,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _assert_target(connection: pymysql.Connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT DATABASE() AS database_name,@@hostname AS host_name")
        target = cursor.fetchone()
    assert target["database_name"] == _EXPECTED_DATABASE
    assert str(target["host_name"]).strip()


def _sources(case_no: str) -> tuple[MatchingSourceVersion, ...]:
    return tuple(
        MatchingSourceVersion(
            kind,
            f"{kind}:{case_no}:8",
            8,
            fingerprint_payload({"case_no": case_no, "kind": kind}).value,
        )
        for kind in SOURCE_KINDS
    )


def _seed_prerequisites(connection: pymysql.Connection, case_no: str) -> dict[str, object]:
    versions = _sources(case_no)
    service_day = date(2026, 9, 1)
    criteria = {"required_service_dates": [service_day.isoformat()]}
    criteria_digest = fingerprint_payload({
        "case_no": case_no,
        "criteria": criteria,
        "criteria_version": 8,
        "source_versions": [item.as_payload() for item in versions],
    }).value
    parent = MatchingPackage(
        package_id=f"matching-package:{case_no}:8",
        version=8,
        mode=MatchingPackageMode.SINGLE,
        segments=(MatchingSegment(1, (service_day,), 1),),
        required_service_dates=(service_day,),
        candidate_results=(MatchingCandidateResult(
            f"candidate:{case_no}:1",
            1,
            CandidateEligibility.ELIGIBLE,
            (),
            coverage_evidence=(service_day,),
            willingness="willing",
        ),),
        criteria_snapshot_id=f"matching-snapshot:{case_no}:8",
        source_versions=versions,
    )
    source_payload = [_source_payload(item) for item in versions]
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO clients (case_no,name,phone,city,address,service_time,service_type) "
            "VALUES (%s,'RPRE client','0900000000','Test City','Test Address','day','care')",
            (case_no,),
        )
        client_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO orders (case_no,client_id) VALUES (%s,%s)",
            (case_no, client_id),
        )
        cursor.execute(
            "INSERT INTO scheduling_generations "
            "(case_no,generation_number,resulting_aggregate_version,status,effective_marker,"
            "created_by,change_reason) VALUES (%s,8,8,'effective',1,'task96-rpre','fixture')",
            (case_no,),
        )
        prior_generation_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO scheduling_aggregates "
            "(case_no,aggregate_version,generation_counter,effective_generation_id) "
            "VALUES (%s,8,8,%s)",
            (case_no, prior_generation_id),
        )
        cursor.execute(
            "INSERT INTO matching_coordination_criteria_snapshots "
            "(snapshot_id,case_no,criteria_version,criteria_snapshot,source_version_tuple,"
            "criteria_digest,actor_ref,occurred_at_utc) VALUES (%s,%s,8,%s,%s,%s,%s,%s)",
            (
                parent.criteria_snapshot_id,
                case_no,
                _json(criteria),
                _json(source_payload),
                criteria_digest,
                "task96-rpre",
                datetime.now(timezone.utc).replace(tzinfo=None),
            ),
        )
        criteria_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO matching_coordination_package_lineage "
            "(package_id,case_no,criteria_snapshot_id,parent_package_id,package_version,"
            "lineage_kind,package_state,package_snapshot,source_version_tuple,package_digest,actor_ref) "
            "VALUES (%s,%s,%s,NULL,8,'initial',%s,%s,%s,%s,%s)",
            (
                parent.package_id,
                case_no,
                criteria_id,
                parent.state.value,
                _json(_package_storage_payload(parent)),
                _json(source_payload),
                parent.fingerprint.value,
                "task96-rpre",
            ),
        )
        parent_id = int(cursor.lastrowid)
        source_event_identity = f"matching-event:{case_no}:8"
        event_payload = {"case_no": case_no, "package_id": parent.package_id}
        cursor.execute(
            "INSERT INTO matching_coordination_events "
            "(event_id,case_no,criteria_snapshot_id,package_lineage_id,event_type,expected_version,"
            "resulting_version,event_payload,source_version_tuple,event_digest,actor_ref,"
            "idempotency_key,correlation_id,occurred_at_utc) "
            "VALUES (%s,%s,%s,%s,'package_proposed',7,8,%s,%s,%s,%s,%s,%s,%s)",
            (
                source_event_identity,
                case_no,
                criteria_id,
                parent_id,
                _json(event_payload),
                _json(source_payload),
                fingerprint_payload(event_payload).value,
                "task96-rpre",
                f"fixture:{case_no}",
                f"correlation:{case_no}:fixture",
                datetime.now(timezone.utc).replace(tzinfo=None),
            ),
        )
    connection.commit()
    return {
        "snapshot_id": parent.criteria_snapshot_id,
        "case_no": case_no,
        "criteria_version": 8,
        "criteria": criteria,
        "source_versions": source_payload,
        "criteria_digest": criteria_digest,
        "parent_package": parent,
        "source_event_identity": source_event_identity,
        "required_service_dates": [service_day.isoformat()],
    }


def _facts(case_no: str) -> ServiceBeforeReplacementFacts:
    roots = tuple(
        ReplacementRootIdentity(kind, f"{kind.value}:{case_no}:old", case_no)
        for kind in (
            ReplacementRootKind.MATCHING_PLAN,
            ReplacementRootKind.MATCHING_SEGMENT,
            ReplacementRootKind.MATCHING_REPLY,
            ReplacementRootKind.RECIPIENT_CONFIRMATION,
        )
    )
    proof = ActualServiceProof(case_no, (), f"official-service:{case_no}:8", 8)
    return ServiceBeforeReplacementFacts(
        case_no,
        ReplacementScenario.R02,
        (),
        f"generation:{case_no}:8",
        f"event:{case_no}:13",
        8,
        13,
        roots,
        actual_service_proof_available=True,
        actual_service_proof=proof,
        aggregate_version=8,
        prior_aggregate_identity=f"aggregate:{case_no}:8",
        replacement_reason="caregiver_requested_replacement",
        reason_evidence=(f"evidence:{case_no}",),
    )


def _command(case_no: str, preview_fingerprint) -> ApplyServiceBeforeReplacement:
    return ApplyServiceBeforeReplacement(
        case_no,
        ReplacementScenario.R02,
        ExpectedVersion(8),
        ExpectedVersion(13),
        ExpectedVersion(8),
        f"generation:{case_no}:8",
        f"event:{case_no}:13",
        f"aggregate:{case_no}:8",
        preview_fingerprint,
        IdempotencyKey(f"replacement:{case_no}:14"),
        ActorContext("task96-rpre", ("scheduling.replace",)),
        "caregiver_requested_replacement",
        (f"evidence:{case_no}",),
        CorrelationId(f"correlation:{case_no}"),
    )


def _owned_counts(connection: pymysql.Connection, case_no: str) -> tuple[int, ...]:
    tables = (
        "scheduling_service_before_replacement_events",
        "scheduling_service_before_replacement_roots",
        "scheduling_service_before_replacement_successors",
        "scheduling_service_before_replacement_receipts",
        "scheduling_service_before_replacement_outbox",
    )
    counts = []
    with connection.cursor() as cursor:
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) AS count_value FROM {table} WHERE case_no=%s", (case_no,))
            counts.append(int(cursor.fetchone()["count_value"]))
    return tuple(counts)


def _source_payload(value: MatchingSourceVersion) -> dict[str, object]:
    return {
        "source_kind": value.source_kind,
        "source_id": value.source_id,
        "version": value.version,
        "fingerprint": value.fingerprint,
    }


def _json(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
