from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import load_workbook

from services import accounts_payable_export


class FakeCursor:
    def __init__(self, staff_identity_rows, client_rows):
        self.staff_identity_rows = staff_identity_rows
        self.client_rows = client_rows
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params):
        self.executed.append((" ".join(sql.split()), params))

    def fetchall(self):
        sql = self.executed[-1][0]
        return self.staff_identity_rows if "FROM staff s" in sql else self.client_rows


class FakeConnection:
    def __init__(self, staff_identity_rows, client_rows):
        self.cursor_instance = FakeCursor(staff_identity_rows, client_rows)
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def test_build_accounts_payable_export_is_read_only_and_bank_serials_reset(monkeypatch):
    connection = FakeConnection(
        staff_identity_rows=[
            {
                "staff_id": 11,
                "recipient_name": "月嫂乙",
                "identity_card": "B200000002",
                "account_no": "002222222222",
                "recipient_bank_code": "812",
            },
            {
                "staff_id": 10,
                "recipient_name": "月嫂甲",
                "identity_card": "A100000001",
                "account_no": "001111111111",
                "recipient_bank_code": "004",
            },
        ],
        client_rows=[
            {
                "source_payment_id": 8,
                "case_no": "115000003",
                "transfer_date": date(2026, 7, 15),
                "amount": Decimal("12000.00"),
                "recipient_name": "客戶丙",
                "account_no": "003333333333",
                "recipient_bank_code": "8220012",
            }
        ],
    )
    monkeypatch.setattr(accounts_payable_export, "get_connection", lambda: connection)
    preparation_calls = []
    monkeypatch.setattr(
        accounts_payable_export,
        "prepare_monthly_payments",
        lambda target_month: preparation_calls.append(target_month) or [
            {
                "settlement_id": 2,
                "staff_id": 11,
                "transfer_date": date(2026, 7, 20),
                "total_payable": Decimal("18000.00"),
                "total_paid": Decimal("0"),
                "remaining_amount": Decimal("18000.00"),
                "case_nos": ["115000002", "115000004"],
                "staff_payment_ids": [2, 4],
            },
            {
                "settlement_id": 1,
                "staff_id": 10,
                "transfer_date": date(2026, 7, 10),
                "total_payable": Decimal("32000.00"),
                "total_paid": Decimal("0"),
                "remaining_amount": Decimal("32000.00"),
                "case_nos": ["115000001"],
                "staff_payment_ids": [1],
            },
        ],
    )

    result = accounts_payable_export.build_accounts_payable_export("2026-07")

    rows = result["payable_rows"]
    assert [row["月份-銀行代碼-流水號"] for row in rows] == [
        "7-31-1",
        "7-31-2",
        "7-633-1",
    ]
    assert preparation_calls == ["2026-07"]
    assert rows[0]["案件編號"] == "115000001"
    assert rows[1]["案件編號"] == "115000002,115000004"
    assert rows[2]["客戶or服務人員姓名"] == "客戶丙"
    assert rows[2]["身分證字號(匯款到永豐才要填)"] == ""
    assert result["bank_totals"] == {
        "31": Decimal("50000.00"),
        "633": Decimal("12000.00"),
    }

    assert connection.closed is True
    assert len(connection.cursor_instance.executed) == 2
    for sql, _params in connection.cursor_instance.executed:
        assert not any(keyword in sql.upper() for keyword in ("INSERT ", "UPDATE ", "DELETE "))

    staff_sql, staff_params = connection.cursor_instance.executed[0]
    assert "FROM staff s" in staff_sql
    assert "FROM staff_payments" not in staff_sql
    assert staff_params == (10, 11)

    client_params = connection.cursor_instance.executed[1][1]
    assert client_params == (date(2026, 7, 1), date(2026, 7, 31))

    client_sql = connection.cursor_instance.executed[1][0].upper()
    assert "CLIENT_PAYMENTS" in client_sql
    assert "SUBSIDY_RETURN_RECEIVABLE" in client_sql
    assert "SUBSIDY_REFUND" not in client_sql

    workbook = load_workbook(BytesIO(result["xlsx_bytes"]))
    worksheet = workbook["應付匯款清單"]
    assert worksheet.max_column == 9
    assert [cell.value for cell in worksheet[1]] == list(accounts_payable_export.EXPORT_HEADERS)
    assert all(cell.fill.fgColor.rgb == "00FFFF00" for cell in worksheet[1])
    assert worksheet.cell(row=2, column=1).value == "7-31-1"
    assert worksheet.cell(row=6, column=1).value == "永豐銀行總額"
    assert worksheet.cell(row=7, column=1).value == "台新銀行總額"


def test_invalid_target_month_is_rejected_before_database_access(monkeypatch):
    monkeypatch.setattr(
        accounts_payable_export,
        "prepare_monthly_payments",
        lambda _target_month: (_ for _ in ()).throw(AssertionError("preparation must not run")),
    )
    monkeypatch.setattr(
        accounts_payable_export,
        "get_connection",
        lambda: (_ for _ in ()).throw(AssertionError("database must not be opened")),
    )

    try:
        accounts_payable_export.build_accounts_payable_export("2026-7")
    except ValueError as exc:
        assert "YYYY-MM" in str(exc)
    else:
        raise AssertionError("invalid target_month must be rejected")
