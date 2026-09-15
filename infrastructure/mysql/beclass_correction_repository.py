"""MySQL persistence for effective Client BeClass corrections."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from domains.case_import.order_information import project_order_information
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.case_import.beclass_correction_workflow import (
    BeClassCorrectionSnapshot,
    allows_manual_beclass_source,
)


_SOURCE_FIELDS = (
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
                "SELECT case_no,status,"
                "EXISTS(SELECT 1 FROM order_service_data_locks l WHERE l.case_no=orders.case_no) "
                "AS service_data_locked FROM orders WHERE case_no=%s" + suffix,
                (case_no,),
            )
            order = cursor.fetchone()
            if order is None:
                return None
            cursor.execute(
                "SELECT id AS beclass_record_id,bound_case_no AS case_no,record_origin,survey_details," + ",".join(_SOURCE_FIELDS)
                + " FROM beclass_records WHERE bound_case_no=%s ORDER BY id LIMIT 2" + suffix,
                (case_no,),
            )
            sources = tuple(cursor.fetchall() or ())
            if not sources:
                if not allows_manual_beclass_source(order.get("status")):
                    return None
                return {
                    "beclass_record_id": None,
                    "case_no": str(order["case_no"]),
                    "aggregate_version": 0,
                    "original": {field: None for field in (*_SOURCE_FIELDS, "multi_birth_count")},
                    "corrections": {},
                    "source_kind": "admin_manual",
                    "financial_fields_locked": _financial_fields_locked(order),
                }
            if len(sources) != 1:
                raise ValueError("beclass_binding_ambiguous")
            source = sources[0]
            cursor.execute(
                "SELECT aggregate_version,effective_values_json FROM beclass_record_correction_states "
                "WHERE beclass_record_id=%s" + suffix,
                (int(source["beclass_record_id"]),),
            )
            state = cursor.fetchone()
        order_information = project_order_information(source.get("survey_details"))
        original = {field: source.get(field) for field in _SOURCE_FIELDS}
        birth_count = order_information.values.get("multi_birth_count")
        original["multi_birth_count"] = (
            birth_count
            if order_information.issues.get("multi_birth_count") is None
            and isinstance(birth_count, str)
            else None
        )
        return {
            "beclass_record_id": int(source["beclass_record_id"]),
            "case_no": str(source["case_no"]),
            "aggregate_version": int((state or {}).get("aggregate_version") or 0),
            "original": original,
            "corrections": _decode_json((state or {}).get("effective_values_json"), {}),
            "source_kind": str(source.get("record_origin") or "imported"),
            "financial_fields_locked": _financial_fields_locked(order),
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

    def persist(self, *, snapshot: BeClassCorrectionSnapshot, after: Mapping[str, str | None], actor: ActorContext, reason: str, key: IdempotencyKey, correlation_id: CorrelationId) -> tuple[int, int, int]:
        resulting_version = snapshot.version + 1
        with self._connection.cursor() as cursor:
            beclass_record_id = snapshot.beclass_record_id
            if beclass_record_id is None:
                if snapshot.source_kind != "admin_manual":
                    raise ValueError("beclass_manual_source_invalid")
                cursor.execute(
                    "INSERT INTO beclass_records (bound_case_no,record_origin) VALUES (%s,'admin_manual')",
                    (snapshot.case_no,),
                )
                beclass_record_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO beclass_record_correction_states "
                "(beclass_record_id,aggregate_version,effective_values_json,updated_by) "
                "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                "aggregate_version=VALUES(aggregate_version),effective_values_json=VALUES(effective_values_json),"
                "updated_by=VALUES(updated_by)",
                (
                    beclass_record_id,
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
                    beclass_record_id,
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
            correction_event_id = int(cursor.lastrowid)
        return beclass_record_id, resulting_version, correction_event_id

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


def _financial_fields_locked(order: Mapping[str, Any]) -> bool:
    return bool(
        order.get("service_data_locked")
        or str(order.get("status") or "")
        in {
            "服務中", "訂單完成", "訂單取消",
            "歷史訂單－服務中", "歷史訂單－服務完成", "歷史訂單－帳務完成",
        }
    )


__all__ = ["MySqlBeClassCorrectionRepository"]
