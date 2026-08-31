"""
File: client_beclass_workbook_import_repository.py
Description: 保存 Client BeClass workbook claim、receipt 與受鎖定的來源根事實寫入。
"""

from __future__ import annotations

import json
from hashlib import sha256

from domains.case_import.client_beclass_binding import classify_client_case_binding
from subsystems.case_import.pairing_current_facts import (
    CasePairingAcceptedLineage,
    CasePairingAcceptedMapping,
)


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

    def bound_source_for_query(self, query_no: str):
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,bound_case_no FROM beclass_records "
                "WHERE query_no=%s LIMIT 1 FOR UPDATE",
                (query_no,),
            )
            row = cursor.fetchone()
        if row is None or row["bound_case_no"] is None:
            return None
        return {"root_id": int(row["id"]), "case_no": str(row["bound_case_no"])}

    def bound_case_no_for_root(self, root_id: int | None) -> str | None:
        if root_id is None:
            return None
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT bound_case_no FROM beclass_records WHERE id=%s FOR UPDATE",
                (root_id,),
            )
            row = cursor.fetchone()
        return None if row is None or row["bound_case_no"] is None else str(row["bound_case_no"])

    def bound_case_nos_for_workbook(self, digest: str) -> tuple[str, ...]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT result_snapshot FROM admin_command_receipts "
                "WHERE command_family=%s AND idempotency_key LIKE %s",
                (self._ROW_FAMILY, f"client-beclass-workbook:{digest}:row:%"),
            )
            root_ids = tuple(
                sorted(
                    {
                        int(root_id)
                        for row in cursor.fetchall()
                        if (root_id := json.loads(row["result_snapshot"]).get("root_id"))
                        is not None
                    }
                )
            )
            if not root_ids:
                return ()
            placeholders = ",".join(["%s"] * len(root_ids))
            cursor.execute(
                "SELECT bound_case_no FROM beclass_records "
                f"WHERE id IN ({placeholders}) AND bound_case_no IS NOT NULL "
                "ORDER BY bound_case_no FOR UPDATE",
                root_ids,
            )
            return tuple(
                sorted({str(row["bound_case_no"]) for row in cursor.fetchall()})
            )

    def claim_workbook(self, key: str, fingerprint: str, correlation_id: str) -> str:
        return self._claim(key, self._WORKBOOK_FAMILY, fingerprint, correlation_id)

    def claim_row(self, key: str, fingerprint: str, correlation_id: str) -> str:
        outcome = self._claim(key, self._ROW_FAMILY, fingerprint, correlation_id)
        if outcome == "conflict":
            raise RuntimeError("client_beclass_row_claim_conflict")
        return outcome

    def resolve_unique_client_case(self, name: str | None, phone: str | None):
        resolution = self.resolve_client_case_binding(name, phone)
        return resolution.bound_root() if resolution.issue_code is None else None

    def resolve_client_case_binding(
        self, name: str | None, phone: str | None, *, for_update: bool = True
    ):
        if not name or not phone:
            return classify_client_case_binding((), ())
        lock_clause = " FOR UPDATE" if for_update else ""
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT client.id FROM clients client "
                "WHERE client.name=%s AND client.phone=%s "
                f"ORDER BY client.id{lock_clause}",
                (name, phone),
            )
            client_ids = tuple(int(row["id"]) for row in cursor.fetchall())
            if len(client_ids) != 1:
                return classify_client_case_binding(client_ids, ())
            cursor.execute(
                "SELECT case_no FROM orders WHERE client_id=%s "
                f"ORDER BY case_no{lock_clause}",
                (client_ids[0],),
            )
            case_nos = tuple(str(row["case_no"]) for row in cursor.fetchall())
        return classify_client_case_binding(client_ids, case_nos)

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

    def save_workbook_receipt(
        self,
        key: str,
        fingerprint: str,
        preview: str,
        actor: str,
        result: dict[str, object],
        *,
        original_review_identity: str | None = None,
    ) -> None:
        self._save_receipt(
            self._WORKBOOK_FAMILY,
            key,
            fingerprint,
            preview,
            actor,
            result,
            None,
            original_review_identity=original_review_identity,
        )

    def save_row_receipt(self, key: str, fingerprint: str, root_id: int | None, outcome: str, review_identity: str | None, actor: str) -> str:
        return self._save_receipt(self._ROW_FAMILY, key, fingerprint, fingerprint, actor, {"outcome": outcome, "root_id": root_id, "review_identity": review_identity}, root_id)

    def append_case_pairing_lineage(
        self,
        original_review_identity: str,
        accepted_source_event_identity: str,
        accepted_result_identity: str,
        accepted_root_id: int | None = None,
    ) -> None:
        """Persist exact cross-source lineage in the caller-owned transaction.

        ``case_import_pairing_accepted_lineage`` is an additive schema
        successor owned by Case Import. It is intentionally not represented
        in ``admin_command_receipts.result_snapshot``: that generic payload is
        replay evidence, not the lineage source of truth. A missing accepted
        root is retained as incomplete lineage and therefore cannot close the
        pairing predicate during readback.
        """
        lineage = CasePairingAcceptedLineage(
            original_review_identity,
            accepted_source_event_identity,
            accepted_result_identity,
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT original_review_identity,accepted_source_event_identity,"
                "accepted_result_identity,accepted_root_id "
                "FROM case_import_pairing_accepted_lineage "
                "WHERE original_review_identity=%s OR accepted_result_identity=%s "
                "FOR UPDATE",
                (
                    lineage.original_review_identity,
                    lineage.accepted_result_identity,
                ),
            )
            rows = tuple(cursor.fetchall() or ())
            if rows:
                if len(rows) != 1 or not _same_pairing_lineage(
                    rows[0], lineage, accepted_root_id
                ):
                    raise RuntimeError("case_pairing_lineage_conflict")
                return
            cursor.execute(
                "INSERT INTO case_import_pairing_accepted_lineage "
                "(original_review_identity,accepted_source_event_identity,"
                "accepted_result_identity,accepted_root_id) VALUES (%s,%s,%s,%s)",
                (
                    lineage.original_review_identity,
                    lineage.accepted_source_event_identity,
                    lineage.accepted_result_identity,
                    accepted_root_id,
                ),
            )

    def read_accepted_mapping(self, original_review_identity: str):
        """Read one exact lineage row and fresh accepted-root ownership facts."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT lineage.original_review_identity,"
                "lineage.accepted_source_event_identity,"
                "lineage.accepted_result_identity,"
                "source.bound_case_no,"
                "(SELECT COUNT(*) FROM orders WHERE case_no=source.bound_case_no) "
                "AS hcm_count "
                "FROM case_import_pairing_accepted_lineage lineage "
                "LEFT JOIN beclass_records source "
                "ON source.id=lineage.accepted_root_id "
                "WHERE lineage.original_review_identity=%s FOR UPDATE",
                (original_review_identity,),
            )
            rows = cursor.fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise RuntimeError("case_pairing_lineage_conflict")
        row = rows[0]
        return CasePairingAcceptedMapping(
            CasePairingAcceptedLineage(
                row["original_review_identity"],
                row["accepted_source_event_identity"],
                row["accepted_result_identity"],
            ),
            None if row["bound_case_no"] is None else str(row["bound_case_no"]),
            int(row["hcm_count"] or 0),
        )

    def _load_receipt(self, family: str, key: str):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT id,request_fingerprint,result_snapshot FROM admin_command_receipts WHERE command_family=%s AND idempotency_key=%s FOR UPDATE", (family, key))
            row = cursor.fetchone()
        if row is not None:
            result = json.loads(row["result_snapshot"])
            row["root_id"] = result.get("root_id")
            if family == self._ROW_FAMILY and result.get("outcome") in {
                "created",
                "existing_source",
            }:
                row["accepted_result_identity"] = (
                    f"admin_command_receipt:{int(row['id'])}"
                )
        return row

    def _claim(self, key: str, family: str, fingerprint: str, correlation_id: str) -> str:
        with self.connection.cursor() as cursor:
            cursor.execute("INSERT IGNORE INTO application_command_claims (idempotency_key,command_family,aggregate_identity,command_fingerprint,correlation_id) VALUES (%s,%s,%s,%s,%s)", (key, family, fingerprint, fingerprint, correlation_id))
            if cursor.rowcount == 1:
                return "created"
            cursor.execute("SELECT command_family,command_fingerprint FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE", (key,))
            row = cursor.fetchone()
        return "resume" if row and row["command_family"] == family and row["command_fingerprint"] == fingerprint else "conflict"

    def _save_receipt(
        self,
        family: str,
        key: str,
        fingerprint: str,
        preview: str,
        actor: str,
        result: dict[str, object],
        root_id: int | None,
        *,
        original_review_identity: str | None = None,
    ) -> str:
        del root_id
        persisted_result = dict(result)
        if original_review_identity is not None:
            persisted_result["_lineage_original_review_identity"] = original_review_identity
        with self.connection.cursor() as cursor:
            cursor.execute("INSERT INTO admin_command_receipts (command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s)", (family, key, fingerprint, preview, actor, "Client BeClass workbook intake", json.dumps(persisted_result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))))
            receipt_id = int(cursor.lastrowid or 0)
        if receipt_id <= 0:
            raise RuntimeError("client_beclass_receipt_identity_missing")
        return f"admin_command_receipt:{receipt_id}"

    @staticmethod
    def _lock_name(key: str) -> str:
        return f"client-beclass:{sha256(key.encode()).hexdigest()[:48]}"


def _comparable_source(payload: dict[str, object]) -> dict[str, object]:
    result = {
        column: _comparable_value(column, payload.get(column))
        for column in ClientBeClassWorkbookImportRepository._SOURCE_COLUMNS
    }
    return result


def _same_pairing_lineage(row, lineage, accepted_root_id) -> bool:
    stored_root_id = row.get("accepted_root_id")
    return (
        str(row.get("original_review_identity"))
        == lineage.original_review_identity
        and str(row.get("accepted_source_event_identity"))
        == lineage.accepted_source_event_identity
        and str(row.get("accepted_result_identity"))
        == lineage.accepted_result_identity
        and (
            None if stored_root_id is None else int(stored_root_id)
        )
        == accepted_root_id
    )


def _comparable_value(column: str, value: object) -> object:
    if value is None:
        return None
    if column == "birth_date":
        return str(value)
    if column != "survey_details":
        return value
    parsed = json.loads(value) if isinstance(value, str) else value
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
