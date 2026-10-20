"""CASHPLAN-01..05: owner amounts, estimates, missing facts and read-only composition."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from shared_kernel.money import MoneyNTD
from subsystems.staff_payables.accounts_payable_export import CaseStaffPayableAuditItem
from subsystems.staff_payables.cash_requirements_query import (
    CashRefundFact, CashRequirementCase, query_cash_requirements,
)


def staff(identity="staff:1", *, amount=24000, balance=24000, due=date(2026, 11, 15),
          source="formal_obligation", disposition="other_month", payment_status="pending"):
    return CaseStaffPayableAuditItem("C-01", 1, "月嫂甲", identity,
        None if amount is None else MoneyNTD(amount), None if balance is None else MoneyNTD(balance),
        due, due, source, disposition, "受款資料待確認" if disposition == "blocked" else "屬其他月份", payment_status)


def case(**changes):
    base = CashRequirementCase("C-01", "客戶甲", "服務中", True, date(2026, 11, 30),
        "一般市民", Decimal(180), Decimal(0), 300, False, False, (staff(),), ())
    return replace(base, **changes)


class Repository:
    def __init__(self, cases):
        self.cases = cases
        self.calls = []

    def query_cases(self, after_case_no, limit):
        self.calls.append((after_case_no, limit))
        return tuple(c for c in self.cases if after_case_no is None or c.case_no > after_case_no)[:limit]


def query(*cases, **options):
    return query_cash_requirements(Repository(cases), **options)


def test_unarranged_case_has_no_estimate_and_arrangement_enables_capped_refund_before_completion():
    assert query(case(has_arrangement=False, staff_items=())).rows == ()
    rows = query(case()).rows
    assert [r.payment_type for r in rows] == ["staff_payable", "client_subsidy_return"]
    estimate = rows[1]
    assert estimate.unpaid_amount_ntd == 40 * 300
    assert estimate.payment_date == date(2027, 1, 15)
    assert estimate.certainty == "estimated" and estimate.date_is_estimate
    assert "服務尚未完成" in estimate.pending_reasons
    assert "客戶服務費尚未收齊" in estimate.pending_reasons


def test_staff_amounts_preserve_each_owner_balance_and_show_paid_or_settled():
    rows = query(case(identity_status="非市民", staff_items=(
        staff(amount=24000, balance=15000, payment_status="partially_paid"), staff("staff:2", amount=18000, balance=18000),
        staff("staff:paid", balance=0, disposition="paid_or_settled", payment_status="paid"),
        staff("staff:settled", balance=0, disposition="paid_or_settled", payment_status="settled"),
    ))).rows
    assert len(rows) == 4
    assert [r.payment_status for r in rows] == ["partially_paid", "pending", "paid", "settled"]
    assert sum(r.unpaid_amount_ntd for r in rows) == 33000
    assert rows[0].source_amount_ntd == 24000
    assert all(r.staff_id == 1 for r in rows)  # exact staff drilldown, never recipient-name matching
    assert all(r.certainty == "confirmed" for r in rows)
    assert all(r.payment_date == date(2026, 11, 15) and not r.date_is_estimate for r in rows)


def test_posted_refund_replaces_estimate_and_uses_current_remaining_and_real_date():
    refund = CashRefundFact("refund:1", "client_subsidy_return", 6000, date(2027, 2, 15), "客戶甲", False)
    rows = query(case(has_subsidy_return=True, refunds=(refund,), staff_items=())).rows
    assert len(rows) == 1
    assert rows[0].unpaid_amount_ntd == 6000
    assert rows[0].payment_date == date(2027, 2, 15)
    assert rows[0].certainty == "confirmed" and not rows[0].date_is_estimate
    assert "退款收款資料待確認" in rows[0].pending_reasons
    assert query(case(has_subsidy_return=True, refunds=(), staff_items=())).rows == ()


@pytest.mark.parametrize("status", ["paid", "settled"])
def test_terminal_refund_remains_visible_without_pending_reasons_or_forecast(status):
    refund = CashRefundFact("refund:paid", "client_subsidy_return", 0, None, "客戶甲", False, status, 6000)
    rows = query(case(has_subsidy_return=True, refunds=(refund,), staff_items=())).rows
    assert len(rows) == 1
    assert rows[0].payment_status == status
    assert rows[0].unpaid_amount_ntd == 0
    assert rows[0].source_amount_ntd == 6000
    assert rows[0].pending_reasons == ()


def test_cash_response_preserves_owner_payment_status():
    from types import SimpleNamespace
    from api.routes.finance_reports import query_accounts_payable_cash_requirements

    page = query(case(identity_status="非市民", staff_items=(
        staff("pending"),
        staff("partial", balance=1500, payment_status="partially_paid"),
        staff("paid", balance=0, disposition="paid_or_settled", payment_status="paid"),
        staff("settled", balance=0, disposition="paid_or_settled", payment_status="settled"),
    )))
    response = query_accounts_payable_cash_requirements(page_size=100, after_case_no=None,
        principal=SimpleNamespace(), application=SimpleNamespace(query=lambda **_: page))
    rows = response.model_dump()["data"]["rows"]
    assert [row["payment_status"] for row in rows] == ["pending", "partially_paid", "paid", "settled"]
    assert [row["unpaid_amount_ntd"] for row in rows] == [24000, 1500, 0, 0]


def test_refund_sql_reads_paid_partial_reversed_and_exact_historical_evidence():
    from contextlib import closing
    import sqlite3
    from infrastructure.mysql.cash_requirements_repository import _REFUNDS_SQL

    with closing(sqlite3.connect(":memory:")) as connection:
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            CREATE TABLE client_obligations (case_no TEXT, obligation_identity TEXT,
                obligation_type TEXT, direction TEXT, status TEXT, amount_due_ntd INTEGER, due_date TEXT, projection_version INTEGER);
            CREATE TABLE client_refund_recipient_snapshots (refund_obligation_identity TEXT, bank_code TEXT, bank_account TEXT);
            CREATE TABLE historical_client_payment_projections (obligation_identity TEXT, confirmation_kind TEXT,
                amount_snapshot_ntd INTEGER, obligation_projection_version INTEGER);
            CREATE TABLE client_ledger_entries (id INTEGER, case_no TEXT, entry_type TEXT, reversal_of_entry_id INTEGER);
            CREATE TABLE client_ledger_obligation_allocations (ledger_entry_id INTEGER, obligation_identity TEXT, amount_ntd INTEGER);
            INSERT INTO client_obligations VALUES
                ('C-01','paid','refund','payable_to_client','settled',0,NULL,1),
                ('C-01','partial','refund','payable_to_client','open',2000,NULL,1),
                ('C-01','reversed','refund','payable_to_client','open',6000,NULL,1),
                ('C-01','historical','subsidy_return','payable_to_client','open',6000,NULL,1),
                ('C-01','stale','subsidy_return','payable_to_client','open',6000,NULL,2),
                ('C-01','cancelled','refund','payable_to_client','cancelled',6000,NULL,1);
            INSERT INTO historical_client_payment_projections VALUES ('historical','paid',6000,1),('stale','paid',6000,1);
            INSERT INTO client_ledger_entries VALUES (1,'C-01','refund',NULL),(2,'C-01','refund',NULL),
                (3,'C-01','refund',NULL),(4,'C-01','reversal',3);
            INSERT INTO client_ledger_obligation_allocations VALUES
                (1,'paid',6000),(2,'partial',4000),(3,'reversed',6000),(4,'reversed',6000);
        """)
        rows = {row["obligation_identity"]: row for row in connection.execute(_REFUNDS_SQL.replace("%s", "?"), ("C-01", "C-01"))}
        assert rows["paid"]["net_paid_ntd"] == 6000
        assert rows["partial"]["net_paid_ntd"] == 4000
        assert rows["reversed"]["net_paid_ntd"] == 0
        assert rows["historical"]["confirmation_kind"] == "paid"
        assert rows["stale"]["confirmation_kind"] is None
        assert "cancelled" not in rows


