"""
File: staff_retirement_repository.py
Description: 持久化 Staff lifecycle state、事件與冪等 receipt。
"""

from __future__ import annotations

from typing import Any

from domains.staff.retirement import StaffLifecycleFact, StaffLifecycleState
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey
from shared_kernel.clock import TAIPEI_TIME_ZONE
from subsystems.staff.retirement_workflow import StaffLifecycleApplyRequest, StaffLifecyclePreview, StaffLifecycleReceipt


class MySqlStaffRetirementRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load(self, staff_id: int, *, lock: bool) -> StaffLifecycleFact:
        suffix = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT id,status FROM staff WHERE id=%s" + suffix, (staff_id,))
            staff = cursor.fetchone()
            if staff is None:
                raise ValueError("staff_not_found")
            if str(staff["status"] or "active") != "active":
                raise ValueError("staff_lifecycle_state_unsupported")
            cursor.execute("SELECT lifecycle_state,aggregate_version,effective_at,reason_code FROM staff_lifecycle_states WHERE staff_id=%s" + suffix, (staff_id,))
            row = cursor.fetchone()
        if row is None:
            return StaffLifecycleFact(staff_id, StaffLifecycleState.ACTIVE, 0)
        effective_at = row["effective_at"]
        if effective_at is not None:
            effective_at = effective_at.replace(tzinfo=TAIPEI_TIME_ZONE)
        return StaffLifecycleFact(staff_id, StaffLifecycleState(str(row["lifecycle_state"])), int(row["aggregate_version"]), effective_at, row["reason_code"])

    def claim_command(self, request: StaffLifecycleApplyRequest, command_fingerprint: PreviewFingerprint) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute("INSERT IGNORE INTO application_command_claims (idempotency_key,command_family,aggregate_identity,command_fingerprint,correlation_id) VALUES (%s,%s,%s,%s,%s)", (request.idempotency_key.value, "staff_lifecycle", str(request.staff_id), command_fingerprint.value, request.correlation_id.value))
            if cursor.rowcount == 1:
                return
            cursor.execute("SELECT command_family,aggregate_identity,command_fingerprint FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE", (request.idempotency_key.value,))
            claim = cursor.fetchone()
        if claim is None or claim["command_family"] != "staff_lifecycle" or claim["aggregate_identity"] != str(request.staff_id) or claim["command_fingerprint"] != command_fingerprint.value:
            raise ValueError("idempotency_mismatch")

    def load_receipt(self, key: IdempotencyKey):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT command_fingerprint,preview_fingerprint,staff_id,resulting_state,resulting_version FROM staff_lifecycle_apply_receipts WHERE idempotency_key=%s FOR UPDATE", (key.value,))
            row = cursor.fetchone()
        if row is None:
            return None
        receipt = StaffLifecycleReceipt(int(row["staff_id"]), StaffLifecycleState(str(row["resulting_state"])), int(row["resulting_version"]), PreviewFingerprint(str(row["preview_fingerprint"])))
        return PreviewFingerprint(str(row["command_fingerprint"])), receipt

    def persist(self, request: StaffLifecycleApplyRequest, preview: StaffLifecyclePreview, receipt: StaffLifecycleReceipt, command_fingerprint: PreviewFingerprint) -> None:
        candidate = preview.candidate
        with self._connection.cursor() as cursor:
            event_id = None
            if not candidate.is_noop:
                effective_at = candidate.effective_at.astimezone(TAIPEI_TIME_ZONE).replace(tzinfo=None)
                cursor.execute("INSERT INTO staff_lifecycle_states (staff_id,lifecycle_state,aggregate_version,effective_at,reason_code,updated_by) VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE lifecycle_state=VALUES(lifecycle_state),aggregate_version=VALUES(aggregate_version),effective_at=VALUES(effective_at),reason_code=VALUES(reason_code),updated_by=VALUES(updated_by)", (receipt.staff_id, receipt.state.value, receipt.version, effective_at, candidate.reason_code, request.actor.actor_id))
                cursor.execute("INSERT INTO staff_lifecycle_events (staff_id,event_type,before_state,resulting_state,effective_at,reason_code,expected_version,resulting_version,actor,correlation_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (receipt.staff_id, "retired" if request.transition.value == "retire" else "reactivated", candidate.before.state.value, receipt.state.value, effective_at, candidate.reason_code, candidate.before.version, receipt.version, request.actor.actor_id, request.correlation_id.value))
                event_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO staff_lifecycle_apply_receipts (idempotency_key,command_fingerprint,preview_fingerprint,staff_id,resulting_state,resulting_version,event_id) VALUES (%s,%s,%s,%s,%s,%s,%s)", (request.idempotency_key.value, command_fingerprint.value, preview.fingerprint.value, receipt.staff_id, receipt.state.value, receipt.version, event_id))
