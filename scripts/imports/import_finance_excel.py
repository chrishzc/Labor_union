# -*- coding: utf-8 -*-
"""Import client bank receipts into the case-based client ledger.

Receipt amounts are never used to define a case's receivable amount.  A new
client-payment snapshot is derived only from the order's service terms.
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal

import pandas as pd
from dotenv import load_dotenv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.append(ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

from services.client_payment_transactions import calculate_client_payment_state
from services.client_payment_writer import build_client_summary_update
from services.db_service import get_connection
from services.order_amount_calculator import calculate_order_amounts


PAYMENT_STAGES = (
    ("deposit", "deposit_received"),
    ("first_payment", "first_payment_received"),
    ("second_payment", "second_payment_received"),
)


def allocate_receipt(receivables: dict, current_state: dict, amount) -> list[tuple[str, Decimal]]:
    """Allocate one receipt in collection-stage order without over-collection."""
    remaining = Decimal(str(amount))
    assert remaining > 0
    allocations = []
    for stage, received_key in PAYMENT_STAGES:
        stage_remaining = Decimal(str(receivables[stage])) - Decimal(str(current_state[received_key]))
        if stage_remaining <= 0:
            continue
        allocation = min(remaining, stage_remaining)
        allocations.append((stage, allocation))
        remaining -= allocation
        if remaining == 0:
            return allocations
    raise ValueError("receipt exceeds the remaining client receivable")


def decode_va_to_case_no(virtual_account):
    """Decode 99781699 + ROC year + sequence virtual account into case_no."""
    va_str = str(virtual_account).strip()
    if len(va_str) != 14 or not va_str.startswith("997816") or va_str[6:8] != "99":
        return None
    code_part = va_str[8:]
    if not code_part.isdigit():
        return None
    return f"{code_part[:3]}{int(code_part[3:]):06d}"


def normalize_header(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower().replace(" ", "")


def get_sheet_name(xl: pd.ExcelFile, expected: str) -> str:
    matches = {normalize_header(name): name for name in xl.sheet_names}
    try:
        return matches[normalize_header(expected)]
    except KeyError as exc:
        raise ValueError(f"找不到工作表：{expected}") from exc


def load_transactions(xl: pd.ExcelFile) -> pd.DataFrame:
    raw = xl.parse(get_sheet_name(xl, "銀行流水明細"), header=None)
    required = {"交易日期", "交易摘要", "支出", "收入", "虛擬帳號/對方帳號"}
    for row_index in range(min(10, len(raw))):
        headers = [str(value).strip() if pd.notna(value) else "" for value in raw.iloc[row_index]]
        if required.issubset(set(headers)):
            data = raw.iloc[row_index + 1:].copy()
            data.columns = headers
            return data[["交易日期", "交易摘要", "支出", "收入", "虛擬帳號/對方帳號"]]
    raise ValueError("找不到銀行流水明細的必要欄位")


def build_snapshot_plan(order: dict) -> dict | None:
    """Build a client ledger plan, or return None for a historical incomplete order."""
    if order.get("deposit_service_days") is None:
        return None
    service_start_date = order.get("actual_start_date") or order.get("start_date")
    if not service_start_date or not order.get("deposit_date"):
        return None
    return calculate_order_amounts(
        {
            "case_no": order["case_no"],
            "service_days": order.get("service_days"),
            "service_hours_per_day": order.get("service_hours_per_day"),
            "subsidy_eligibility": order.get("subsidy_eligibility"),
            "client_floor_fee": order.get("floor_fee", 0),
            "service_start_date": service_start_date,
            "actual_completion_date": order.get("actual_end_date"),
        },
        collection_schedule={
            "deposit_service_days": order["deposit_service_days"],
            "deposit_due_date": order["deposit_date"],
        },
    )


def create_client_payment_snapshot(cursor, plan: dict) -> int:
    """Persist the calculator's three-stage client ledger snapshot."""
    stages = {stage["stage"]: stage for stage in plan["client_ledger_plan"]["stages"]}
    cursor.execute(
        """INSERT INTO client_payments (
            case_no,
            deposit_receivable, deposit_due_date,
            first_payment_receivable, first_payment_due_date,
            second_payment_receivable, second_payment_due_date,
            amount_receivable, payment_status
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'待收訂金')""",
        (
            plan["case_no"],
            stages["deposit"]["receivable"], stages["deposit"]["due_date"],
            stages["first_payment"]["receivable"], stages["first_payment"]["due_date"],
            stages["second_payment"]["receivable"], stages["second_payment"]["due_date"],
            plan["client_ledger_plan"]["amount_receivable"],
        ),
    )
    return cursor.lastrowid


def _order_for_snapshot(cursor, case_no: str) -> dict | None:
    cursor.execute(
        """SELECT case_no, service_days, service_hours_per_day, subsidy_eligibility,
                  floor_fee, deposit_date, deposit_service_days,
                  start_date, actual_start_date, actual_end_date
           FROM orders WHERE case_no = %s FOR UPDATE""",
        (case_no,),
    )
    return cursor.fetchone()


def _existing_receipt_transactions(cursor, client_payment_id: int) -> list[dict]:
    cursor.execute(
        """SELECT stage, transaction_type, transaction_status, amount, occurred_at, external_reference
           FROM client_payment_transactions
           WHERE client_payment_id = %s
             AND stage IN ('deposit', 'first_payment', 'second_payment')
           ORDER BY occurred_at, id FOR UPDATE""",
        (client_payment_id,),
    )
    return cursor.fetchall()


