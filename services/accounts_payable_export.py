"""Read-only monthly accounts-payable export for bank transfers."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
import re

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from services.db_service import get_connection


EXPORT_HEADERS = (
    "月份-銀行代碼-流水號",
    "銀行名稱",
    "客戶or服務人員姓名",
    "銀行帳號",
    "銀行代號(碼)",
    "金額",
    "身分證字號(匯款到永豐才要填)",
    "案件編號",
    "匯款日期",
)

OUTGOING_BANKS = {
    "31": "永豐銀行",
    "633": "台新銀行",
}


def _month_bounds(target_month: str) -> tuple[date, date]:
    if not isinstance(target_month, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", target_month):
        raise ValueError("target_month 必須為 YYYY-MM")
    try:
        first_day = datetime.strptime(target_month, "%Y-%m").date().replace(day=1)
    except (TypeError, ValueError) as exc:
        raise ValueError("target_month 必須為 YYYY-MM") from exc

    last_day = date(
        first_day.year,
        first_day.month,
        monthrange(first_day.year, first_day.month)[1],
    )
    return first_day, last_day


def _as_decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _fetch_payables(target_month: str) -> list[dict]:
    first_day, last_day = _month_bounds(target_month)
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT sp.id AS source_payment_id,
                       sp.case_no,
                       sp.due_date AS transfer_date,
                       sp.total_payable - sp.amount_paid AS amount,
                       s.name AS recipient_name,
                       s.identity_card,
                       sba.account_no,
                       sba.bank_code AS recipient_bank_code
                FROM staff_payments sp
                JOIN staff s ON s.id = sp.staff_id
                LEFT JOIN staff_bank_accounts sba ON sba.id = (
                    SELECT sba2.id
                    FROM staff_bank_accounts sba2
                    WHERE sba2.staff_id = sp.staff_id
                      AND sba2.is_primary = 1
                    ORDER BY sba2.id
                    LIMIT 1
                )
                WHERE sp.payment_status IN ('pending', 'partially_paid')
                  AND sp.due_date BETWEEN %s AND %s
                  AND sp.total_payable - sp.amount_paid > 0
                """,
                (first_day, last_day),
            )
            staff_rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT cp.id AS source_payment_id,
                       cp.case_no,
                       cp.subsidy_return_due_date AS transfer_date,
                       cp.subsidy_return_receivable - cp.subsidy_return_refunded AS amount,
                       c.name AS recipient_name,
                       br.refund_account_no AS account_no,
                       br.refund_bank_code AS recipient_bank_code
                FROM client_payments cp
                JOIN clients c ON c.case_no = cp.case_no
                LEFT JOIN beclass_records br ON br.query_no = cp.case_no
                WHERE cp.subsidy_return_due_date BETWEEN %s AND %s
                  AND cp.subsidy_return_receivable - cp.subsidy_return_refunded > 0
                """,
                (first_day, last_day),
            )
            client_rows = cursor.fetchall()

    finally:
        conn.close()

    rows = []
    for row in staff_rows:
        rows.append({
            **row,
            "outgoing_bank_code": "31",
            "outgoing_bank_name": OUTGOING_BANKS["31"],
            "source_type": "staff_payment",
        })
    for row in client_rows:
        rows.append({
            **row,
            "identity_card": "",
            "outgoing_bank_code": "633",
            "outgoing_bank_name": OUTGOING_BANKS["633"],
            "source_type": "client_subsidy_return",
        })
    rows.sort(key=lambda row: (
        row["outgoing_bank_code"],
        row["transfer_date"],
        str(row["case_no"]),
        row["source_payment_id"],
    ))
    return rows


def _build_workbook(payable_rows: list[dict], bank_totals: dict[str, Decimal]) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "應付匯款清單"
    worksheet.append(EXPORT_HEADERS)

    yellow_fill = PatternFill(fill_type="solid", fgColor="FFFF00")
    for cell in worksheet[1]:
        cell.fill = yellow_fill
        cell.font = Font(bold=True)

    for row in payable_rows:
        worksheet.append(tuple(row[header] for header in EXPORT_HEADERS))

    worksheet.append(())
    for code in ("31", "633"):
        worksheet.append((f"{OUTGOING_BANKS[code]}總額", "", "", "", "", float(bank_totals[code])))

    worksheet.freeze_panes = "A2"
    worksheet.column_dimensions["A"].width = 24
    worksheet.column_dimensions["B"].width = 14
    worksheet.column_dimensions["C"].width = 22
    worksheet.column_dimensions["D"].width = 22
    worksheet.column_dimensions["E"].width = 16
    worksheet.column_dimensions["F"].width = 14
    worksheet.column_dimensions["G"].width = 30
    worksheet.column_dimensions["H"].width = 16
    worksheet.column_dimensions["I"].width = 14

    for row_index in range(2, 2 + len(payable_rows)):
        worksheet.cell(row=row_index, column=4).number_format = "@"
        worksheet.cell(row=row_index, column=5).number_format = "@"
        worksheet.cell(row=row_index, column=9).number_format = "yyyy-mm-dd"

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def build_accounts_payable_export(target_month: str) -> dict:
    """Build a read-only monthly payable list and in-memory XLSX workbook."""
    source_rows = _fetch_payables(target_month)
    serials = {"31": 0, "633": 0}
    bank_totals = {"31": Decimal("0"), "633": Decimal("0")}
    payable_rows = []

    for source_row in source_rows:
        bank_code = source_row["outgoing_bank_code"]
        serials[bank_code] += 1
        amount = _as_decimal(source_row["amount"])
        bank_totals[bank_code] += amount
        payable_rows.append({
            EXPORT_HEADERS[0]: f"{int(target_month[5:7])}-{bank_code}-{serials[bank_code]}",
            EXPORT_HEADERS[1]: source_row["outgoing_bank_name"],
            EXPORT_HEADERS[2]: source_row.get("recipient_name") or "",
            EXPORT_HEADERS[3]: str(source_row.get("account_no") or ""),
            EXPORT_HEADERS[4]: str(source_row.get("recipient_bank_code") or ""),
            EXPORT_HEADERS[5]: amount,
            EXPORT_HEADERS[6]: source_row.get("identity_card") or "",
            EXPORT_HEADERS[7]: str(source_row["case_no"]),
            EXPORT_HEADERS[8]: source_row["transfer_date"],
        })

    return {
        "payable_rows": payable_rows,
        "xlsx_bytes": _build_workbook(payable_rows, bank_totals),
        "bank_totals": bank_totals,
    }
