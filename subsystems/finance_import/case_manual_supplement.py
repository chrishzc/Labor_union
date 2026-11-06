"""
File: case_manual_supplement.py
Description: 案件抽屜手動補登並自動銷帳應用服務，自動將選定操作銀行、方向、期款轉化為標準規格對帳單明細並完成領域銷帳。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from domains.client_finance.reconciliation import PaymentStage
from infrastructure.mysql.client_receipt_reconciliation_repository import (
    MySqlClientReceiptReconciliationRepository,
)
from infrastructure.mysql.client_refund_reversal_repository import MySqlClientRefundReversalRepository
from domains.client_finance.client_refund_reversal import ClientFinanceCorrectionType, ClientRefundPurpose
from infrastructure.mysql.finance_import_owning_domain_composite import BorrowedTransactionUnitOfWork
from infrastructure.mysql.staff_payable_correction_sql import selectable_staff_obligation
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.client_finance.reconciliation_workflow import (
    ClientReconciliationApplyRequest,
    ClientReconciliationWorkflow, ReconciliationSelection,
)
from subsystems.client_finance.virtual_account_resolution import resolve_case_virtual_account
from subsystems.client_finance.client_refund_reversal_workflow import (
    ClientRefundReversalApplyRequest, ClientRefundReversalSelection,
    ClientRefundReversalWorkflow, ManualClientRefundSource,
)
from subsystems.finance_import.accounting_workspace import AccountingConflict
from subsystems.finance_import.statement_archive import StatementCommandConflict


def _bank_references(bank, reason, cancellation_code, memo, *, allow_overage_disposition=False,
                     manual_command=None):
    # Sinopac's canonical parser reads the original reference column; storing
    # only the row-level cancellation_code would make the owner reject it.
    references = {"source": "manual_supplement", "bank": bank, "reason": reason,
                  "銷帳編號": cancellation_code, "備註": memo}
    if allow_overage_disposition:
        references["allow_overage_disposition"] = True
    if manual_command is not None:
        references["manual_command"] = dict(manual_command)
        references["manual_command_digest"] = fingerprint_payload(manual_command).value
    return references


def _supplement_command(case_no, bank, direction, target_item, amount_ntd,
                        transaction_date, reason, actor, *, allow_overage_disposition=False):
    command = {
        "case_no": case_no, "bank": bank, "direction": direction,
        "target_item": target_item, "amount_ntd": amount_ntd,
        "transaction_date": transaction_date, "reason": reason, "actor": actor,
    }
    # Omission means false, preserving receipts saved before this option existed.
    if allow_overage_disposition:
        command["allow_overage_disposition"] = True
    return command


def _replay_reason(command, stored_digest):
    if stored_digest == fingerprint_payload(command).value:
        return None
    # A former no-intent command can never authorize a new overage disposition.
    if command.get("allow_overage_disposition", False):
        raise StatementCommandConflict("idempotency_conflict")
    legacy_note = command["reason"] or "人工補登"
    legacy_digest = hashlib.sha256(
        (f"{command['case_no']}:{command['bank']}:{command['direction']}:"
         f"{command['target_item']}:{command['amount_ntd']}:{command['transaction_date']}:"
         f"{legacy_note}:{command['actor']}").encode()
    ).hexdigest()
    if stored_digest == legacy_digest:
        return legacy_note
    raise StatementCommandConflict("idempotency_conflict")


class ManualSupplementBlocked(ValueError):
    """A known owner blocker; the caller must roll back the whole command."""

    def __init__(self, code: str):
        self.error = TypedError(
            ErrorCategory.DOMAIN_BLOCKED, code,
            "Manual supplement requires review before posting.",
            CorrelationId("finance-manual-supplement"), domain_blockers=(code,),
        )
        super().__init__(code)


@dataclass(frozen=True)
class ManualSupplementResult:
    case_no: str
    row_id: int
    entry_id: int
    direction: str
    target_item: str
    amount_ntd: int
    reconciled: bool


class CaseManualSupplementService:
    """案件手動補登核心服務。在單一事務內建立標準對帳單明細並調用各領域核銷。"""

    def __init__(self, connection):
        self.connection = connection

    def execute(
        self,
        case_no: str,
        bank: str,
        direction: str,
        target_item: str,
        amount_ntd: int,
        transaction_date: str,
        reason: str | None,
        idempotency_key: str,
        actor: str,
        allow_overage_disposition: bool = False,
    ) -> ManualSupplementResult:
        if bank not in {"sinopac", "taishin"}:
            raise ValueError(f"不支援的操作銀行: {bank}")
        if direction not in {"client_receipt", "staff_salary", "client_refund", "government_subsidy"}:
            raise ValueError(f"不支援的交易方向: {direction}")
        if not isinstance(allow_overage_disposition, bool) or (allow_overage_disposition and direction not in {"client_receipt", "client_refund"}):
            raise ValueError("invalid_client_receipt_intent")
        if amount_ntd <= 0:
            raise ValueError("補登金額必須大於 0")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", transaction_date):
            raise ValueError("交易日期格式必須為 YYYY-MM-DD")
        if not idempotency_key.strip():
            raise ValueError("缺少冪等鍵 (Idempotency-Key)")
        if not target_item.strip():
            raise ValueError("缺少沖銷對象／期款代碼")

        note_text = (reason or "").strip()
        command = _supplement_command(
            case_no, bank, direction, target_item, amount_ntd, transaction_date, note_text, actor,
            allow_overage_disposition=allow_overage_disposition,
        )

        with self.connection.cursor() as cursor:
            # 1. 驗證訂單存在
            cursor.execute("SELECT case_no FROM orders WHERE case_no=%s FOR UPDATE", (case_no,))
            if not cursor.fetchone():
                raise LookupError(f"查無案件: {case_no}")

            # 2. 冪等檢查
            cmd_digest = fingerprint_payload(command).value
            cursor.execute(
                "SELECT command_digest,result_identity FROM finance_statement_commands WHERE idempotency_key=%s FOR UPDATE",
                (idempotency_key,),
            )
            existing = cursor.fetchone()
            if existing:
                # Old receipts used a delimiter-based digest and a generated
                # default reason. Accept them only after checking original facts.
                return self._replay(
                    cursor, existing["result_identity"], command,
                    legacy_reason=_replay_reason(command, existing["command_digest"]),
                )

            # Replay precedes mutable balance/status checks: a settled target can replay.
            target = self._lock_target(cursor, case_no, direction, target_item)
            resolution = resolve_case_virtual_account(cursor, case_no)
            if resolution["result"] != "resolved":
                raise ManualSupplementBlocked(str(resolution["reason"]))
            virtual_account = str(resolution["virtual_account"])
            case_suffix = virtual_account[-6:]
            if (direction in {"staff_salary", "client_refund"} and amount_ntd > int(target["remaining_ntd"])
                and not (direction == "client_refund" and allow_overage_disposition)):
                code = "staff_payout_difference_mode_invalid" if direction == "staff_salary" else "allocation_exceeds_obligation"
                raise ManualSupplementBlocked(code)

            # 3. 建立標準對帳單明細 (finance_import_rows)
            row_fp = hashlib.sha256(
                f"manual-supplement:{case_no}:{bank}:{direction}:{amount_ntd}:{transaction_date}:{idempotency_key}".encode()
            ).hexdigest()

            is_incoming = direction in {"client_receipt", "government_subsidy"}
            cancellation_code = virtual_account if direction == "client_receipt" else ""
            memo = (
                f"HC{case_suffix}服務人員"
                if direction == "staff_salary"
                else f"HC{case_suffix}退款"
                if direction == "client_refund"
                else f"新竹市政府補助款 {case_suffix}"
                if direction == "government_subsidy"
                else note_text
            )
            classification = (
                "government_subsidy"
                if direction == "government_subsidy"
                else "client_receipt"
                if direction == "client_receipt"
                else "staff_payout"
                if direction == "staff_salary"
                else "client_refund"
            )
            date_slash = transaction_date.replace("-", "/")
            raw_payload = {
                "帳號": None,
                "交易日": date_slash,
                "計息日": date_slash,
                "入帳日": date_slash,
                "摘要": "人工補登",
                "幣別": "TWD",
                "支出": "" if is_incoming else amount_ntd,
                "存入": amount_ntd if is_incoming else "",
                "餘額": "",
                "票據號碼": "",
                "銷帳編號": cancellation_code,
                "交易參考編號": f"MANUAL-{idempotency_key[:16]}",
                "備註": memo,
                "更正註記": "",
                "存摺備註": "",
            }

            cursor.execute(
                """
                INSERT INTO finance_import_rows (
                    dedup_fingerprint, format_id, transaction_date, direction,
                    credit, debit, summary, memo, cancellation_code, bank_references,
                    warnings, classification_type, reconciliation_status, raw_payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row_fp,
                    bank,
                    transaction_date,
                    "incoming" if is_incoming else "outgoing",
                    amount_ntd if is_incoming else None,
                    None if is_incoming else amount_ntd,
                    "人工補登",
                    memo,
                    cancellation_code,
                    json.dumps(
                        _bank_references(bank, note_text, cancellation_code, memo,
                                         allow_overage_disposition=allow_overage_disposition,
                                         manual_command=command if direction == "client_refund" else None),
                        ensure_ascii=False,
                    ),
                    "[]",
                    classification,
                    "pending" if direction in {"client_receipt", "client_refund"} else "reconciled",
                    json.dumps(raw_payload, ensure_ascii=False),
                ),
            )
            row_id = cursor.lastrowid

            # 4. 領域核銷連動
            entry_id = 0
            if direction == "client_receipt":
                self._post_client_receipt(
                    case_no, row_id, target_item, target["obligation_type"],
                    idempotency_key, actor, note_text,
                    allow_overage_disposition=allow_overage_disposition,
                )
                cursor.execute(
                    "SELECT id FROM client_ledger_entries WHERE finance_import_row_id=%s AND case_no=%s AND entry_type='receipt'",
                    (row_id, case_no),
                )
                entry = cursor.fetchone()
                if entry is None:
                    raise AccountingConflict("manual_supplement_receipt_missing")
                entry_id = int(entry["id"])

            elif direction == "staff_salary":
                # 月嫂薪資核銷
                staff_id = int(target["staff_id"])

                bank_hash = hashlib.sha256(f"manual:{staff_id}:{bank}".encode()).hexdigest()
                cursor.execute(
                    """
                    INSERT INTO staff_payout_events (
                        staff_id, finance_import_row_id, event_type, amount_ntd,
                        occurred_on, bank_account_identity_hash, reconciliation_reference,
                        idempotency_key, actor, reason
                    ) VALUES (%s, %s, 'payout', %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        staff_id,
                        row_id,
                        amount_ntd,
                        transaction_date,
                        bank_hash,
                        f"manual-payout:{row_id}",
                        idempotency_key,
                        actor,
                        note_text,
                    ),
                )
                entry_id = cursor.lastrowid
                cursor.execute(
                    """
                    INSERT INTO staff_payout_obligation_links (
                        payout_event_id, obligation_identity, allocated_amount_ntd, allocation_ordinal
                    ) VALUES (%s, %s, %s, 1)
                    """,
                    (entry_id, target_item, amount_ntd),
                )
                # All assignments use the same locked pre-payment values. MySQL
                # single-table UPDATE otherwise reuses already-updated net_paid.
                net_paid = int(target["net_paid_ntd"]) + amount_ntd
                remaining = int(target["remaining_ntd"]) - amount_ntd
                cursor.execute(
                    """
                    UPDATE staff_payable_projections
                    SET net_paid_ntd=%s, balance_ntd=%s, status=%s,
                        aggregate_version=aggregate_version+1, current_event_id=%s
                    WHERE obligation_identity=%s AND aggregate_version=%s
                    """,
                    (net_paid, remaining, "completed" if remaining == 0 else "partially_paid",
                     entry_id, target_item, target["aggregate_version"]),
                )
                if cursor.rowcount != 1:
                    raise AccountingConflict("staff_payables_candidate_stale")

            elif direction == "client_refund":
                self._post_client_refund(
                    case_no, row_id, target_item, amount_ntd, transaction_date,
                    idempotency_key, actor, note_text, cmd_digest,
                    allow_overage_disposition=allow_overage_disposition,
                )
                cursor.execute(
                    "SELECT id FROM client_ledger_entries WHERE finance_import_row_id=%s AND case_no=%s AND entry_type='refund'",
                    (row_id, case_no),
                )
                entry = cursor.fetchone()
                if entry is None:
                    raise AccountingConflict("manual_supplement_receipt_missing")
                entry_id = int(entry["id"])

            elif direction == "government_subsidy":
                # 政府入款核銷（台新入款 G）
                cursor.execute(
                    "SELECT COALESCE(actual_end_date, end_date) as service_end FROM orders WHERE case_no=%s",
                    (case_no,),
                )
                ord_row = cursor.fetchone()
                svc_date = ord_row["service_end"] if ord_row and ord_row["service_end"] else transaction_date
                year_val = int(str(svc_date)[:4])
                month_val = int(str(svc_date)[5:7]) if len(str(svc_date)) >= 7 else 1
                quarter_val = (month_val - 1) // 3 + 1
                cursor.execute(
                    """
                    INSERT INTO government_subsidy_period_entries (
                        period_unit, period_year, period_index, period_start, period_end,
                        finance_import_row_id, amount_ntd, paid_on, idempotency_key, actor
                    ) VALUES (
                        'quarter', %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        year_val,
                        quarter_val,
                        f"{year_val}-{(quarter_val-1)*3+1:02d}-01",
                        f"{year_val}-{quarter_val*3:02d}-28",
                        row_id,
                        amount_ntd,
                        transaction_date,
                        idempotency_key,
                        actor,
                    ),
                )
                entry_id = cursor.lastrowid
                cursor.execute(
                    """
                    INSERT INTO government_subsidy_period_members (
                        receipt_id, case_no, service_end_date, amount_ntd
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (entry_id, case_no, svc_date, amount_ntd),
                )

            # 5. 寫入 command 收據防重
            cursor.execute(
                """
                INSERT INTO finance_statement_commands (
                    idempotency_key, command_digest, result_identity, saved_count, excluded_count, actor
                ) VALUES (%s, %s, %s, 1, 0, %s)
                """,
                (idempotency_key, cmd_digest, f"manual:{row_id}", actor),
            )

        return ManualSupplementResult(
            case_no=case_no,
            row_id=row_id,
            entry_id=entry_id,
            direction=direction,
            target_item=target_item,
            amount_ntd=amount_ntd,
            reconciled=True,
        )


    def _lock_target(self, cursor, case_no, direction, target_item):
        if direction == "government_subsidy":
            return {}
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
            allowed_types = ("deposit", "first", "second", "adjustment") if direction == "client_receipt" else ("refund", "adjustment")
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

    def _post_client_receipt(self, case_no, row_id, target_item, obligation_type, key, actor, reason,
                             *, allow_overage_disposition=False):
        repository = MySqlClientReceiptReconciliationRepository(self.connection)
        workflow = ClientReconciliationWorkflow(repository, BorrowedTransactionUnitOfWork)
        selection = ReconciliationSelection(
            case_no, PaymentStage(obligation_type), (str(row_id),), (target_item,),
            allow_overage_disposition=allow_overage_disposition,
            allow_partial_receipt=not allow_overage_disposition,
        )
        preview = workflow.preview(selection)
        request = ClientReconciliationApplyRequest(
            selection, ExpectedVersion(preview.account_version), preview.fingerprint,
            IdempotencyKey("manual-client-receipt:" + hashlib.sha256(key.encode()).hexdigest()),
            ActorContext(actor), reason, CorrelationId("finance-manual-supplement"),
        )
        repository.bind_apply_request(request)
        try:
            return workflow.apply(request)
        except ValueError as error:
            if str(error) == "client_refund_recipient_snapshot_missing":
                raise ManualSupplementBlocked(str(error)) from error
            raise
        finally:
            repository.clear_apply_request()

    def _post_client_refund(self, case_no, row_id, target_item, amount_ntd, transaction_date,
                            key, actor, reason, command_digest, *, allow_overage_disposition=False):
        context = ManualClientRefundSource(
            int(row_id), case_no, target_item, amount_ntd, transaction_date,
            ActorContext(actor), command_digest, allow_overage_disposition, reason=reason,
        )
        repository = MySqlClientRefundReversalRepository(self.connection, manual_source=context)
        workflow = ClientRefundReversalWorkflow(repository, BorrowedTransactionUnitOfWork)
        selection = ClientRefundReversalSelection(
            case_no,
            ClientFinanceCorrectionType.REFUND_OVERAGE if allow_overage_disposition else ClientFinanceCorrectionType.REFUND,
            ClientRefundPurpose.CUSTOMER_REFUND,
            bank_fact_identities=(str(row_id),), obligation_identities=(target_item,),
            allow_partial_refund_recovery=not allow_overage_disposition,
        )
        preview = workflow.preview(selection, CorrelationId("finance-manual-supplement"))
        request = ClientRefundReversalApplyRequest(
            selection, ExpectedVersion(preview.account_version), preview.fingerprint,
            IdempotencyKey("manual-client-refund:" + hashlib.sha256(key.encode()).hexdigest()),
            ActorContext(actor), reason, CorrelationId("finance-manual-supplement"),
        )
        repository.bind_apply_request(request)
        try:
            return workflow.apply(request)
        finally:
            repository.clear_apply_request()

    def _replay(self, cursor, result_identity, command, *, legacy_reason=None):
        if not isinstance(result_identity, str) or re.fullmatch(r"manual:[1-9][0-9]*", result_identity) is None:
            raise StatementCommandConflict("manual_supplement_receipt_invalid")
        row_id = int(result_identity.split(":", 1)[1])
        case_no, direction = command["case_no"], command["direction"]
        cursor.execute(
            "SELECT format_id,transaction_date,credit,debit,bank_references FROM finance_import_rows WHERE id=%s",
            (row_id,),
        )
        source = cursor.fetchone()
        if source is None:
            raise StatementCommandConflict("manual_supplement_receipt_invalid")
        references = source["bank_references"]
        if isinstance(references, str):
            references = json.loads(references)
        expected_reason = command["reason"] if legacy_reason is None else legacy_reason
        source_amount = source["credit"] if direction in {"client_receipt", "government_subsidy"} else source["debit"]
        if (
            source["format_id"] != command["bank"]
            or str(source["transaction_date"]) != command["transaction_date"]
            or not isinstance(references, dict)
            or references.get("source") != "manual_supplement"
            or references.get("reason") != expected_reason
            or references.get("allow_overage_disposition", False) is not command.get("allow_overage_disposition", False)
            or source_amount is None
            or int(source_amount) != command["amount_ntd"]
        ):
            raise StatementCommandConflict("idempotency_conflict")
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
            entry_type = "receipt" if direction == "client_receipt" else "refund"
            query = (
                "SELECT entry.id AS entry_id,allocation.obligation_identity AS target_item,entry.amount_ntd,entry.actor "
                "FROM client_ledger_entries entry JOIN client_ledger_obligation_allocations allocation ON allocation.ledger_entry_id=entry.id "
                "WHERE entry.finance_import_row_id=%s AND entry.case_no=%s AND entry.entry_type='" + entry_type + "'"
            )
        cursor.execute(query, (row_id, case_no))
        rows = tuple(cursor.fetchall())
        if len(rows) != 1:
            raise StatementCommandConflict("manual_supplement_receipt_invalid")
        original = rows[0]
        if (
            int(original["amount_ntd"]) != command["amount_ntd"]
            or original["actor"] != command["actor"]
            or (direction != "government_subsidy" and original["target_item"] != command["target_item"])
        ):
            raise StatementCommandConflict("idempotency_conflict")
        return ManualSupplementResult(
            case_no, row_id, int(original["entry_id"]), direction,
            command["target_item"] if direction == "government_subsidy" else str(original["target_item"]),
            int(original["amount_ntd"]), True,
        )
