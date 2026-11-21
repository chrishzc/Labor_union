"""Finance Import archive adapter: no second copy of canonical bank facts."""
import hashlib
import json

from subsystems.finance_import.query import BANK_CASE_PROOFS_SQL
from subsystems.finance_import.statement_archive import (
    StatementCommandConflict, StatementCommandReceipt, StatementExportRow,
)




class MySqlStatementArchiveRepository:
    def __init__(self, connection):
        self.connection = connection

    def export_rows(self):
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT b.id,b.format_id,b.raw_payload,p.case_no FROM finance_import_rows b JOIN ("
                + BANK_CASE_PROOFS_SQL + ") p ON p.row_id=b.id JOIN orders r ON r.case_no=p.case_no "
                "LEFT JOIN finance_statement_exclusions x ON x.finance_import_row_id=b.id "
                "WHERE x.finance_import_row_id IS NULL ORDER BY b.id,p.case_no"
            )
            canonical = cursor.fetchall()
            by_id = {}
            for row in canonical:
                entry = by_id.setdefault(int(row["id"]), {"bank": row["format_id"], "fields": _object(row["raw_payload"]), "cases": []})
                if row["case_no"] not in entry["cases"]:
                    entry["cases"].append(row["case_no"])
            purposes = _load_row_purposes(cursor, tuple(by_id.keys()), by_id) if by_id else {}
        result = [
            StatementExportRow(
                f"bank:{identity}",
                row["bank"],
                "reconciled",
                tuple(row["cases"]),
                tuple(row["fields"].items()),
                purposes.get(identity, "已核銷款項"),
            )
            for identity, row in by_id.items()
        ]
        return tuple(result)

    def legacy_reference_rows(self):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT id,fields FROM finance_manual_statements ORDER BY id")
            rows = cursor.fetchall()
        return tuple(StatementExportRow(f"manual:{row['id']}", "manual", "reference", (),
                                       tuple(_object(row["fields"]).items())) for row in rows)

    def exclude_duplicate(self, candidate, kept, key, actor):
        command = {"operation": "exclude", "candidate": candidate, "kept": kept, "actor": actor}

        def write(cursor):
            self._require_existing(kept)
            if not candidate.startswith("bank:") or not candidate[5:].isdigit():
                raise ValueError("only_later_bank_candidate_can_be_excluded")
            identity = int(candidate[5:])
            cursor.execute("SELECT kept_identity FROM finance_statement_exclusions WHERE finance_import_row_id=%s", (identity,))
            previous = cursor.fetchone()
            if previous:
                if previous["kept_identity"] != kept:
                    raise StatementCommandConflict("duplicate_retained_source_changed")
                return StatementCommandReceipt(kept, 0, 1)
            self._require_existing(candidate)
            if kept.startswith("bank:") and int(kept[5:]) >= identity:
                raise ValueError("keep_existing_earlier_statement")
            cursor.execute("SELECT 1 FROM finance_statement_exclusions WHERE kept_identity=%s LIMIT 1", (candidate,))
            if cursor.fetchone():
                raise StatementCommandConflict("retained_statement_is_referenced")
            cursor.execute(
                "INSERT INTO finance_statement_exclusions(finance_import_row_id,kept_identity,actor) VALUES (%s,%s,%s)",
                (identity, kept, actor),
            )
            return StatementCommandReceipt(kept, 0, 1)

        return self._command(command, key, actor, write)

    def _require_existing(self, identity):
        if identity not in {row.identity for row in self.export_rows()}:
            raise StatementCommandConflict("successful_statement_not_found")

    def _command(self, command, key, actor, write):
        digest = hashlib.sha256(json.dumps(command, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        self.connection.begin()
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT version FROM finance_statement_archive_state WHERE id=1 FOR UPDATE")
                if cursor.fetchone() is None:
                    raise RuntimeError("archive_schema_not_initialized")
                cursor.execute("SELECT * FROM finance_statement_commands WHERE idempotency_key=%s", (key,))
                previous = cursor.fetchone()
                if previous:
                    if previous["command_digest"] != digest:
                        raise StatementCommandConflict("idempotency_conflict")
                    result = StatementCommandReceipt(previous["result_identity"], previous["saved_count"], previous["excluded_count"])
                else:
                    result = write(cursor)
                    cursor.execute(
                        "INSERT INTO finance_statement_commands(idempotency_key,command_digest,result_identity,saved_count,excluded_count,actor) VALUES (%s,%s,%s,%s,%s,%s)",
                        (key, digest, result.identity, result.saved_count, result.excluded_count, actor),
                    )
                    cursor.execute("UPDATE finance_statement_archive_state SET version=version+1 WHERE id=1")
            self.connection.commit()
            return result
        except Exception:
            self.connection.rollback()
            raise


def _object(value):
    result = json.loads(value) if isinstance(value, str) else value
    if not isinstance(result, dict):
        raise ValueError("statement_source_invalid")
    return result


_STAGE_PRIORITY = {"訂金": 1, "第一期": 2, "第二期": 3}


def format_export_purpose(bank: str, proofs: list[dict]) -> str:
    if not proofs:
        return "已核銷款項"
    has_over_refund_recovery = any(item.get("proof_source") == "client_over_refund_recovery" for item in proofs)
    labels: list[str] = []
    identities: set[str] = set()
    is_gov_only = True
    for index, item in enumerate(proofs):
        source = item.get("proof_source")
        entry_type = item.get("entry_type")
        obligation_type = item.get("obligation_type")
        item_identity = str(item.get("item_identity") or f"{source}:{index}")
        if source == "client_over_refund_recovery":
            is_gov_only = False
            label = "客戶退款超付追償"
        elif source == "client_ledger":
            if has_over_refund_recovery and obligation_type is None:
                continue
            is_gov_only = False
            if entry_type in ("reversal", "subsidy_return_reversal"):
                label = "客戶退匯"
            elif entry_type in ("subsidy_return", "subsidy_advance") or obligation_type == "subsidy_return":
                label = "退客戶先墊補助"
            elif entry_type == "refund" or obligation_type == "refund":
                label = "取消結算退款" if item_identity.startswith("client-cancellation:") else "客戶退款"
            elif obligation_type == "deposit":
                label = "訂金"
            elif obligation_type == "first":
                label = "第一期"
            elif obligation_type == "second":
                label = "第二期"
            elif obligation_type == "adjustment":
                label = "取消結算補收" if item_identity.startswith("client-cancellation:") else "帳務調整"
            else:
                label = "客戶入款"
        elif source == "staff_payout":
            is_gov_only = False
            if entry_type in ("return", "reversal"):
                label = "月嫂退匯"
            else:
                label = "補助轉交月嫂" if bank == "taishin" else "月嫂薪資"
        elif source == "government_subsidy":
            label = "政府補助差額退回" if entry_type == "outgoing" else "政府補助"
        elif source == "staff_overpayment_recovery":
            is_gov_only = False
            label = "月嫂超付追償"
        else:
            is_gov_only = False
            label = "已核銷款項"
        identities.add(f"{source}:{item_identity}")
        if label not in labels:
            labels.append(label)
    if not labels:
        return "已核銷款項"
    labels.sort(key=lambda text: _STAGE_PRIORITY.get(text, 99))
    combined = "+".join(labels)
    if not is_gov_only and (len(labels) > 1 or len(identities) > 1):
        return f"{combined}(組合銷帳)"
    return combined


def _load_row_purposes(cursor, row_ids: tuple[int, ...], by_id: dict[int, dict]) -> dict[int, str]:
    if not row_ids:
        return {}
    placeholders = ",".join(["%s"] * len(row_ids))
    cursor.execute(
        f"""
        SELECT l.finance_import_row_id AS row_id,
               'client_ledger' AS proof_source,
               l.entry_type AS entry_type,
               o.obligation_type AS obligation_type,
               o.obligation_identity AS item_identity,
               COALESCE(x.allocation_ordinal, 0) AS ordinal
        FROM client_ledger_entries l
        LEFT JOIN client_ledger_obligation_allocations x ON x.ledger_entry_id=l.id
        LEFT JOIN client_obligations o ON o.obligation_identity=x.obligation_identity
        WHERE l.finance_import_row_id IN ({placeholders})
        UNION ALL
        SELECT COALESCE(e.finance_import_row_id, l.finance_import_row_id) AS row_id,
               'client_over_refund_recovery' AS proof_source,
               e.event_type AS entry_type,
               NULL AS obligation_type,
               e.recovery_identity AS item_identity,
               0 AS ordinal
        FROM client_over_refund_recovery_events e
        LEFT JOIN client_ledger_entries l ON l.id=e.receipt_ledger_entry_id
        WHERE e.event_type='collected'
          AND COALESCE(e.finance_import_row_id, l.finance_import_row_id) IN ({placeholders})
        UNION ALL
        SELECT e.finance_import_row_id AS row_id,
               'staff_payout' AS proof_source,
               e.event_type AS entry_type,
               NULL AS obligation_type,
               l.obligation_identity AS item_identity,
               0 AS ordinal
        FROM staff_payout_events e
        LEFT JOIN staff_payout_obligation_links l ON l.payout_event_id=e.id
        WHERE e.finance_import_row_id IN ({placeholders})
        UNION ALL
        SELECT t.finance_import_row_id AS row_id,
               'government_subsidy' AS proof_source,
               b.direction AS entry_type,
               NULL AS obligation_type,
               CAST(t.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci AS item_identity,
               0 AS ordinal
        FROM government_subsidy_transactions t
        JOIN finance_import_rows b ON b.id=t.finance_import_row_id
        WHERE t.finance_import_row_id IN ({placeholders}) AND t.transaction_status='succeeded'
        UNION ALL
        SELECT entry.finance_import_row_id AS row_id,
               'government_subsidy' AS proof_source,
               b.direction AS entry_type,
               NULL AS obligation_type,
               CAST(entry.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci AS item_identity,
               0 AS ordinal
        FROM government_subsidy_period_entries entry
        JOIN finance_import_rows b ON b.id=entry.finance_import_row_id
        WHERE entry.finance_import_row_id IN ({placeholders})
        UNION ALL
        SELECT event.finance_import_row_id AS row_id,
               'staff_overpayment_recovery' AS proof_source,
               event.event_type AS entry_type,
               NULL AS obligation_type,
               event.recovery_identity AS item_identity,
               0 AS ordinal
        FROM staff_overpayment_recovery_events event
        WHERE event.event_type='cash_recovered' AND event.finance_import_row_id IN ({placeholders})
        ORDER BY row_id, ordinal
        """,
        row_ids * 6,
    )
    grouped: dict[int, list[dict]] = {}
    for row in cursor.fetchall():
        grouped.setdefault(int(row["row_id"]), []).append(row)
    return {
        row_id: format_export_purpose(by_id[row_id]["bank"], grouped.get(row_id, []))
        for row_id in row_ids
    }
