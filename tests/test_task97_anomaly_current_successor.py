"""Focused contract tests for the Task 97 current-only anomaly successor."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path

from api.dependencies.durable_job_handlers import anomaly_recheck_handler, default_job_handlers
from domains.anomalies.current_issue import (
    CURRENT_ISSUE_SUBJECT_FIELDS,
    CurrentIssueCandidate,
    OwnerSnapshot,
    build_issue_key,
    canonical_subject_identity,
    canonical_subject_identity_for_code,
)
from infrastructure.mysql.current_anomaly_issue_repository import MySqlCurrentIssueRepository
from infrastructure.mysql.anomaly_runtime import MySqlAnomalyRuntime
from shared_kernel.fingerprints import fingerprint_payload
from domains.anomalies.current_issue import RecheckIntent, RecheckScope
from subsystems.anomalies.current_issue_recheck import recheck_intent_from_payload


ROOT = Path(__file__).resolve().parents[1]


def test_subject_identity_and_key_are_collation_independent() -> None:
    subject = {"batch_id": 7, "bank_fact_identity": "bf-1"}
    canonical = canonical_subject_identity({"bank_fact_identity": "bf-1", "batch_id": 7})
    assert canonical == '{"bank_fact_identity":"bf-1","batch_id":7}'
    payload = json.dumps(
        {"v": 1, "definition_code": "GOVSUB-002", "subject_identity": subject},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    expected = "ci_" + hmac.new(b"test-secret", payload, hashlib.sha256).hexdigest()
    assert build_issue_key("test-secret", "GOVSUB-002", subject) == expected
    assert build_issue_key("test-secret", "GOVSUB-002", dict(reversed(tuple(subject.items())))) == expected


def test_issue_key_requires_injected_secret() -> None:
    try:
        build_issue_key("", "GOVSUB-002", {"bank_fact_identity": "bf-1"})
    except ValueError as error:
        assert str(error) == "issue identity secret is required"
    else:  # pragma: no cover - assertion form keeps the failure explicit
        raise AssertionError("missing issue secret must fail closed")


def test_runtime_secret_is_only_used_through_key_composition() -> None:
    runtime = MySqlAnomalyRuntime(issue_identity_secret="test-secret")
    assert runtime.current_issue_key("GOVSUB-001", {"bank_fact_identity": "bf-1"}).startswith("ci_")
    try:
        MySqlAnomalyRuntime().current_issue_key("GOVSUB-001", {"bank_fact_identity": "bf-1"})
    except RuntimeError as error:
        assert str(error) == "anomaly issue identity secret not composed"
    else:  # pragma: no cover
        raise AssertionError("runtime without a secret must fail closed")


def test_subject_schema_is_closed_for_all_fifteen_target_codes() -> None:
    assert len(CURRENT_ISSUE_SUBJECT_FIELDS) == 15
    identity = {"assignment_id_a": "a-1", "assignment_id_b": "a-2"}
    assert canonical_subject_identity_for_code("SCHEDULE-003", identity) == (
        '{"assignment_id_a":"a-1","assignment_id_b":"a-2"}'
    )
    try:
        canonical_subject_identity_for_code("SCHEDULE-003", {**identity, "extra": "x"})
    except ValueError as error:
        assert str(error) == "anomaly subject identity fields are not closed"
    else:  # pragma: no cover
        raise AssertionError("unknown subject fields must fail closed")


def test_recheck_payload_round_trips_without_a_secret() -> None:
    scope = RecheckScope("government_subsidy", "claim", "claim", ("c-1",), ("government_subsidy:claim:c-1",))
    intent = RecheckIntent("recheck:c-1", scope, 4, fingerprint_payload({"subject": "c-1"}))
    payload = {
        "intent_identity": intent.intent_identity,
        "owner_domain": scope.owner_domain,
        "owner_root_type": scope.owner_root_type,
        "subject_type": scope.subject_type,
        "subject_ids": list(scope.subject_ids),
        "owner_lock_keys": list(scope.owner_lock_keys),
        "owner_version": intent.owner_version,
        "payload_fingerprint": intent.payload_fingerprint.value,
    }
    restored = recheck_intent_from_payload(payload)
    assert restored == intent
    assert "secret" not in json.dumps(payload)


def test_generic_job_registry_contains_typed_anomaly_recheck() -> None:
    assert default_job_handlers()["anomaly.recheck"] is anomaly_recheck_handler
    assert MySqlCurrentIssueRepository.__name__ == "MySqlCurrentIssueRepository"


def test_mysql_projection_fails_before_sql_without_canonical_subject_identity() -> None:
    scope = RecheckScope(
        "scheduling",
        "assignment",
        "assignment",
        ("a-1",),
        ("scheduling:assignment:a-1",),
    )
    repository = MySqlCurrentIssueRepository(object())
    repository._snapshot = OwnerSnapshot(scope, "owner-v1", 1, object())
    candidate = CurrentIssueCandidate(
        "ci_missing_identity",
        "SCHEDULE-006",
        "scheduling",
        "assignment",
        "assignment",
        "a-1",
        1,
        "blocking",
        True,
        {"reason": "test"},
    )

    try:
        repository.upsert_current(candidate, datetime.now(timezone.utc))
    except RuntimeError as error:
        assert str(error) == "current issue upsert lacks canonical subject identity"
    else:  # pragma: no cover
        raise AssertionError("missing canonical identity must fail before SQL")


def test_schema_is_one_current_projection_and_no_anomaly_history() -> None:
    sql = (ROOT / "db/schema_parts/1016_current_anomaly_issues.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS current_anomaly_issues" in sql
    assert "subject_identity JSON NOT NULL" in sql
    assert "details_version" in sql
    lower = sql.lower()
    for forbidden in ("occurrence", "workflow", "claim", "resolve", "reclassification", "timeline", "history", "delivery"):
        assert f"create table {forbidden}" not in lower
