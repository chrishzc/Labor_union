"""Read existing Scheduling photo submission lineage; never create external facts."""
from __future__ import annotations

from datetime import date, datetime
import re

from domains.controlled_files.reference_finalize import canonical_scheduling_object_key
from domains.line.identities import LineUserId
from subsystems.scheduling.service_day_log_photo_reference import SubmittedServiceDayLogPhoto


class MySqlSubmittedServiceDayLogPhotoRepository:
    def __init__(self, connection):
        self._connection = connection

    def get_submitted_photo_reference(self, file_id: str) -> SubmittedServiceDayLogPhoto | None:
        if not isinstance(file_id, str) or re.fullmatch(r"cf_[0-9a-f]{32}", file_id) is None:
            return None
        with self._connection.cursor() as cursor:
            cursor.execute(_SUBMITTED_PHOTO_SQL, (file_id,))
            rows = tuple(cursor.fetchall())
        return _submitted_photo_reference(rows)


def _submitted_photo_reference(rows) -> SubmittedServiceDayLogPhoto | None:
    """Materialize the same committed attachment used by the owner's readback.

    LIFF token verification happens at the existing transport before the owner
    writer. These rows preserve that writer's staff identity/submission, not a
    provider-issued message receipt or a retained token-verification attestation.
    """
    if len(rows) != 1:
        return None
    row = rows[0]
    try:
        positive = ("log_id", "attachment_id", "assignment_id", "staff_id", "event_id", "version", "size_bytes")
        if any(type(row[name]) is not int or row[name] <= 0 for name in positive):
            return None
        day = row["service_date"]
        if not isinstance(day, date) or isinstance(day, datetime):
            return None
        LineUserId(row["staff_line_user_id"])
        if (not isinstance(row["content_fingerprint"], str)
            or re.fullmatch(r"[0-9a-f]{64}", row["content_fingerprint"]) is None
            or not isinstance(row["idempotency_key"], str) or not row["idempotency_key"].strip()
            or row["event_idempotency_key"] != row["idempotency_key"]
            or row["event_type"] != "submitted"
            or row["event_assignment_id"] != row["assignment_id"]
            or row["event_staff_id"] != row["staff_id"]
            or row["event_service_date"] != day
            or row["assignment_case_no"] != row["case_no"]
            or row["assignment_staff_id"] != row["staff_id"]):
            return None
        kind, digest = row["attachment_kind"], row["sha256_digest"]
        if kind not in {"baby_log_photo", "meal_photo"}:
            return None
        expected_key = canonical_scheduling_object_key(case_no=row["case_no"], service_date=day,
            attachment_kind=kind, sequence=1, sha256_digest=digest)
        if (row["reference_kind"] != "scheduling_service_day_log_attachment"
            or row["provider_media_id"] is not None
            or not isinstance(row["file_id"], str) or re.fullmatch(r"cf_[0-9a-f]{32}", row["file_id"]) is None
            or row["object_owner"] != "scheduling" or row["staging_owner"] != "scheduling"
            or row["object_purpose"] != kind or row["staging_purpose"] != kind
            or row["object_subject"] != row["case_no"] or row["staging_subject"] != row["case_no"]
            or row["object_key"] != expected_key or row["staging_key"] != expected_key
            or row["staging_digest"] != digest or row["staging_state"] != "applied"
            or row["object_actor"] != f"staff:{row['staff_id']}" or row["staging_actor"] != row["object_actor"]
            or row["mime_type"] not in {"image/jpeg", "image/png"}
            or row["staging_mime_type"] != row["mime_type"] or row["staging_size_bytes"] != row["size_bytes"]):
            return None
        return SubmittedServiceDayLogPhoto(row["file_id"], row["version"], digest, row["size_bytes"], row["mime_type"], row["case_no"], kind,
            row["log_id"], row["attachment_id"], row["assignment_id"], row["staff_id"], day)
    except (KeyError, TypeError, ValueError):
        return None


_SUBMITTED_PHOTO_SQL = (
    "SELECT object.opaque_object_id AS file_id,object.version_number AS version,"
    "object.content_sha256 AS sha256_digest,object.owner_type AS object_owner,"
    "object.purpose AS object_purpose,object.subject_reference AS object_subject,"
    "object.object_key,object.created_by_actor AS object_actor,object.content_type AS mime_type,object.size_bytes,"
    "staging.owner_type AS staging_owner,staging.purpose AS staging_purpose,"
    "staging.subject_reference AS staging_subject,staging.object_key AS staging_key,"
    "staging.content_sha256 AS staging_digest,staging.staging_state,staging.created_by_actor AS staging_actor,"
    "staging.content_type AS staging_mime_type,staging.size_bytes AS staging_size_bytes,reference.reference_kind,"
    "attachment.id AS attachment_id,attachment.attachment_kind,attachment.provider_media_id,"
    "log.id AS log_id,log.case_no,log.assignment_id,log.staff_id,log.staff_line_user_id,log.service_date,"
    "log.content_fingerprint,log.idempotency_key,event.id AS event_id,event.event_type,"
    "event.assignment_id AS event_assignment_id,event.staff_id AS event_staff_id,"
    "event.service_date AS event_service_date,event.idempotency_key AS event_idempotency_key,"
    "assignment.case_no AS assignment_case_no,assignment.staff_id AS assignment_staff_id "
    "FROM controlled_file_objects object "
    "JOIN controlled_file_staging_objects staging ON staging.id=object.source_staging_id "
    "JOIN controlled_file_references reference ON reference.controlled_file_object_id=object.id "
    "JOIN scheduling_service_day_log_attachments attachment ON attachment.id=reference.service_day_log_attachment_id "
    "AND attachment.controlled_file_object_id=object.id "
    "JOIN scheduling_service_day_logs log ON log.id=attachment.service_day_log_id "
    "JOIN scheduling_service_day_log_events event ON event.service_day_log_id=log.id AND event.event_type='submitted' "
    "JOIN case_staff_assignments assignment ON assignment.id=log.assignment_id "
    "WHERE object.opaque_object_id=%s LIMIT 2"
)
