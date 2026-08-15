"""
File: client_beclass_workbook_import_repository.py
Description: 保存 Client BeClass workbook claim、receipt 與受鎖定的來源根事實寫入。
"""

from __future__ import annotations

import json
from hashlib import sha256


class ClientBeClassWorkbookImportRepository:
    _WORKBOOK_FAMILY = "client_beclass_workbook_ingest"
    _ROW_FAMILY = "client_beclass_row_intake"
    _SOURCE_COLUMNS = (
        "query_no", "created_at", "name", "email", "phone", "tel", "ext",
        "city", "zip_code", "address", "refund_bank_code",
        "refund_account_no", "admin_notes", "birth_date", "survey_details",
    )

    def __init__(self, connection) -> None:
        self.connection = connection

    def acquire_lock(self, key: str) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s,5) AS acquired", (self._lock_name(key),))
            row = cursor.fetchone()
        return bool(row and row["acquired"] == 1)

    def release_lock(self, key: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (self._lock_name(key),))

    def load_workbook_receipt(self, key: str):
        return self._load_receipt(self._WORKBOOK_FAMILY, key)

    def load_row_receipt(self, key: str):
        return self._load_receipt(self._ROW_FAMILY, key)

    def source_state(self, payload: dict[str, object]) -> str:
        query_no = payload.get("query_no")
        if not query_no:
            return "absent"
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {','.join(self._SOURCE_COLUMNS)} "
                "FROM beclass_records WHERE query_no=%s LIMIT 1",
                (query_no,),
            )
            stored = cursor.fetchone()
        if stored is None:
            return "absent"
        return "exact" if _comparable_source(stored) == _comparable_source(payload) else "conflict"

    def claim_workbook(self, key: str, fingerprint: str, correlation_id: str) -> str:
        return self._claim(key, self._WORKBOOK_FAMILY, fingerprint, correlation_id)

    def claim_row(self, key: str, fingerprint: str, correlation_id: str) -> str:
        outcome = self._claim(key, self._ROW_FAMILY, fingerprint, correlation_id)
        if outcome == "conflict":
            raise RuntimeError("client_beclass_row_claim_conflict")
        return outcome

    def resolve_unique_client_case(self, name: str | None, phone: str | None):
        if not name or not phone:
            return None
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT client.id,client.case_no FROM clients client "
                "JOIN orders order_root ON order_root.client_id=client.id "
                "WHERE client.name=%s AND client.phone=%s "
                "ORDER BY client.id LIMIT 2 FOR UPDATE",
                (name, phone),
            )
            rows = cursor.fetchall()
        return rows[0] if len(rows) == 1 else None

    def create_bound_source_if_absent(self, payload: dict[str, object], client_case) -> int | None:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT id FROM beclass_records WHERE query_no=%s FOR UPDATE", (payload["query_no"],))
            if cursor.fetchone() is not None:
                return None
            bound_payload = {**payload, "client_id": int(client_case["id"]), "bound_case_no": str(client_case["case_no"])}
            columns = tuple(sorted(bound_payload))
            cursor.execute(f"INSERT INTO beclass_records ({','.join(f'`{column}`' for column in columns)}) VALUES ({','.join(['%s'] * len(columns))})", tuple(bound_payload[column] for column in columns))
            if cursor.rowcount != 1:
                raise RuntimeError("client_beclass_root_insert_failed")
            return int(cursor.lastrowid)

    def require_matching_client_root(self, receipt) -> None:
        root_id = receipt.get("root_id")
        if root_id is None:
            return
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT id FROM beclass_records WHERE id=%s FOR UPDATE", (root_id,))
            if cursor.fetchone() is None:
                raise RuntimeError("client_beclass_replay_root_drift")

    def save_workbook_receipt(self, key: str, fingerprint: str, preview: str, actor: str, result: dict[str, object]) -> None:
        self._save_receipt(self._WORKBOOK_FAMILY, key, fingerprint, preview, actor, result, None)

    def save_row_receipt(self, key: str, fingerprint: str, root_id: int | None, outcome: str, review_identity: str | None, actor: str) -> None:
        self._save_receipt(self._ROW_FAMILY, key, fingerprint, fingerprint, actor, {"outcome": outcome, "root_id": root_id, "review_identity": review_identity}, root_id)

    def _load_receipt(self, family: str, key: str):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT request_fingerprint,result_snapshot FROM admin_command_receipts WHERE command_family=%s AND idempotency_key=%s FOR UPDATE", (family, key))
            row = cursor.fetchone()
        if row is not None:
            row["root_id"] = json.loads(row["result_snapshot"]).get("root_id")
        return row

    def _claim(self, key: str, family: str, fingerprint: str, correlation_id: str) -> str:
        with self.connection.cursor() as cursor:
            cursor.execute("INSERT IGNORE INTO application_command_claims (idempotency_key,command_family,aggregate_identity,command_fingerprint,correlation_id) VALUES (%s,%s,%s,%s,%s)", (key, family, fingerprint, fingerprint, correlation_id))
            if cursor.rowcount == 1:
                return "created"
            cursor.execute("SELECT command_family,command_fingerprint FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE", (key,))
            row = cursor.fetchone()
        return "resume" if row and row["command_family"] == family and row["command_fingerprint"] == fingerprint else "conflict"

    def _save_receipt(self, family: str, key: str, fingerprint: str, preview: str, actor: str, result: dict[str, object], root_id: int | None) -> None:
        del root_id
        with self.connection.cursor() as cursor:
            cursor.execute("INSERT INTO admin_command_receipts (command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s)", (family, key, fingerprint, preview, actor, "Client BeClass workbook intake", json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))))

    @staticmethod
    def _lock_name(key: str) -> str:
        return f"client-beclass:{sha256(key.encode()).hexdigest()[:48]}"


def _comparable_source(payload: dict[str, object]) -> dict[str, object]:
    result = {
        column: _comparable_value(column, payload.get(column))
        for column in ClientBeClassWorkbookImportRepository._SOURCE_COLUMNS
    }
    return result


def _comparable_value(column: str, value: object) -> object:
    if value is None:
        return None
    if column == "birth_date":
        return str(value)
    if column != "survey_details":
        return value
    parsed = json.loads(value) if isinstance(value, str) else value
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