def _record_receipt_allocation(cursor, payment: dict, transaction: dict, stage: str, amount: Decimal):
    candidate = {
        "stage": stage,
        "transaction_type": "receipt",
        "transaction_status": "succeeded",
        "amount": amount,
        "occurred_at": transaction["date"],
        "external_reference": f"excel:{payment['case_no']}:{transaction['idx']}:{stage}",
    }
    cursor.execute(
        """INSERT INTO client_payment_transactions
           (client_payment_id, case_no, stage, transaction_type, transaction_status,
            amount, occurred_at, external_reference, notes)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (payment["id"], payment["case_no"], stage, "receipt", "succeeded", amount,
         transaction["date"], candidate["external_reference"], "銀行 Excel 匯入"),
    )
    return candidate


def _update_client_summary(cursor, payment: dict, transactions: list[dict], occurred_at):
    receivables = {
        "deposit": payment["deposit_receivable"],
        "first_payment": payment["first_payment_receivable"],
        "second_payment": payment["second_payment_receivable"],
    }
    update = build_client_summary_update(receivables, transactions, occurred_at)
    cursor.execute(
        """UPDATE client_payments SET
            deposit_received=%s, first_payment_received=%s, second_payment_received=%s,
            amount_received=%s, deposit_received_at=%s, first_payment_received_at=%s,
            second_payment_received_at=%s, second_payment_due_date=%s
           WHERE id=%s""",
        (update["deposit_received"], update["first_payment_received"], update["second_payment_received"],
         update["amount_received"], update["deposit_received_at"], update["first_payment_received_at"],
         update["second_payment_received_at"], update["second_payment_due_date"], payment["id"]),
    )
    if update["deposit_received_at"]:
        cursor.execute(
            """UPDATE orders SET status = '訂單成立'
               WHERE case_no = %s AND status = '洽談中'""",
            (payment["case_no"],),
        )
    return update


def _parse_bank_transactions(df_tx: pd.DataFrame) -> tuple[dict[str, list[dict]], int]:
    transactions_by_case: dict[str, list[dict]] = {}
    skipped = 0
    for idx, row in df_tx.iterrows():
        if pd.isna(row.get("交易日期")):
            continue
        income_value = row.get("收入")
        income = Decimal(str(income_value)) if pd.notna(income_value) and str(income_value).strip() else Decimal("0")
        if income <= 0:
            if pd.notna(row.get("支出")):
                skipped += 1
            continue
        case_no = decode_va_to_case_no(row.get("虛擬帳號/對方帳號"))
        if not case_no:
            skipped += 1
            continue
        transactions_by_case.setdefault(case_no, []).append({
            "amount": income,
            "date": pd.to_datetime(row["交易日期"]).strftime("%Y-%m-%d"),
            "idx": idx,
        })
    for transactions in transactions_by_case.values():
        transactions.sort(key=lambda transaction: transaction["date"])
    return transactions_by_case, skipped


def import_bank_transactions(df_tx: pd.DataFrame) -> dict[str, int]:
    """Import parsed bank receipts atomically and return imported/skipped counts."""
    transactions_by_case, skipped_transactions = _parse_bank_transactions(df_tx)
    imported_client_transactions = 0
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            for case_no, bank_transactions in transactions_by_case.items():
                order = _order_for_snapshot(cursor, case_no)
                if not order:
                    skipped_transactions += len(bank_transactions)
                    continue
                cursor.execute("SELECT * FROM client_payments WHERE case_no = %s FOR UPDATE", (case_no,))
                payment = cursor.fetchone()
                if not payment:
                    plan = build_snapshot_plan(order)
                    if plan is None:
                        skipped_transactions += len(bank_transactions)
                        continue
                    payment_id = create_client_payment_snapshot(cursor, plan)
                    cursor.execute("SELECT * FROM client_payments WHERE id = %s FOR UPDATE", (payment_id,))
                    payment = cursor.fetchone()

                existing = _existing_receipt_transactions(cursor, payment["id"])
                receivables = {
                    "deposit": payment["deposit_receivable"],
                    "first_payment": payment["first_payment_receivable"],
                    "second_payment": payment["second_payment_receivable"],
                }
                current_state = calculate_client_payment_state(receivables, existing)
                for transaction in bank_transactions:
                    reference_prefix = f"excel:{case_no}:{transaction['idx']}:"
                    if any(str(item.get("external_reference") or "").startswith(reference_prefix) for item in existing):
                        continue
                    try:
                        allocations = allocate_receipt(receivables, current_state, transaction["amount"])
                    except ValueError:
                        skipped_transactions += 1
                        continue
                    for stage, amount in allocations:
                        candidate = _record_receipt_allocation(cursor, payment, transaction, stage, amount)
                        existing.append(candidate)
                        current_state = calculate_client_payment_state(receivables, existing)
                        imported_client_transactions += 1
                    _update_client_summary(cursor, payment, existing, transaction["date"])
        conn.commit()
        return {"imported_client_transactions": imported_client_transactions, "skipped_transactions": skipped_transactions}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Import finance Excel data")
    parser.add_argument("--check", action="store_true", help="Only verify readiness")
    parser.add_argument("--excel-path", default="document/帳務.xlsx")
    args = parser.parse_args()
    if args.check:
        print("READY TO IMPORT")
        return 0
    if not os.path.exists(args.excel_path):
        raise FileNotFoundError(f"找不到帳務 Excel：{args.excel_path}")
    result = import_bank_transactions(load_transactions(pd.ExcelFile(args.excel_path)))
    print(f"已匯入客戶交易：{result['imported_client_transactions']}")
    print(f"略過交易：{result['skipped_transactions']}")
    return 0


if __name__ == "__main__":
    assert decode_va_to_case_no("99781699115001") == "115000001"
    raise SystemExit(main())
