from decimal import Decimal

import pytest

from services import actual_hours_adjustment_confirmation_service as service


class FakeCursor:
    def __init__(self, order, assignments, payment=None, settlement=None):
        self.order = order
        self.assignments = assignments
        self.payment = payment
        self.settlement = settlement
        self.executed = []
        self.current = None

    def execute(self, sql, params=()):
        self.executed.append((" ".join(sql.split()), params))
        if "FROM orders" in sql:
            self.current = self.order
        elif "FROM case_staff_assignments" in sql:
            self.current = self.assignments
        elif "FROM staff_payments" in sql:
            self.current = self.payment
        elif "FROM staff_monthly_settlement_details" in sql:
            self.current = self.settlement
        else:
            self.current = None

    def fetchone(self):
        return self.current

    def fetchall(self):
        return self.current

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class FakeConnection:
    def __init__(self, order, assignments, payment=None, settlement=None):
        self.cursor_obj = FakeCursor(order, assignments, payment, settlement)
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


def _order(days=2, hours_per_day=Decimal("4.5")):
    return {"service_days": days, "service_hours_per_day": hours_per_day}


def _assignment(assignment_id, actual_hours, staff_id=7):
    return {
        "assignment_id": assignment_id,
        "staff_id": staff_id,
        "actual_hours": actual_hours,
        "status": "active",
    }


def test_validation_uses_exact_decimal_total_for_all_active_assignments(monkeypatch):
    connection = FakeConnection(
        _order(), [_assignment(11, Decimal("4.5")), _assignment(12, Decimal("4.5"), 8)]
    )
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    result = service.validate_case_actual_hours_for_payment("115000001")

    assert result == {
        "case_no": "115000001",
        "target_hours": Decimal("9.0"),
        "actual_hours_total": Decimal("9.0"),
        "difference": Decimal("0.0"),
        "assignments": [
            {"assignment_id": 11, "staff_id": 7, "actual_hours": Decimal("4.5")},
            {"assignment_id": 12, "staff_id": 8, "actual_hours": Decimal("4.5")},
        ],
        "can_confirm": True,
    }
    assert connection.closed is True


def test_validation_marks_missing_actual_hours_as_not_confirmable(monkeypatch):
    connection = FakeConnection(_order(), [_assignment(11, None), _assignment(12, Decimal("4.5"), 8)])
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    result = service.validate_case_actual_hours_for_payment("115000001")

    assert result["can_confirm"] is False
    assert result["actual_hours_total"] is None
    assert result["difference"] is None
    assert result["assignments"][0]["actual_hours"] is None


def test_adjustment_appends_audit_before_updating_only_the_requested_assignment(monkeypatch):
    assignments = [_assignment(11, Decimal("2.5")), _assignment(12, Decimal("6"), 8)]
    connection = FakeConnection(_order(), assignments)
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    result = service.adjust_actual_hours_before_payment(
        "115000001",
        [{"assignment_id": 11, "adjusted_actual_hours": "3.0", "adjustment_reason": "half-day handoff"}],
        "operator-7",
    )

    assert result["confirmation"]["can_confirm"] is True
    assert result["adjustment_records"] == [
        {
            "assignment_id": 11,
            "previous_actual_hours": Decimal("2.5"),
            "adjusted_actual_hours": Decimal("3.0"),
            "adjustment_reason": "half-day handoff",
            "adjusted_by": "operator-7",
        }
    ]
    writes = [item for item in connection.cursor_obj.executed if item[0].startswith(("INSERT INTO actual_hours_adjustments", "UPDATE case_staff_assignments"))]
    assert writes[0][0].startswith("INSERT INTO actual_hours_adjustments")
    assert writes[0][1] == (11, Decimal("2.5"), Decimal("3.0"), "half-day handoff", "operator-7")
    assert writes[1][0].startswith("UPDATE case_staff_assignments SET actual_hours")
    assert writes[1][1] == (Decimal("3.0"), 11)
    assert all(params[-1] != 12 for sql, params in writes if sql.startswith("UPDATE"))
    assert connection.commits == 1


def test_adjustment_rejects_locked_assignment_without_writing(monkeypatch):
    connection = FakeConnection(_order(), [_assignment(11, Decimal("9"))], payment={"assignment_id": 11})
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    with pytest.raises(ValueError, match="active staff payment"):
        service.adjust_actual_hours_before_payment(
            "115000001",
            [{"assignment_id": 11, "adjusted_actual_hours": "8", "adjustment_reason": "correction"}],
            "operator-7",
        )

    assert not any(sql.startswith(("INSERT INTO actual_hours_adjustments", "UPDATE case_staff_assignments")) for sql, _ in connection.cursor_obj.executed)
    assert connection.rollbacks == 1


def test_adjustment_rejects_cancelled_or_cross_case_assignment(monkeypatch):
    connection = FakeConnection(_order(), [_assignment(11, Decimal("9"))])
    monkeypatch.setattr(service, "get_connection", lambda: connection)

    with pytest.raises(ValueError, match="does not belong"):
        service.adjust_actual_hours_before_payment(
            "115000001",
            [{"assignment_id": 12, "adjusted_actual_hours": "8", "adjustment_reason": "correction"}],
            "operator-7",
        )

    assert connection.rollbacks == 1
