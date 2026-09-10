from datetime import date
from infrastructure.mysql.contract_full_preview_repository import _extend_actual_receipt_dates


class Cursor:
    def __init__(self, rows): self.rows = rows
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, args):
        assert args == ("CASE-1", "CASE-1")
        assert "reversal_of_entry_id" in sql and "allocation.amount_ntd>0" in sql
    def fetchall(self): return self.rows


class Connection:
    def __init__(self, rows): self.rows = rows
    def cursor(self): return Cursor(self.rows)


def test_unpaid_contract_never_uses_due_dates():
    facts = {"floor_fee": 100, "deposit_due_date": date(2026, 10, 1)}
    _extend_actual_receipt_dates(Connection([]), "CASE-1", facts, {})
    assert facts["deposit_receipt_date"] is None
    assert facts["floor_fee_receipt_date"] is None
    assert facts["first_receipt_date"] is None


def test_multiple_actual_receipt_dates_are_preserved_without_inventing_a_deadline():
    facts, owners = {"floor_fee": 100, "deposit_due_date": date(2026, 10, 1)}, {}
    _extend_actual_receipt_dates(Connection([
        {"obligation_type": "deposit", "occurred_on": date(2026, 9, 2)},
        {"obligation_type": "deposit", "occurred_on": date(2026, 9, 1)},
    ]), "CASE-1", facts, owners)
    assert facts["deposit_receipt_date"] == "2026-09-01、2026-09-02"
    assert facts["floor_fee_receipt_date"] == facts["deposit_receipt_date"]
    assert "client_receipt_dates" in owners
