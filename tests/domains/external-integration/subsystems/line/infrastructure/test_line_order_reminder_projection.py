from datetime import date, datetime, timezone

from infrastructure.mysql.order_pre_start_notification_source_repository import (
    MySqlOrderPreStartNotificationSourceRepository,
)
from subsystems.line.notification_source_adapters import (
    from_order_pre_start_checkpoint,
    from_order_second_payment_checkpoint,
)
from subsystems.line.order_pre_start_notification_source import (
    OrderPreStartNotificationSourceProjector,
)


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params):
        self.executed = (sql, params)

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.cursor_instance = _Cursor(rows)

    def cursor(self):
        return self.cursor_instance


def test_pre_start_scan_is_keyed_by_service_date_and_preserves_payment_deadline():
    connection = _Connection(
        [
            {
                "case_no": "CASE-310-A",
                "service_start_date": date(2026, 9, 20),
                "first_payment_due_date": date(2026, 9, 18),
                "first_payment_required": 10000,
                "first_payment_received": 4000,
                "client_line_user_id": "U310",
            }
        ]
    )
    repository = MySqlOrderPreStartNotificationSourceRepository(connection)

    candidates = repository.find_due_candidates(date(2026, 9, 20))

    sql, params = connection.cursor_instance.executed
    assert "o.service_start_date = %s" in sql
    assert "p.first_payment_due_date = %s" not in sql
    assert params == ("2026-09-20",)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.planned_start_date == "2026-09-20"
    assert candidate.first_payment_due_date == "2026-09-18"
    assert candidate.first_payment_amount == 6000
    assert candidate.payment_state == "partial"
    assert candidate.already_settled is False


def test_second_payment_scan_keeps_missing_and_zero_obligation_states_distinct():
    connection = _Connection(
        [
            {
                "case_no": "CASE-310-MISSING",
                "service_start_date": date(2026, 9, 1),
                "second_payment_due_date": date(2026, 9, 20),
                "second_payment_required": None,
                "second_payment_received": 0,
                "client_line_user_id": None,
            },
            {
                "case_no": "CASE-310-ZERO",
                "service_start_date": date(2026, 9, 2),
                "second_payment_due_date": date(2026, 9, 20),
                "second_payment_required": 0,
                "second_payment_received": 0,
                "client_line_user_id": None,
            },
        ]
    )
    repository = MySqlOrderPreStartNotificationSourceRepository(connection)

    candidates = repository.find_second_payment_due_candidates(date(2026, 9, 20))

    assert len(candidates) == 2
    assert candidates[0].payment_state == "missing"
    assert candidates[0].second_payment_amount == 0
    assert candidates[0].already_settled is False
    assert candidates[0].service_start_date == "2026-09-01"
    assert candidates[1].payment_state == "not_required"
    assert candidates[1].second_payment_amount == 0
    assert candidates[1].already_settled is True
    assert candidates[1].service_start_date == "2026-09-02"


def test_notification_facts_do_not_alias_payment_deadlines_to_service_date():
    occurred_at = datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc)

    first = from_order_pre_start_checkpoint(
        case_no="CASE-310-FIRST",
        planned_start_date="2026-09-20",
        first_payment_due_date="2026-09-18",
        first_payment_amount=6000,
        payment_state="partial",
        already_settled=False,
        occurred_at=occurred_at,
    )
    assert first.facts["service_date"] == "2026-09-20"
    assert first.facts["first_payment_due_date"] == "2026-09-18"
    assert first.facts["first_payment_status"] == "部分已收，尚有餘額"

    second = from_order_second_payment_checkpoint(
        case_no="CASE-310-SECOND",
        service_start_date="2026-09-20",
        second_payment_due_date="2026-10-01",
        second_payment_amount=0,
        payment_state="missing",
        already_settled=False,
        occurred_at=occurred_at,
    )
    assert second.facts["service_date"] == "2026-09-20"
    assert second.facts["second_payment_due_date"] == "2026-10-01"
    assert second.facts["second_payment_amount"] == "帳務資料尚未確認"
    assert second.facts["second_payment_status"] == "帳務資料尚未確認"


def test_projector_uses_taipei_business_date_for_three_day_window():
    class Scanner:
        def __init__(self):
            self.targets = []

        def find_due_candidates(self, target_date):
            self.targets.append(target_date)
            return ()

        def find_second_payment_due_candidates(self, target_date):
            self.targets.append(target_date)
            return ()

    class Registry:
        def register_and_project(self, event):
            raise AssertionError("no events expected")

    scanner = Scanner()
    projector = OrderPreStartNotificationSourceProjector(scanner, Registry())

    processed = projector.run_once(datetime(2026, 9, 15, 16, 30, tzinfo=timezone.utc))

    assert processed == 0
    assert scanner.targets == [date(2026, 9, 19), date(2026, 9, 19)]
