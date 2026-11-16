"""MySQL adapter for the Client-owned profile change workflow."""

from __future__ import annotations

import json
from typing import Any, Mapping


class MySqlClientProfileRepository:
    """Keep Client root writes behind one typed repository boundary."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_email_fill_target(self, case_no: str, *, for_update: bool = False) -> dict[str, Any] | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT c.id AS client_id,c.client_profile_version,c.email FROM orders o "
                           "JOIN clients c ON c.id=o.client_id WHERE o.case_no=%s" + suffix, (case_no,))
            return cursor.fetchone()

    def load_profile(self, client_id: int, *, for_update: bool = False) -> dict[str, Any] | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id AS client_id,client_profile_version,name,gender,phone,email,city,address,"
                "residence_type,delivery_type,baby_info,notes,due_month,reject_reason,service_type,admin_notes,identity_status FROM clients WHERE id=%s" + suffix,
                (client_id,),
            )
            return cursor.fetchone()

    def load_profile_by_case_no(self, case_no: str, *, for_update: bool = False) -> dict[str, Any] | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.id AS client_id,o.case_no,c.client_profile_version,c.name,c.gender,c.phone,c.email,c.city,c.address,"
                "c.residence_type,c.delivery_type,c.baby_info,c.notes,c.due_month,c.reject_reason,c.service_type,c.admin_notes,"
                "c.identity_status,o.status AS order_status,o.actual_start_date,o.actual_end_date FROM orders o "
                "JOIN clients c ON c.id=o.client_id WHERE o.case_no=%s" + suffix,
                (case_no,),
            )
            return cursor.fetchone()

    def prepare_identity_change(self, case_no: str, client_id: int, *, lock: bool):
        from infrastructure.mysql.order_terms_read_model import select_order
        from infrastructure.mysql.pricing_configuration_repository import (
            MySqlPricingConfigurationRepository, citizen_reclassification_terms,
        )

        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT case_no FROM orders WHERE client_id=%s ORDER BY case_no LIMIT 2"
                + (" FOR UPDATE" if lock else ""), (client_id,),
            )
            if len(cursor.fetchall()) != 1:
                raise ValueError("profile_identity_shared_client_conflict")
            order = select_order(cursor, case_no, lock=lock)
            cursor.execute(
                "SELECT case_no FROM client_payment_terms WHERE case_no=%s"
                + (" FOR UPDATE" if lock else ""), (case_no,),
            )
            if cursor.fetchone() is None and order["pricing_override_event_id"] is None:
                return None
            terms = citizen_reclassification_terms(cursor, order, lock=lock)
        pricing = MySqlPricingConfigurationRepository(self._connection)
        return pricing.case(case_no, lock=lock), terms

    def apply_identity_pricing(self, prepared, *, actor_id: str, reason: str, key: str):
        from infrastructure.mysql.pricing_configuration_repository import MySqlPricingConfigurationRepository

        if prepared is not None:
            facts, terms = prepared
            MySqlPricingConfigurationRepository(self._connection).save_case(
                facts, terms, actor_id, reason, key, identity_reclassification=True,
            )

    def claim_admin_command(self, *, case_no: str, idempotency_key: str, command_fingerprint: str, correlation_id: str) -> None:
        family = "client_profile_admin_change/v1"
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO application_command_claims "
                "(idempotency_key,command_family,aggregate_identity,command_fingerprint,correlation_id) "
                "VALUES (%s,%s,%s,%s,%s)",
                (idempotency_key, family, case_no, command_fingerprint, correlation_id),
            )
            if cursor.rowcount == 1:
                return
            cursor.execute(
                "SELECT command_family,aggregate_identity,command_fingerprint "
                "FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE",
                (idempotency_key,),
            )
            claim = cursor.fetchone()
        if (
            claim is None
            or claim["command_family"] != family
            or claim["aggregate_identity"] != case_no
            or claim["command_fingerprint"] != command_fingerprint
        ):
            raise RuntimeError("idempotency_mismatch")

    def find_admin_receipt(self, key: str, *, for_update: bool = False) -> dict[str, Any] | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT request_fingerprint AS command_fingerprint,preview_fingerprint,result_snapshot "
                "FROM admin_command_receipts WHERE command_family=%s AND idempotency_key=%s" + suffix,
                ("client_profile_admin_change/v1", key),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return {**row, "result": _decode_json(row.get("result_snapshot"), {})}

    def apply_admin_change(self, *, client_id: int, expected_version: int, before: Mapping[str, str], requested: Mapping[str, str], actor_id: str, reason: str, idempotency_key: str, correlation_id: str) -> int:
        fields = tuple(sorted(requested))
        assignments = ",".join(f"{field}=%s" for field in fields)
        resulting_version = expected_version + 1
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE clients SET " + assignments + ",client_profile_version=%s "
                "WHERE id=%s AND client_profile_version=%s",
                tuple(requested[field] for field in fields)
                + (resulting_version, client_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("client_profile_version_stale")
            cursor.execute(
                "INSERT INTO client_profile_admin_change_events "
                "(client_id,expected_version,resulting_version,actor_id,reason,idempotency_key,"
                "correlation_id,before_values_json,after_values_json) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    client_id, expected_version, resulting_version, actor_id, reason,
                    idempotency_key, correlation_id, _json(before), _json(requested),
                ),
            )
        return resulting_version

    def save_admin_receipt(self, *, idempotency_key: str, command_fingerprint: str, preview_fingerprint: str, actor_id: str, reason: str, result: Mapping[str, Any]) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO admin_command_receipts "
                "(command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    "client_profile_admin_change/v1", idempotency_key,
                    command_fingerprint, preview_fingerprint, actor_id, reason, _json(result),
                ),
            )


def _decode_json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return default
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return default
    return decoded


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
