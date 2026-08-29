from datetime import date

from infrastructure.mysql.order_terms_read_model import _contract_charge_days


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None

    def execute(self, statement, parameters):
        self.statement = (statement, parameters)

    def fetchall(self):
        return self.rows


def test_contract_completion_prefers_execution_schedule_when_it_exists():
    cursor = _Cursor(())

    charge_days = _contract_charge_days(
        cursor,
        "CASE-1",
        ({"work_date": date(2026, 8, 1), "is_work_day": 1, "is_double_pay": 1},),
        lock=False,
    )

    assert [(item.service_date, item.is_double_pay) for item in charge_days] == [
        (date(2026, 8, 1), True)
    ]
    assert cursor.statement is None


def test_contract_completion_uses_active_precontract_commitment_before_execution():
    cursor = _Cursor([{"service_date": date(2026, 8, 1)}])

    charge_days = _contract_charge_days(cursor, "CASE-1", (), lock=True)

    assert [(item.service_date, item.is_double_pay) for item in charge_days] == [
        (date(2026, 8, 1), False)
    ]
    assert "precontract_service_commitment_days" in cursor.statement[0]
    assert cursor.statement[1] == ("CASE-1",)
