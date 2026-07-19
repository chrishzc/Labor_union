from datetime import date
from decimal import Decimal

import pytest

from services import staff_monthly_settlements as service


class FakeCursor:
    def __init__(self, responses):
        self.responses = list(responses)
        self.current = None
        self.executed = []
        self.lastrowid = 501

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))
        if sql.lstrip().upper().startswith("SELECT"):
            self.current = self.responses.pop(0)

    def fetchone(self):
        return self.current

    def fetchall(self):
        return self.current


class FakeConnection:
    def __init__(self, responses):
        self.cursor_obj = FakeCursor(responses)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def payment(payment_id, staff_id=8, case_no="115000001", assignment_id=21, salary="1000", floor="100", adjustment="0"):
    return {
        "id": payment_id,
        "assignment_id": assignment_id,
        "case_no": case_no,
        "staff_id": staff_id,
        "service_salary": Decimal(salary),
        "floor_fee_amount": Decimal(floor),
        "adjustment_amount": Decimal(adjustment),
        "total_payable": Decimal(salary) + Decimal(floor) + Decimal(adjustment),
        "payment_status": "pending",
        "assignment_case_no": case_no,
        "assignment_staff_id": staff_id,
        "assignment_status": "confirmed",
    }


def test_creates_one_monthly_settlement_for_two_cases(monkeypatch):
    connection = FakeConnection([
        None,
        None,
        payment(1),
        payment(2, case_no="115000002", assignment_id=22, salary="2000", floor="0"),
    ])
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    result = service.create_staff_monthly_settlement(
        8, "2026-07-01", 1,
        [{"staff_payment_id": 1}, {"staff_payment_id": 2}],
    )

    assert result["result"] == "created"
    assert result["settlement"]["settlement_month"] == date(2026, 7, 1)
    assert result["settlement"]["total_payable"] == Decimal("3100")
    assert len(result["settlement"]["details"]) == 2
    assert connection.commits == 1


def test_nonzero_legacy_subsidy_without_confirmed_evidence_requires_review(monkeypatch):
    connection = FakeConnection([None, None, payment(1)])
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    result = service.create_staff_monthly_settlement(
        8, date(2026, 7, 1), 1,
        [{"staff_payment_id": 1, "legacy_subsidy_payable": "300", "legacy_subsidy_status": "confirmed"}],
    )

    assert result["result"] == "review_required"
    detail = result["settlement"]["details"][0]
    assert detail["legacy_subsidy_status"] == "review_required"
    assert detail["review_required"] is True


def test_confirmed_legacy_subsidy_with_evidence_is_accepted(monkeypatch):
    connection = FakeConnection([None, None, payment(1)])
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    result = service.create_staff_monthly_settlement(
        8, "2026-07-01", 1,
        [{
            "staff_payment_id": 1,
            "legacy_subsidy_payable": "300",
            "legacy_subsidy_status": "confirmed",
            "review_note": "舊制第二次補助明細已人工確認",
        }],
    )

    assert result["result"] == "created"
    assert result["settlement"]["total_payable"] == Decimal("1400")


def test_rejects_other_staff_payment(monkeypatch):
    connection = FakeConnection([None, None, payment(1, staff_id=9)])
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    with pytest.raises(ValueError, match="another staff"):
        service.create_staff_monthly_settlement(8, "2026-07-01", 1, [{"staff_payment_id": 1}])

    assert connection.rollbacks == 1


def test_rejects_non_month_start_without_opening_connection(monkeypatch):
    monkeypatch.setattr(service, "get_connection", lambda: (_ for _ in ()).throw(AssertionError("must not connect")))

    with pytest.raises(ValueError, match="first day"):
        service.create_staff_monthly_settlement(8, "2026-07-15", 1, [{"staff_payment_id": 1}])


def test_identical_existing_snapshot_is_idempotent(monkeypatch):
    existing = {
        "id": 10, "staff_id": 8, "settlement_month": date(2026, 7, 1),
        "revision": 1, "total_payable": Decimal("1100"), "total_paid": Decimal("0"),
        "status": "draft", "finalized_at": None,
    }
    existing_details = [{
        "staff_payment_id": 1, "case_no": "115000001", "assignment_id": 21,
        "staff_id": 8, "service_salary": Decimal("1000"),
        "legacy_subsidy_payable": Decimal("0"), "floor_fee_amount": Decimal("100"),
        "adjustment_amount": Decimal("0"), "payable_amount": Decimal("1100"),
        "legacy_subsidy_status": "not_applicable", "review_required": False,
        "review_note": None,
    }]
    connection = FakeConnection([existing, None, payment(1), existing_details])
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    result = service.create_staff_monthly_settlement(8, "2026-07-01", 1, [{"staff_payment_id": 1}])

    assert result["result"] == "existing"
    assert connection.commits == 0


