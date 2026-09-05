"""Focused contract tests for the Task 97 current-only anomaly successor."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from api.dependencies.durable_job_handlers import anomaly_recheck_handler, default_job_handlers
from domains.anomalies.current_issue import (
    CURRENT_ISSUE_SUBJECT_FIELDS,
    CurrentIssueCandidate,
    build_issue_key,
    canonical_subject_identity,
    canonical_subject_identity_for_code,
)
from infrastructure.mysql.current_anomaly_issue_repository import MySqlCurrentIssueRepository
from infrastructure.mysql.anomaly_runtime import MySqlAnomalyRuntime
from shared_kernel.fingerprints import fingerprint_payload
from domains.anomalies.current_issue import RecheckIntent, RecheckScope
from subsystems.anomalies.current_issue_recheck import recheck_intent_from_payload


ROOT = Path(__file__).resolve().parents[7]  # repository root from canonical module test root


def test_subject_identity_and_key_are_collation_independent() -> None:
    subject = {"case_no": "CASE-7", "notification_reason": "recipient_unavailable"}
    canonical = canonical_subject_identity(subject)
    assert canonical == '{"case_no":"CASE-7","notification_reason":"recipient_unavailable"}'
    payload = json.dumps(
        {
            "v": 2,
            "definition_code": "LINE-006",
            "subject_identity": subject,
            "lifecycle_token": "owner-lifecycle-7",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    expected = "ci_" + hashlib.sha256(payload).hexdigest()
    assert build_issue_key("LINE-006", subject, "owner-lifecycle-7") == expected
    assert build_issue_key(
        "LINE-006", dict(reversed(tuple(subject.items()))), "owner-lifecycle-7"
    ) == expected


def test_issue_key_changes_for_a_new_lifecycle_without_secret() -> None:
    subject = {"case_no": "CASE-7", "notification_reason": "recipient_unavailable"}
    first = build_issue_key("LINE-006", subject, "owner-lifecycle-7")
    repeated = build_issue_key("LINE-006", subject, "owner-lifecycle-7")
    next_lifecycle = build_issue_key("LINE-006", subject, "owner-lifecycle-8")

    assert first == repeated
    assert next_lifecycle != first
    assert first.startswith("ci_") and len(first) == 67


def test_runtime_identity_requires_only_canonical_lifecycle_facts() -> None:
    runtime = MySqlAnomalyRuntime()
    subject = {"case_no": "CASE-7", "notification_reason": "recipient_unavailable"}
    assert runtime.current_issue_key("LINE-006", subject, "owner-lifecycle-7") == build_issue_key(
        "LINE-006", subject, "owner-lifecycle-7"
    )


def test_subject_schema_is_closed_for_the_current_code() -> None:
    assert set(CURRENT_ISSUE_SUBJECT_FIELDS) == {"LINE-006"}
    identity = {"case_no": "CASE-1", "notification_reason": "recipient_unavailable"}
    assert canonical_subject_identity_for_code("LINE-006", identity) == (
        '{"case_no":"CASE-1","notification_reason":"recipient_unavailable"}'
    )
    try:
        canonical_subject_identity_for_code("LINE-006", {**identity, "extra": "x"})
    except ValueError as error:
        assert str(error) == "anomaly subject identity fields are not closed"
    else:  # pragma: no cover
        raise AssertionError("unknown subject fields must fail closed")


def test_recheck_payload_round_trips_without_a_secret() -> None:
    scope = RecheckScope("line", "notification_failure", "recipient_unavailable", ("CASE-1",), ("line:notification_failure:CASE-1",))
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


def test_current_candidate_requires_canonical_subject_identity() -> None:
    try:
        CurrentIssueCandidate(
            issue_key="ci_missing_identity",
            definition_code="LINE-006",
            owner_domain="line",
            owner_root_type="notification_failure",
            subject_type="recipient_unavailable",
            subject_id="CASE-1",
            owner_version=1,
            severity="blocking",
            blocking=True,
            details={"reason": "test"},
        )
    except TypeError as error:
        assert "subject_identity" in str(error)
    else:  # pragma: no cover
        raise AssertionError("missing canonical identity must fail at construction")


def test_schema_is_one_current_projection_and_no_anomaly_history() -> None:
    sql = (ROOT / "db/schema_parts/1016_current_anomaly_issues.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS current_anomaly_issues" in sql
    assert "subject_identity JSON NOT NULL" in sql
    assert "details_version" in sql
    lower = sql.lower()
    for forbidden in ("occurrence", "workflow", "claim", "resolve", "reclassification", "timeline", "history", "delivery"):
        assert f"create table {forbidden}" not in lower
