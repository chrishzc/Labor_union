"""
File: case_manual_supplement.py
Description: 案件抽屜手動補登並自動銷帳應用服務，自動將選定操作銀行、方向、期款轉化為標準規格對帳單明細並完成領域銷帳。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any


def _case_suffix_six(case_no: str) -> str:
    """提取案件後六碼，用於對帳單備註比對。"""
    digits = re.findall(r"\d+", case_no)
    if not digits:
        return case_no[-6:].zfill(6)
    num_str = "".join(digits)
    return num_str[-6:].zfill(6)


def _build_virtual_account(case_no: str) -> str:
    """計算案件 14 碼標準虛擬帳號（99781699 + 3 碼年度 + 3 碼流水）。"""
    match = re.match(r"^A?(\d{3})(\d{3,6})$", case_no)
    if not match:
        suffix = _case_suffix_six(case_no)
        return f"99781699{suffix}"
    year = match.group(1)
    raw_seq = int(match.group(2))
    account_seq = raw_seq + 500 if case_no.startswith("A") else raw_seq
    return f"99781699{year}{account_seq:03d}"


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
    ) -> ManualSupplementResult:
        if bank not in {"sinopac", "taishin"}:
            raise ValueError(f"不支援的操作銀行: {bank}")
        if direction not in {"client_receipt", "staff_salary", "client_refund", "government_subsidy"}:
            raise ValueError(f"不支援的交易方向: {direction}")
        if amount_ntd <= 0:
            raise ValueError("補登金額必須大於 0")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", transaction_date):
            raise ValueError("交易日期格式必須為 YYYY-MM-DD")
        if not idempotency_key.strip():
            raise ValueError("缺少冪等鍵 (Idempotency-Key)")
        if not target_item.strip():
            raise ValueError("缺少沖銷對象／期款代碼")

        case_suffix = _case_suffix_six(case_no)
        virtual_account = _build_virtual_account(case_no)
        note_text = (reason or "").strip() or "人工補登"

        with self.connection.cursor() as cursor:
            # 1. 驗證訂單存在
            cursor.execute("SELECT case_no FROM orders WHERE case_no=%s", (case_no,))
            if not cursor.fetchone():
                raise LookupError(f"查無案件: {case_no}")

            # 2. 冪等檢查
            cmd_digest = hashlib.sha256(
                f"{case_no}:{bank}:{direction}:{target_item}:{amount_ntd}:{transaction_date}:{note_text}:{actor}".encode()
            ).hexdigest()
            cursor.execute(
                "SELECT result_identity FROM finance_statement_commands WHERE idempotency_key=%s",
                (idempotency_key,),
            )
            existing = cursor.fetchone()
            if existing:
                res_id = existing["result_identity"] or f"case:{case_no}"
                return ManualSupplementResult(
                    case_no=case_no,
                    row_id=0,
                    entry_id=0,
                    direction=direction,
                    target_item=target_item,
                    amount_ntd=amount_ntd,
                    reconciled=True,
                )

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
                "帳號": "80700000000000" if bank == "sinopac" else "81200000000000",
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
                        {"source": "manual_supplement", "bank": bank, "reason": note_text},
                        ensure_ascii=False,
                    ),
                    "[]",
                    classification,
                    "reconciled",
                    json.dumps(raw_payload, ensure_ascii=False),
                ),
            )
            row_id = cursor.lastrowid

            # 4. 領域核銷連動
            entry_id = 0
            if direction == "client_receipt":
                # 客戶繳款核銷
                cursor.execute(
                    """
                    INSERT INTO client_ledger_entries (
                        case_no, finance_import_row_id, entry_type, amount_ntd,
                        occurred_on, reconciliation_reference, idempotency_key, actor, reason
                    ) VALUES (%s, %s, 'receipt', %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        case_no,
                        row_id,
                        amount_ntd,
                        transaction_date,
                        f"manual-supplement:{row_id}",
                        idempotency_key,
                        actor,
                        note_text,
                    ),
                )
                entry_id = cursor.lastrowid
                cursor.execute(
                    """
                    INSERT INTO client_ledger_obligation_allocations (
                        ledger_entry_id, obligation_identity, amount_ntd, allocation_ordinal
                    ) VALUES (%s, %s, %s, 1)
                    """,
                    (entry_id, target_item, amount_ntd),
                )
                # 更新期款餘額與狀態（嚴格遵循 chk_client_obligation_state 約束）
                cursor.execute(
                    "SELECT amount_due_ntd FROM client_obligations WHERE obligation_identity=%s FOR UPDATE",
                    (target_item,),
                )
                ob_row = cursor.fetchone()
                if ob_row:
                    before_due = int(ob_row["amount_due_ntd"])
                    remaining = max(0, before_due - amount_ntd)
                    new_status = "settled" if remaining == 0 else "open"
                    cursor.execute(
                        """
                        UPDATE client_obligations
                        SET amount_due_ntd=%s, status=%s, projection_version=projection_version+1
                        WHERE obligation_identity=%s
                        """,
                        (remaining, new_status, target_item),
                    )
                # 累加帳戶版本
                cursor.execute(
                    "UPDATE client_finance_accounts SET aggregate_version=aggregate_version+1 WHERE case_no=%s",
                    (case_no,),
                )

            elif direction == "staff_salary":
                # 月嫂薪資核銷
                cursor.execute(
                    "SELECT staff_id, amount_due_ntd FROM staff_obligations WHERE obligation_identity=%s",
                    (target_item,),
                )
                staff_ob = cursor.fetchone()
                if not staff_ob:
                    raise LookupError(f"查無月嫂應付項目: {target_item}")
                staff_id = staff_ob["staff_id"]

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
                # 更新 staff_payable_projections
                cursor.execute(
                    """
                    UPDATE staff_payable_projections
                    SET net_paid_ntd = net_paid_ntd + %s,
                        balance_ntd = GREATEST(0, obligation_amount_ntd - (net_paid_ntd + %s)),
                        status = CASE WHEN (net_paid_ntd + %s) >= obligation_amount_ntd THEN 'completed' ELSE 'partially_paid' END,
                        aggregate_version = aggregate_version + 1,
                        current_event_id = %s
                    WHERE obligation_identity=%s
                    """,
                    (amount_ntd, amount_ntd, amount_ntd, entry_id, target_item),
                )

            elif direction == "client_refund":
                # 客戶退款核銷
                cursor.execute(
                    """
                    INSERT INTO client_ledger_entries (
                        case_no, finance_import_row_id, entry_type, amount_ntd,
                        occurred_on, reconciliation_reference, idempotency_key, actor, reason
                    ) VALUES (%s, %s, 'refund', %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        case_no,
                        row_id,
                        amount_ntd,
                        transaction_date,
                        f"manual-refund:{row_id}",
                        idempotency_key,
                        actor,
                        note_text,
                    ),
                )
                entry_id = cursor.lastrowid
                cursor.execute(
                    """
                    INSERT INTO client_ledger_obligation_allocations (
                        ledger_entry_id, obligation_identity, amount_ntd, allocation_ordinal
                    ) VALUES (%s, %s, %s, 1)
                    """,
                    (entry_id, target_item, amount_ntd),
                )
                # 更新退款餘額與狀態（嚴格遵循 chk_client_obligation_state 約束）
                cursor.execute(
                    "SELECT amount_due_ntd FROM client_obligations WHERE obligation_identity=%s FOR UPDATE",
                    (target_item,),
                )
                ref_row = cursor.fetchone()
                if ref_row:
                    before_due = int(ref_row["amount_due_ntd"])
                    remaining = max(0, before_due - amount_ntd)
                    new_status = "settled" if remaining == 0 else "open"
                    cursor.execute(
                        """
                        UPDATE client_obligations
                        SET amount_due_ntd=%s, status=%s, projection_version=projection_version+1
                        WHERE obligation_identity=%s
                        """,
                        (remaining, new_status, target_item),
                    )
                cursor.execute(
                    "UPDATE client_finance_accounts SET aggregate_version=aggregate_version+1 WHERE case_no=%s",
                    (case_no,),
                )

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