def test_identical_finalized_snapshot_retry_is_existing(monkeypatch):
    existing = {
        "id": 10, "staff_id": 8, "settlement_month": date(2026, 7, 1),
        "revision": 1, "total_payable": Decimal("1100"), "total_paid": Decimal("0"),
        "status": "finalized", "finalized_at": "2026-07-31 12:00:00",
    }
    existing_details = [{
        "staff_payment_id": 1, "case_no": "115000001", "assignment_id": 21,
        "staff_id": 8, "service_salary": Decimal("1000"),
        "legacy_subsidy_payable": Decimal("0"), "floor_fee_amount": Decimal("100"),
        "adjustment_amount": Decimal("0"), "payable_amount": Decimal("1100"),
        "legacy_subsidy_status": "not_applicable", "review_required": False,
        "review_note": None,
    }]
    connection = FakeConnection([existing, None, payment(1), existing_details])
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    result = service.create_staff_monthly_settlement(
        8, "2026-07-01", 1, [{"staff_payment_id": 1}]
    )

    assert result["result"] == "existing"
    assert result["settlement"]["status"] == "finalized"
    assert not any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in connection.cursor_obj.executed)


@pytest.mark.parametrize("other_status", ["draft", "finalized", "paid", "review_required"])
def test_payment_in_other_non_cancelled_settlement_requires_review(
    monkeypatch, other_status
):
    conflict = {
        "staff_payment_id": 1,
        "settlement_id": 44,
        "staff_id": 8,
        "settlement_month": date(2026, 6, 1),
        "revision": 2,
        "status": other_status,
    }
    connection = FakeConnection([None, conflict])
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    result = service.create_staff_monthly_settlement(
        8, "2026-07-01", 1, [{"staff_payment_id": 1}]
    )

    assert result == {
        "result": "review_required",
        "reason": "staff_payment_already_in_active_settlement",
        "staff_payment_id": 1,
        "settlement_id": 44,
    }
    assert not any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in connection.cursor_obj.executed)


def test_cancelled_other_settlement_does_not_block(monkeypatch):
    connection = FakeConnection([None, None, payment(1)])
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    result = service.create_staff_monthly_settlement(
        8, "2026-07-01", 1, [{"staff_payment_id": 1}]
    )

    assert result["result"] == "created"
    conflict_sql = connection.cursor_obj.executed[1][0]
    assert "sms.status <> 'cancelled'" in conflict_sql


def test_reads_formal_staff_payment_status_and_rejects_cancelled(monkeypatch):
    source = payment(1)
    source["payment_status"] = "cancelled"
    connection = FakeConnection([None, None, source])
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    with pytest.raises(ValueError, match="cancelled staff_payment"):
        service.create_staff_monthly_settlement(
            8, "2026-07-01", 1, [{"staff_payment_id": 1}]
        )

    payment_sql = connection.cursor_obj.executed[2][0]
    assert "sp.payment_status" in payment_sql


def test_finalizes_review_free_exact_settlement(monkeypatch):
    header = {
        "id": 10, "staff_id": 8, "settlement_month": date(2026, 7, 1),
        "revision": 1, "total_payable": Decimal("1100"), "total_paid": Decimal("0"),
        "status": "draft", "finalized_at": None,
    }
    connection = FakeConnection([header, [{"payable_amount": Decimal("1100"), "review_required": False}]])
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    result = service.finalize_staff_monthly_settlement(10)

    assert result["result"] == "finalized"
    assert result["settlement"]["status"] == "finalized"
    assert connection.commits == 1


def test_review_detail_cannot_finalize(monkeypatch):
    header = {
        "id": 10, "staff_id": 8, "settlement_month": date(2026, 7, 1),
        "revision": 1, "total_payable": Decimal("1100"), "total_paid": Decimal("0"),
        "status": "review_required", "finalized_at": None,
    }
    connection = FakeConnection([header, [{"payable_amount": Decimal("1100"), "review_required": True}]])
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    result = service.finalize_staff_monthly_settlement(10)

    assert result["result"] == "review_required"
    assert connection.commits == 1
