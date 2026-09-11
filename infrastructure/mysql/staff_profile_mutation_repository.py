"""MySQL adapter for Staff personal/contact owner mutations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from domains.staff.profile import STAFF_PROFILE_FIELDS
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.staff.profile_workflow import StaffProfileSnapshot


_FAMILY = "staff_profile_change/v1"


class MySqlStaffProfileMutationRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load(self, staff_id: int, *, for_update: bool) -> Mapping[str, Any] | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id AS staff_id,staff_profile_version," + ",".join(STAFF_PROFILE_FIELDS)
                + " FROM staff WHERE id=%s" + suffix,
                (staff_id,),
            )
            return cursor.fetchone()

    def claim(self, *, staff_id: int, key: IdempotencyKey, command_fingerprint: PreviewFingerprint, correlation_id: CorrelationId) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO application_command_claims "
                "(idempotency_key,command_family,aggregate_identity,command_fingerprint,correlation_id) "
                "VALUES (%s,%s,%s,%s,%s)",
                (key.value, _FAMILY, str(staff_id), command_fingerprint.value, correlation_id.value),
            )
            if cursor.rowcount == 1:
                return
            cursor.execute(
                "SELECT command_family,aggregate_identity,command_fingerprint "
                "FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE",
                (key.value,),
            )
            claim = cursor.fetchone()
        if (
            claim is None
            or claim["command_family"] != _FAMILY
            or claim["aggregate_identity"] != str(staff_id)
            or claim["command_fingerprint"] != command_fingerprint.value
        ):
            raise ValueError("idempotency_mismatch")

    def load_receipt(self, key: IdempotencyKey, *, for_update: bool) -> Mapping[str, Any] | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT request_fingerprint,result_snapshot FROM admin_command_receipts "
                "WHERE command_family=%s AND idempotency_key=%s" + suffix,
                (_FAMILY, key.value),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return {"request_fingerprint": row["request_fingerprint"], "result": _decode(row["result_snapshot"])}

    def persist(self, *, snapshot: StaffProfileSnapshot, changes: Mapping[str, str | None], actor: ActorContext, reason: str, key: IdempotencyKey, correlation_id: CorrelationId) -> int:
        fields = tuple(sorted(changes))
        resulting_version = snapshot.version + 1
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE staff SET " + ",".join(f"{field}=%s" for field in fields)
                + ",staff_profile_version=%s WHERE id=%s AND staff_profile_version=%s",
                tuple(changes[field] for field in fields)
                + (resulting_version, snapshot.staff_id, snapshot.version),
            )
            if cursor.rowcount != 1:
                raise ValueError("staff_profile_stale_version")
            cursor.execute(
                "INSERT INTO staff_profile_change_events "
                "(staff_id,expected_version,resulting_version,actor_id,reason,idempotency_key,"
                "correlation_id,before_values_json,after_values_json) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    snapshot.staff_id,
                    snapshot.version,
                    resulting_version,
                    actor.actor_id,
                    reason,
                    key.value,
                    correlation_id.value,
                    _json({field: snapshot.values.get(field) for field in fields}),
                    _json(changes),
                ),
            )
        return resulting_version

    def save_receipt(self, *, key: IdempotencyKey, command_fingerprint: PreviewFingerprint, preview_fingerprint: PreviewFingerprint, actor: ActorContext, reason: str, result: Mapping[str, Any]) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO admin_command_receipts "
                "(command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (_FAMILY, key.value, command_fingerprint.value, preview_fingerprint.value,
                 actor.actor_id, reason, _json(result)),
            )


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise ValueError("staff_profile_receipt_invalid")
    return decoded


__all__ = ["MySqlStaffProfileMutationRepository"]