def test_cancelled_case_retains_established_unpaid_but_does_not_forecast_unperformed_refund():
    refund = CashRefundFact("refund:cancel", "client_refund", 2000, None, "客戶甲", True)
    rows = query(case(order_status="訂單取消", has_arrangement=False, refunds=(refund,))).rows
    assert {r.payment_type for r in rows} == {"staff_payable", "client_refund"}
    assert rows[1].payment_date is None


@pytest.mark.parametrize("identity", ["補助市民", "低收入戶", "中低收入戶", "非市民"])
def test_full_subsidy_without_client_payment_or_ineligible_identity_has_no_refund_estimate(identity):
    assert query(case(identity_status=identity, service_hours=Decimal(80), staff_items=())).rows == ()


def test_missing_amount_and_date_remain_unknown_and_bank_blocker_is_visible():
    rows = query(case(service_hours=None, planned_end_date=None, service_fees_collected=None,
        staff_items=(staff(amount=None, balance=None, due=None, source="order_facts", disposition="date_not_formed"),))).rows
    assert len(rows) == 2
    assert all(r.unpaid_amount_ntd is None and r.payment_date is None for r in rows)
    assert all(r.pending_reasons for r in rows)
    blocked = query(case(identity_status="非市民", staff_items=(staff(disposition="blocked"),))).rows[0]
    assert blocked.unpaid_amount_ntd == 24000
    assert "月嫂付款狀態或受款資料待確認" in blocked.pending_reasons


