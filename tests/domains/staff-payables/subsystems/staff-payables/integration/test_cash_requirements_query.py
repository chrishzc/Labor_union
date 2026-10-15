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
          source="formal_obligation", disposition="other_month"):
    return CaseStaffPayableAuditItem("C-01", 1, "月嫂甲", identity,
        None if amount is None else MoneyNTD(amount), None if balance is None else MoneyNTD(balance),
        due, due, source, disposition, "受款資料待確認" if disposition == "blocked" else "屬其他月份")


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


def test_staff_amounts_preserve_each_owner_balance_and_skip_paid_or_settled():
    rows = query(case(identity_status="非市民", staff_items=(
        staff(amount=24000, balance=15000), staff("staff:2", amount=18000, balance=18000),
        staff("staff:paid", balance=0, disposition="paid_or_settled"),
        staff("staff:settled", disposition="paid_or_settled"),
    ))).rows
    assert len(rows) == 2
    assert sum(r.unpaid_amount_ntd for r in rows) == 33000
    assert rows[0].source_amount_ntd == 24000
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
    from infrastructure.mysql.cash_requirements_repository import MySqlCashRequirementsRepository, _ARRANGED_STAFF_SQL

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql, params): self.sql = sql
        def fetchall(self):
            if self.sql == _ARRANGED_STAFF_SQL:
                return ({"staff_id": 1, "recipient_name": "月嫂甲"}, {"staff_id": 2, "recipient_name": "月嫂乙"})
            return ()
    class Connection:
        def cursor(self): return Cursor()
    class StaffSource:
        def load_case(self, case_no, payment_date):
            return (staff(balance=0, disposition="paid_or_settled"),)
    repository = MySqlCashRequirementsRepository(Connection())
    repository._staff = StaffSource()
    facts = repository._case({"case_no": "C-01", "client_name": "客戶甲", "order_status": "服務中",
        "has_arrangement": 1, "planned_end_date": date(2026, 11, 30), "identity_status": "非市民",
        "historical_hours": None, "work_day_count": 20, "service_hours_per_day": 9,
        "floor_fee": 0, "client_hourly_rate_ntd": 300, "receivable_count": 1,
        "open_receivable_count": 1, "return_count": 0})
    rows = query(facts).rows
    assert len(rows) == 1 and rows[0].recipient_name == "月嫂乙"
    assert rows[0].unpaid_amount_ntd is None and rows[0].payment_date is None
    assert rows[0].row_id == "C-01:staff:2"
