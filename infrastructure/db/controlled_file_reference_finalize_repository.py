"""MySQL adapter for the 1015 controlled-file reference/finalize successor.

The adapter executes statements only.  Transaction ownership stays with the
outer application Unit of Work, and storage-provider effects never run here.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from domains.controlled_files.reference_finalize import (
    ControlledFileFinalizeIntent,
    ControlledFileFinalizeState,
    ControlledFileLease,
    ReferenceAwareStagingCandidate,
    SchedulingControlledFileReference,
)
from subsystems.controlled_files.reference_finalize import ControlledFileFinalizeError


class MySqlControlledFileReferenceFinalizeRepository:
    """Persistence port; callers provide the transaction boundary."""

    def __init__(self, connection: Any, *, lease_duration: timedelta = timedelta(hours=24)) -> None:
        if lease_duration <= timedelta(0):
            raise ValueError("controlled file lease duration must be positive")
        self._connection = connection
        self._lease_duration = lease_duration

    def create_finalize_intent(self, intent: ControlledFileFinalizeIntent) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO controlled_file_finalize_intents
                    (finalize_id, staging_object_id, controlled_file_object_id,
                     expected_sha256, finalize_state, created_at_utc)
                SELECT %s, staging.id, object.id, %s, 'pending', %s
                FROM controlled_file_staging_objects staging
                JOIN controlled_file_objects object
                  ON object.opaque_object_id=%s
                WHERE staging.staging_id=%s
                """,
                (
                    intent.finalize_id,
                    intent.expected_sha256,
                    _mysql_utc(intent.created_at or datetime.now(timezone.utc)),
                    intent.controlled_file_object_id,
                    intent.staging_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ControlledFileFinalizeError(
                    "controlled_file_finalize_reference_missing",
                    "finalize intent references missing controlled-file facts",
                )

    def claim_finalize_intent(
        self, finalize_id: str, *, worker_id: str, observed_at: datetime
    ) -> ControlledFileFinalizeIntent | None:
        """Claim with CAS; the caller commits this short transaction."""

        claim_token = f"{worker_id}:{uuid4().hex}"
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE controlled_file_finalize_intents
                SET finalize_state='processing', claimed_by=%s,
                    claimed_at_utc=%s, claim_token=%s, attempt_count=attempt_count+1,
                    available_at_utc=NULL, failed_at_utc=NULL, last_error_code=NULL,
                    observed_sha256=NULL, observed_size_bytes=NULL
                WHERE finalize_id=%s
                  AND (finalize_state IN ('pending','reconciliation_required')
                       OR (finalize_state='processing' AND claimed_at_utc < %s))
                """,
                (worker_id, _mysql_utc(observed_at), claim_token, finalize_id,
                 _mysql_utc(observed_at - self._lease_duration)),
            )
            if cursor.rowcount != 1:
                cursor.execute(
                    "SELECT intent.finalize_id,staging.staging_id,object.opaque_object_id "
                    "AS controlled_file_object_id,intent.expected_sha256,intent.finalize_state,"
                    "intent.claim_token,intent.observed_sha256,intent.observed_size_bytes,"
                    "intent.created_at_utc FROM controlled_file_finalize_intents intent "
                    "JOIN controlled_file_staging_objects staging ON staging.id=intent.staging_object_id "
                    "JOIN controlled_file_objects object ON object.id=intent.controlled_file_object_id "
                    "WHERE intent.finalize_id=%s",
                    (finalize_id,),
                )
                row = cursor.fetchone()
                return None if row is None else _intent(row)
            cursor.execute(
                "SELECT intent.finalize_id,staging.staging_id,object.opaque_object_id "
                "AS controlled_file_object_id,intent.expected_sha256,intent.finalize_state,"
                "intent.claim_token,intent.observed_sha256,intent.observed_size_bytes,"
                "intent.created_at_utc FROM controlled_file_finalize_intents intent "
                "JOIN controlled_file_staging_objects staging ON staging.id=intent.staging_object_id "
                "JOIN controlled_file_objects object ON object.id=intent.controlled_file_object_id "
                "WHERE intent.finalize_id=%s",
                (finalize_id,),
            )
            row = cursor.fetchone()
        if not isinstance(row, Mapping):
            raise ControlledFileFinalizeError(
                "controlled_file_finalize_claim_missing",
                "finalize claim succeeded without a readable intent",
            )
        return _intent(row)

    def mark_finalize_available(
        self,
        finalize_id: str,
        *,
        worker_id: str,
        claim_token: str,
        observed_at: datetime,
        observed_sha256: str,
        observed_size_bytes: int,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE controlled_file_finalize_intents
                SET finalize_state='available', available_at_utc=%s,
                    observed_sha256=%s, observed_size_bytes=%s,
                    claimed_by=NULL, claimed_at_utc=NULL, claim_token=NULL
                WHERE finalize_id=%s AND finalize_state='processing'
                  AND claimed_by=%s AND claim_token=%s
                """,
                (_mysql_utc(observed_at), observed_sha256, observed_size_bytes, finalize_id, worker_id, claim_token),
            )
            if cursor.rowcount != 1:
                raise ControlledFileFinalizeError(
                    "controlled_file_finalize_state_conflict",
                    "finalize intent is no longer owned by worker",
                )

    def mark_finalize_reconciliation_required(
        self,
        finalize_id: str,
        *,
        worker_id: str,
        claim_token: str,
        observed_at: datetime,
        error_code: str,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE controlled_file_finalize_intents
                SET finalize_state='reconciliation_required', last_error_code=%s,
                    failed_at_utc=%s, claimed_by=NULL, claimed_at_utc=NULL, claim_token=NULL
                WHERE finalize_id=%s AND finalize_state='processing'
                  AND claimed_by=%s AND claim_token=%s
                """,
                (error_code, _mysql_utc(observed_at), finalize_id, worker_id, claim_token),
            )
            if cursor.rowcount != 1:
                raise ControlledFileFinalizeError(
                    "controlled_file_finalize_state_conflict",
                    "finalize intent is no longer owned by worker",
                )

    def assert_finalize_available(self, controlled_file_object_id: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1 FROM controlled_file_objects object
                JOIN controlled_file_finalize_intents intent
                  ON intent.controlled_file_object_id=object.id
                WHERE object.opaque_object_id=%s AND intent.finalize_state='available'
                LIMIT 1
                """,
                (controlled_file_object_id,),
            )
            if cursor.fetchone() is None:
                raise ControlledFileFinalizeError(
                    "controlled_file_finalize_not_available",
                    "controlled file bytes are not integrity verified",
                )

    def assert_controlled_file_exists(self, controlled_file_object_id: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM controlled_file_objects WHERE opaque_object_id=%s LIMIT 1",
                (controlled_file_object_id,),
            )
            if cursor.fetchone() is None:
                raise ControlledFileFinalizeError(
                    "controlled_file_object_not_found",
                    "controlled file object does not exist",
                )

    def create_scheduling_reference(
        self, reference: SchedulingControlledFileReference
    ) -> SchedulingControlledFileReference:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO controlled_file_references
                    (reference_id, controlled_file_object_id,
                     service_day_log_attachment_id, reference_kind, created_at_utc)
                SELECT %s, object.id, attachment.id, %s, %s
                FROM controlled_file_objects object
                JOIN scheduling_service_day_log_attachments attachment
                  ON attachment.id=%s
                WHERE object.opaque_object_id=%s
                """,
                (
                    reference.reference_id,
                    reference.kind.value,
                    _mysql_utc(reference.created_at),
                    reference.service_day_log_attachment_id,
                    reference.controlled_file_object_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ControlledFileFinalizeError(
                    "controlled_file_reference_create_conflict",
                    "Scheduling attachment reference could not be created",
                )
        return reference

    def acquire_lease(self, lease: ControlledFileLease) -> ControlledFileLease:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO controlled_file_leases
                    (lease_id, staging_object_id, holder, lease_state,
                     acquired_at_utc, expires_at_utc)
                SELECT %s, id, %s, 'active', %s, %s
                FROM controlled_file_staging_objects WHERE staging_id=%s
                """,
                (
                    lease.lease_id,
                    lease.holder,
                    _mysql_utc(lease.acquired_at),
                    _mysql_utc(lease.expires_at),
                    lease.staging_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ControlledFileFinalizeError(
                    "controlled_file_lease_create_conflict",
                    "staging object is unavailable for lease",
                )
        return lease

    def acquire_finalize_lease(
        self,
        intent: ControlledFileFinalizeIntent,
        *,
        worker_id: str,
        acquired_at: datetime,
    ) -> ControlledFileLease:
        lease = ControlledFileLease(
            lease_id=f"cfl_{uuid4().hex}",
            staging_id=intent.staging_id,
            holder=worker_id,
            acquired_at=acquired_at,
            expires_at=acquired_at + self._lease_duration,
        )
        return self.acquire_lease(lease)

    def release_lease(self, lease_id: str, *, released_at: datetime, worker_id: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE controlled_file_leases
                SET lease_state='released', released_at_utc=%s
                WHERE lease_id=%s AND lease_state='active' AND holder=%s
                """,
                (_mysql_utc(released_at), lease_id, worker_id),
            )
            if cursor.rowcount != 1:
                raise ControlledFileFinalizeError(
                    "controlled_file_lease_state_conflict",
                    "lease is not active or is owned by another worker",
                )

    def release_finalize_lease(
        self, lease: ControlledFileLease, *, released_at: datetime, worker_id: str
    ) -> None:
        self.release_lease(lease.lease_id, released_at=released_at, worker_id=worker_id)

    def list_reference_aware_gc_candidates(
        self, *, limit: int, observed_at: datetime
    ) -> tuple[ReferenceAwareStagingCandidate, ...]:
        if isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("controlled file GC limit must be between 1 and 100")
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT staging.staging_id, staging.staging_version,
                       staging.content_sha256, staging.expires_at_utc,
                       CASE WHEN staging.staging_state='applied' THEN 1 ELSE 0 END registered,
                       COUNT(DISTINCT reference.id) reference_count,
                       COUNT(DISTINCT active_lease.id) active_lease_count
                FROM controlled_file_staging_objects staging
                JOIN controlled_file_finalize_intents intent
                     ON intent.staging_object_id=staging.id
                LEFT JOIN controlled_file_objects object ON object.source_staging_id=staging.id
                LEFT JOIN controlled_file_references reference
                       ON reference.controlled_file_object_id=object.id
                LEFT JOIN controlled_file_leases active_lease
                       ON active_lease.staging_object_id=staging.id
                      AND active_lease.lease_state='active'
                      AND active_lease.expires_at_utc>%s
                WHERE staging.staging_state IN ('staged','quarantined')
                GROUP BY staging.id, staging.staging_id, staging.staging_version,
                         staging.content_sha256, staging.expires_at_utc, staging.staging_state
                ORDER BY staging.id LIMIT %s
                """,
                (_mysql_utc(observed_at), limit),
            )
            rows = cursor.fetchall()
        return tuple(
            ReferenceAwareStagingCandidate(
                staging_id=str(row["staging_id"]),
                staging_version=int(row["staging_version"]),
                expected_sha256=str(row["content_sha256"]),
                expires_at=_aware(row["expires_at_utc"]),
                registered=bool(row["registered"]),
                reference_count=int(row["reference_count"]),
                active_lease=int(row["active_lease_count"]) > 0,
            )
            for row in rows
        )


def _intent(row: Mapping[str, Any]) -> ControlledFileFinalizeIntent:
    return ControlledFileFinalizeIntent(
        finalize_id=str(row["finalize_id"]),
        staging_id=str(row["staging_id"]),
        controlled_file_object_id=str(row["controlled_file_object_id"]),
        expected_sha256=str(row["expected_sha256"]),
        state=ControlledFileFinalizeState(str(row["finalize_state"])),
        created_at=_aware(row["created_at_utc"]),
        claim_token=None if row.get("claim_token") is None else str(row["claim_token"]),
        observed_sha256=(
            None if row.get("observed_sha256") is None else str(row["observed_sha256"])
        ),
        observed_size_bytes=(
            None if row.get("observed_size_bytes") is None else int(row["observed_size_bytes"])
        ),
    )


def _mysql_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("controlled-file timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = ["MySqlControlledFileReferenceFinalizeRepository"]
