"""MySQL source store for the existing case-scoped manual supplement command."""
from __future__ import annotations

from contextlib import contextmanager
import re

from infrastructure.mysql.staff_payable_correction_sql import selectable_staff_obligation
from subsystems.client_finance.virtual_account_resolution import resolve_case_virtual_account
from subsystems.finance_import.accounting_workspace import AccountingConflict
from subsystems.finance_import.case_manual_supplement import ManualSupplementReplayFacts, ManualSupplementSourceRow
from subsystems.finance_import.statement_archive import StatementCommandConflict


class MySqlManualSupplementSourceStore:
    """Borrows the same connection/cursor; the existing API owns the transaction."""
    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def session(self):
        with self.connection.cursor() as cursor:
            yield _MySqlManualSupplementSourceSession(cursor)


class _MySqlManualSupplementSourceSession:
    def __init__(self, cursor):
        self.cursor = cursor

    def require_case(self, case_no):
        cursor = self.cursor
        cursor.execute("SELECT case_no FROM orders WHERE case_no=%s FOR UPDATE", (case_no,))
        if not cursor.fetchone():
            raise LookupError(f"查無案件: {case_no}")

    def find_command(self, idempotency_key):
        cursor = self.cursor
        cursor.execute(
            "SELECT command_digest,result_identity FROM finance_statement_commands WHERE idempotency_key=%s FOR UPDATE",
            (idempotency_key,),
        )
        return cursor.fetchone()

    def resolve_virtual_account(self, case_no):
        return resolve_case_virtual_account(self.cursor, case_no)

    def lock_target(self, case_no, direction, target_item):
        cursor = self.cursor
        if direction == "staff_salary":
            cursor.execute(
                "SELECT obligations.staff_id FROM staff_obligations obligations "
                "WHERE obligations.obligation_identity=%s AND obligations.case_no=%s",
                (target_item, case_no),
            )
            scope = cursor.fetchone()
            if scope is None:
                raise AccountingConflict("manual_supplement_target_not_current")
            cursor.execute(
                "SELECT aggregate_version FROM staff_payable_accounts WHERE staff_id=%s FOR UPDATE",
                (scope["staff_id"],),
            )
            cursor.fetchone()
            cursor.execute(
                "SELECT obligations.staff_id,projection.net_paid_ntd,projection.balance_ntd AS remaining_ntd,"
                "projection.aggregate_version FROM staff_obligations obligations "
                "JOIN staff_payable_projections projection ON projection.obligation_identity=obligations.obligation_identity "
                "WHERE obligations.obligation_identity=%s AND obligations.case_no=%s "
                "AND obligations.direction='payable_to_staff' AND obligations.status='open' "
                "AND projection.status IN ('payable','partially_paid') AND projection.balance_ntd>0 "
                "AND " + selectable_staff_obligation() + " FOR UPDATE",
                (target_item, case_no),
            )
        else:
            cursor.execute(
                "SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s FOR UPDATE",
                (case_no,),
            )
            cursor.fetchone()
            expected_direction = "receivable_from_client" if direction == "client_receipt" else "payable_to_client"
            allowed_types = ("deposit", "first", "second", "adjustment") if direction == "client_receipt" else ("refund", "adjustment", "subsidy_return")
            placeholders = ",".join("%s" for _ in allowed_types)
            cursor.execute(
                "SELECT obligation_type,amount_due_ntd AS remaining_ntd FROM client_obligations "
                "WHERE obligation_identity=%s AND case_no=%s AND direction=%s "
                "AND status='open' AND amount_due_ntd>0 "
                f"AND obligation_type IN ({placeholders}) FOR UPDATE",
                (target_item, case_no, expected_direction, *allowed_types),
            )
        target = cursor.fetchone()
        if target is None:
            raise AccountingConflict("manual_supplement_target_not_current")
        return target

    def append_source(self, row: ManualSupplementSourceRow) -> int:
        cursor = self.cursor
        cursor.execute(
            """
                INSERT INTO finance_import_rows (
                    dedup_fingerprint, format_id, transaction_date, direction,
                    credit, debit, summary, memo, cancellation_code, bank_references,
                    warnings, classification_type, reconciliation_status, raw_payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
            row.values,
        )
        return int(cursor.lastrowid)

    def posted_entry_id(self, direction, case_no, row_id, target_item, obligation_type):
        cursor = self.cursor
        if direction == "client_receipt":
            cursor.execute(
                "SELECT id FROM client_ledger_entries WHERE finance_import_row_id=%s AND case_no=%s AND entry_type='receipt'",
                (row_id, case_no),
            )
            entry = cursor.fetchone()
            if entry is None:
                raise AccountingConflict("manual_supplement_receipt_missing")
            entry_id = int(entry["id"])
        elif direction == "staff_salary":
            cursor.execute(
                "SELECT payout.id FROM staff_payout_events payout "
                "JOIN staff_payout_obligation_links link ON link.payout_event_id=payout.id "
                "WHERE payout.finance_import_row_id=%s AND payout.event_type='payout' AND link.obligation_identity=%s",
                (row_id, target_item),
            )
            entry = cursor.fetchone()
            if entry is None:
                raise AccountingConflict("manual_supplement_receipt_missing")
            entry_id = int(entry["id"])
        elif direction == "client_refund":
            cursor.execute(
                "SELECT id FROM client_ledger_entries WHERE finance_import_row_id=%s AND case_no=%s AND entry_type=%s",
                (row_id, case_no, "subsidy_return" if obligation_type == "subsidy_return" else "refund"),
            )
            entry = cursor.fetchone()
            if entry is None:
                raise AccountingConflict("manual_supplement_receipt_missing")
            entry_id = int(entry["id"])
        return entry_id

    def save_command(self, idempotency_key, cmd_digest, row_id, actor):
        cursor = self.cursor
        # 5. 寫入 command 收據防重
        cursor.execute(
            """
                INSERT INTO finance_statement_commands (
                    idempotency_key, command_digest, result_identity, saved_count, excluded_count, actor
                ) VALUES (%s, %s, %s, 1, 0, %s)
                """,
            (idempotency_key, cmd_digest, f"manual:{row_id}", actor),
        )

    def load_replay_source(self, result_identity):
        cursor = self.cursor
        if not isinstance(result_identity, str) or re.fullmatch(r"manual:[1-9][0-9]*", result_identity) is None:
            raise StatementCommandConflict("manual_supplement_receipt_invalid")
        row_id = int(result_identity.split(":", 1)[1])
        cursor.execute(
            "SELECT format_id,transaction_date,credit,debit,bank_references FROM finance_import_rows WHERE id=%s",
            (row_id,),
        )
        source = cursor.fetchone()
        if source is None:
            raise StatementCommandConflict("manual_supplement_receipt_invalid")
        return ManualSupplementReplayFacts(row_id, source)

    def load_replay_entries(self, row_id, command):
        cursor = self.cursor
        case_no, direction = command["case_no"], command["direction"]
        if direction == "staff_salary":
            query = (
                "SELECT payout.id AS entry_id,link.obligation_identity AS target_item,payout.amount_ntd,payout.actor "
                "FROM staff_payout_events payout JOIN staff_payout_obligation_links link ON link.payout_event_id=payout.id "
                "JOIN staff_obligations obligation ON obligation.obligation_identity=link.obligation_identity "
                "WHERE payout.finance_import_row_id=%s AND obligation.case_no=%s AND payout.event_type='payout'"
            )
        elif direction == "government_subsidy":
            query = (
                "SELECT entry.id AS entry_id,member.case_no AS target_item,entry.amount_ntd,entry.actor "
                "FROM government_subsidy_period_entries entry JOIN government_subsidy_period_members member ON member.receipt_id=entry.id "
                "WHERE entry.finance_import_row_id=%s AND member.case_no=%s"
            )
        else:
            query = (
                "SELECT entry.id AS entry_id,allocation.obligation_identity AS target_item,entry.amount_ntd,entry.actor,entry.entry_type,obligation.obligation_type "
                "FROM client_ledger_entries entry JOIN client_ledger_obligation_allocations allocation ON allocation.ledger_entry_id=entry.id "
                "JOIN client_obligations obligation ON obligation.obligation_identity=allocation.obligation_identity "
                "WHERE entry.finance_import_row_id=%s AND entry.case_no=%s AND entry.entry_type "
                + ("='receipt'" if direction == "client_receipt" else "IN ('refund','subsidy_return')")
            )
        cursor.execute(query, (row_id, case_no))
        rows = tuple(cursor.fetchall())
        return rows