def test_requery_observes_changes_without_mutating_facts_or_posting_refund():
    original = case()
    repository = Repository((original,))
    first = query_cash_requirements(repository)
    repository.cases = (replace(original, planned_end_date=date(2026, 12, 4), client_hourly_rate_ntd=350),)
    second = query_cash_requirements(repository)
    assert first.rows[-1].unpaid_amount_ntd == 12000
    assert second.rows[-1].unpaid_amount_ntd == 14000
    assert second.rows[-1].payment_date == date(2027, 2, 15)
    assert original.refunds == () and original.planned_end_date == date(2026, 11, 30)


def test_cursor_advances_even_when_first_case_has_no_outstanding_rows():
    repository = Repository((case(has_subsidy_return=True, staff_items=()), case(case_no="C-02", staff_items=())))
    first = query_cash_requirements(repository, page_size=1)
    assert first.rows == () and first.next_cursor == "C-01"
    second = query_cash_requirements(repository, page_size=1, after_case_no=first.next_cursor)
    assert len(second.rows) == 1 and second.rows[0].case_no == "C-02" and second.next_cursor is None
    assert repository.calls == [(None, 2), ("C-01", 2)]


def test_cash_query_composition_rolls_back_read_snapshot_without_committing(monkeypatch):
    from api.dependencies import accounts_payable_export as composition

    statements = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, statement): statements.append(statement)
    class Connection:
        def cursor(self): return Cursor()
        def rollback(self): statements.append("rollback")
        def commit(self): raise AssertionError("cash query must never commit")
    monkeypatch.setattr(composition, "MySqlCashRequirementsRepository", lambda connection: Repository((case(),)))
    page = composition.CashRequirementsApplication(Connection()).query()
    assert len(page.rows) == 2
    assert statements == ["SET TRANSACTION ISOLATION LEVEL REPEATABLE READ",
        "START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY", "rollback"]


def test_arranged_staff_with_missing_payroll_is_visible_without_relisting_paid_successor():
    from infrastructure.mysql.cash_requirements_repository import MySqlCashRequirementsRepository

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql, params): self.sql = sql
        def fetchall(self):
            return ()
    class Connection:
        def cursor(self): return Cursor()
    class StaffSource:
        def load_case(self, case_no, payment_date):
            return (staff(balance=0, disposition="paid_or_settled", payment_status="paid"),
                    replace(staff("C-01:staff:2", amount=None, balance=None, due=None, source="order_facts"),
                            staff_id=2, recipient_name="月嫂乙"))
    repository = MySqlCashRequirementsRepository(Connection())
    repository._staff = StaffSource()
    facts = repository._case({"case_no": "C-01", "client_name": "客戶甲", "order_status": "服務中",
        "has_arrangement": 1, "planned_end_date": date(2026, 11, 30), "identity_status": "非市民",
        "historical_hours": None, "work_day_count": 20, "service_hours_per_day": 9,
        "floor_fee": 0, "client_hourly_rate_ntd": 300, "receivable_count": 1,
        "open_receivable_count": 1, "return_count": 0})
    rows = query(facts).rows
    assert len(rows) == 2 and rows[0].payment_status == "paid"
    assert rows[1].recipient_name == "月嫂乙"
    assert rows[1].unpaid_amount_ntd is None and rows[1].payment_date is None
    assert rows[1].row_id == "C-01:staff:2"
