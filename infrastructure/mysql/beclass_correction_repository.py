"""MySQL persistence for effective Client BeClass corrections."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.case_import.beclass_correction_workflow import BeClassCorrectionSnapshot


_FIELDS = (
    "name", "email", "phone", "tel", "ext", "city", "zip_code", "address", "admin_notes",
)
_FAMILY = "client_beclass_correction/v1"


class MySqlBeClassCorrectionRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load(self, case_no: str, *, for_update: bool) -> Mapping[str, Any] | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id AS beclass_record_id,bound_case_no AS case_no," + ",".join(_FIELDS)
                + " FROM beclass_records WHERE bound_case_no=%s ORDER BY id LIMIT 2" + suffix,
                (case_no,),
            )
            sources = tuple(cursor.fetchall() or ())
            if not sources:
                return None
            if len(sources) != 1:
                raise ValueError("beclass_binding_ambiguous")
            source = sources[0]
            cursor.execute(
                "SELECT aggregate_version,effective_values_json FROM beclass_record_correction_states "
                "WHERE beclass_record_id=%s" + suffix,
                (int(source["beclass_record_id"]),),
            )
            state = cursor.fetchone()
        return {
            "beclass_record_id": int(source["beclass_record_id"]),
            "case_no": str(source["case_no"]),
            "aggregate_version": int((state or {}).get("aggregate_version") or 0),
            "original": {field: source.get(field) for field in _FIELDS},
            "corrections": _decode_json((state or {}).get("effective_values_json"), {}),
        }

    def claim(self, *, case_no: str, key: IdempotencyKey, command_fingerprint: PreviewFingerprint, correlation_id: CorrelationId) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO application_command_claims "
                "(idempotency_key,command_family,aggregate_identity,command_fingerprint,correlation_id) "
                "VALUES (%s,%s,%s,%s,%s)",
                (key.value, _FAMILY, case_no, command_fingerprint.value, correlation_id.value),
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
            or claim["aggregate_identity"] != case_no
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
        return {
            "request_fingerprint": str(row["request_fingerprint"]),
            "result": _decode_json(row["result_snapshot"], {}),
        }

    def persist(self, *, snapshot: BeClassCorrectionSnapshot, after: Mapping[str, str | None], actor: ActorContext, reason: str, key: IdempotencyKey, correlation_id: CorrelationId) -> int:
        resulting_version = snapshot.version + 1
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO beclass_record_correction_states "
                "(beclass_record_id,aggregate_version,effective_values_json,updated_by) "
                "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                "aggregate_version=VALUES(aggregate_version),effective_values_json=VALUES(effective_values_json),"
                "updated_by=VALUES(updated_by)",
                (
                    snapshot.beclass_record_id,
                    resulting_version,
                    _json(after),
                    actor.actor_id,
                ),
            )
            cursor.execute(
                "INSERT INTO beclass_record_correction_events "
                "(beclass_record_id,expected_version,resulting_version,actor_id,reason,idempotency_key,"
                "correlation_id,before_values_json,after_values_json) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    snapshot.beclass_record_id,
                    snapshot.version,
                    resulting_version,
                    actor.actor_id,
                    reason,
                    key.value,
                    correlation_id.value,
                    _json(snapshot.effective),
                    _json(after),
                ),
            )
        return resulting_version

    def save_receipt(self, *, key: IdempotencyKey, command_fingerprint: PreviewFingerprint, preview_fingerprint: PreviewFingerprint, actor: ActorContext, reason: str, result: Mapping[str, Any]) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO admin_command_receipts "
                "(command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    _FAMILY,
                    key.value,
                    command_fingerprint.value,
                    preview_fingerprint.value,
                    actor.actor_id,
                    reason,
                    _json(result),
                ),
            )


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_json(value: Any, default: Any) -> Any:
    if isinstance(value, dict):
        return value
    if value is None:
        return default
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return default
    return decoded if isinstance(decoded, dict) else default


__all__ = ["MySqlBeClassCorrectionRepository"]
