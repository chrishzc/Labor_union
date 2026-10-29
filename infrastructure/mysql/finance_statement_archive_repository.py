"""Finance Import archive adapter: no second copy of canonical bank facts."""
import hashlib
import json

from subsystems.finance_import.statement_archive import (
    StatementCommandConflict, StatementCommandReceipt, StatementExportRow,
)

_PROOFS = """
SELECT finance_import_row_id AS row_id,case_no FROM client_ledger_entries WHERE finance_import_row_id IS NOT NULL
UNION
SELECT e.finance_import_row_id,o.case_no FROM staff_payout_events e
JOIN staff_payout_obligation_links l ON l.payout_event_id=e.id
JOIN staff_obligations o ON o.obligation_identity=l.obligation_identity WHERE e.finance_import_row_id IS NOT NULL
UNION
SELECT t.finance_import_row_id,i.case_no FROM government_subsidy_transactions t
JOIN government_subsidy_allocations a ON a.transaction_id=t.id
JOIN subsidy_claim_batch_items i ON i.id=a.claim_item_id
WHERE t.finance_import_row_id IS NOT NULL AND t.transaction_status='succeeded'
UNION
SELECT entry.finance_import_row_id,member.case_no FROM government_subsidy_period_entries entry
JOIN government_subsidy_period_members member ON member.receipt_id=COALESCE(entry.reversal_of_id,entry.id)
"""


class MySqlStatementArchiveRepository:
    def __init__(self, connection):
        self.connection = connection

    def export_rows(self):
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT b.id,b.format_id,b.raw_payload,p.case_no FROM finance_import_rows b JOIN ("
                + _PROOFS + ") p ON p.row_id=b.id JOIN orders r ON r.case_no=p.case_no "
                "LEFT JOIN finance_statement_exclusions x ON x.finance_import_row_id=b.id "
                "WHERE x.finance_import_row_id IS NULL ORDER BY b.id,p.case_no"
            )
            canonical = cursor.fetchall()
            cursor.execute("SELECT id,fields FROM finance_manual_statements ORDER BY id")
            manual = cursor.fetchall()
        by_id = {}
        for row in canonical:
            entry = by_id.setdefault(int(row["id"]), {"bank": row["format_id"], "fields": _object(row["raw_payload"]), "cases": []})
            if row["case_no"] not in entry["cases"]:
                entry["cases"].append(row["case_no"])
        result = [StatementExportRow(f"bank:{identity}", row["bank"], "reconciled", tuple(row["cases"]), tuple(row["fields"].items())) for identity, row in by_id.items()]
        result.extend(StatementExportRow(f"manual:{row['id']}", "manual", "manual", (), tuple(_object(row["fields"]).items())) for row in manual)
        return tuple(result)

    def create_manual(self, fields, key, actor, duplicate_of=None):
        command = {"operation": "manual", "fields": fields, "duplicate_of": duplicate_of, "actor": actor}

        def write(cursor):
            if duplicate_of:
                self._require_existing(duplicate_of)
                return StatementCommandReceipt(duplicate_of, 0, 1)
            cursor.execute("INSERT INTO finance_manual_statements(fields,actor) VALUES (%s,%s)", (json.dumps(fields, ensure_ascii=False), actor))
            return StatementCommandReceipt(f"manual:{cursor.lastrowid}", 1, 0)

        return self._command(command, key, actor, write)

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
