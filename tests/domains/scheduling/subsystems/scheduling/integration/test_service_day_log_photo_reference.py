"""Existing photo submission lineage metadata only: no project SQL or provider calls."""
from datetime import date
from pathlib import Path
import ast

import pytest

from domains.controlled_files.reference_finalize import canonical_scheduling_object_key
from infrastructure.mysql.service_day_log_photo_reference_repository import (
    MySqlSubmittedServiceDayLogPhotoRepository, _submitted_photo_reference,
)


def row(kind="meal_photo"):
    day, digest = date(2026, 11, 6), "a" * 64
    key = canonical_scheduling_object_key(case_no="CASE-1", service_date=day,
        attachment_kind=kind, sequence=1, sha256_digest=digest)
    return {
        "log_id": 9, "attachment_id": 10, "assignment_id": 11, "staff_id": 7, "event_id": 12,
        "version": 2, "size_bytes": 100, "service_date": day, "staff_line_user_id": "U-synthetic",
        "content_fingerprint": "b" * 64, "idempotency_key": "log-key", "event_idempotency_key": "log-key",
        "event_type": "submitted", "event_assignment_id": 11, "event_staff_id": 7, "event_service_date": day,
        "assignment_case_no": "CASE-1", "assignment_staff_id": 7, "case_no": "CASE-1", "attachment_kind": kind,
        "sha256_digest": digest, "reference_kind": "scheduling_service_day_log_attachment", "provider_media_id": None,
        "file_id": "cf_" + "c" * 32, "object_owner": "scheduling", "staging_owner": "scheduling",
        "object_purpose": kind, "staging_purpose": kind, "object_subject": "CASE-1", "staging_subject": "CASE-1",
        "object_key": key, "staging_key": key, "staging_digest": digest, "staging_state": "applied",
        "object_actor": "staff:7", "staging_actor": "staff:7", "mime_type": "image/jpeg",
        "staging_mime_type": "image/jpeg", "staging_size_bytes": 100,
    }


@pytest.mark.parametrize("kind", ["meal_photo", "baby_log_photo"])
def test_reference_reads_exact_owner_submission_and_frozen_file_tuple_without_claiming_provider_receipt(kind):
    facts = row(kind)
    reference = _submitted_photo_reference((facts,))
    assert (reference.file_id, reference.version, reference.sha256_digest) == (facts["file_id"], 2, "a" * 64)
    assert (reference.size_bytes, reference.mime_type) == (facts["size_bytes"], facts["mime_type"])
    assert (reference.case_no, reference.attachment_kind, reference.staff_id, reference.assignment_id) == ("CASE-1", kind, 7, 11)
    assert reference.owner_submission_reference == "scheduling-service-day-log:9"
    assert not hasattr(reference, "provider_message_id") and not hasattr(reference, "outbound_reference")
    assert not hasattr(reference, "staff_line_user_id")  # No LINE identity in the bounded cross-owner read model.


@pytest.mark.parametrize("field,value", [
    ("version", 0), ("file_id", "arbitrary-path"), ("sha256_digest", "d" * 64),
    ("log_id", True), ("event_id", 0), ("event_type", "unknown"), ("event_assignment_id", 12),
    ("event_staff_id", 8), ("event_service_date", date(2026, 11, 5)), ("event_idempotency_key", "other-key"),
    ("assignment_case_no", "OTHER"), ("assignment_staff_id", 8), ("staff_line_user_id", ""),
    ("content_fingerprint", "invalid"), ("idempotency_key", ""),
    ("provider_media_id", "legacy-provider-media"), ("reference_kind", "unowned"),
    ("object_owner", "staff"), ("staging_owner", "staff"), ("object_purpose", "baby_log_photo"),
    ("staging_purpose", "baby_log_photo"), ("object_subject", "OTHER"), ("staging_subject", "OTHER"),
    ("object_key", "different-key"), ("staging_key", "different-key"), ("staging_digest", "d" * 64),
    ("staging_state", "staged"), ("object_actor", "staff:8"), ("staging_actor", "staff:8"),
    ("mime_type", "application/pdf"), ("staging_mime_type", "image/png"), ("staging_size_bytes", 101),
])
def test_incomplete_or_conflicting_owner_submission_never_becomes_a_reference(field, value):
    facts = {**row(), field: value}
    assert _submitted_photo_reference((facts,)) is None


@pytest.mark.parametrize("rows", [(), ({},), (row(), row())])
def test_missing_or_ambiguous_submission_is_unavailable(rows):
    assert _submitted_photo_reference(rows) is None


def test_invalid_file_identity_is_rejected_before_opening_a_database_cursor():
    class NoSqlConnection:
        def cursor(self): raise AssertionError("Project SQL including fake SQL is forbidden")
    assert MySqlSubmittedServiceDayLogPhotoRepository(NoSqlConnection()).get_submitted_photo_reference("not-a-file-id") is None


def test_reader_is_bounded_and_has_no_write_or_transaction_effects():
    path = Path(__file__).resolve().parents[6] / "infrastructure/mysql/service_day_log_photo_reference_repository.py"
    module = ast.parse(path.read_text(encoding="utf-8"))
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"commit", "rollback", "begin"} for node in ast.walk(module))
    sql = next(node.value.value for node in module.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_SUBMITTED_PHOTO_SQL" for target in node.targets))
    assert sql.startswith("SELECT ") and sql.endswith("WHERE object.opaque_object_id=%s LIMIT 2")
    assert "scheduling_service_day_log_events" in sql and "controlled_file_references" in sql
    assert "line_inbox_events" not in sql and "line_media_records" not in sql
    assert not any(word in sql.upper() for word in ("INSERT ", "UPDATE ", "DELETE ", "FOR UPDATE"))
