"""
File: test_order_pre_start_notification_source.py
Description: 驗證服務開始前 3 天投影器正確掃描案件並派發 LINE notification source event。
"""

from datetime import date, datetime, timezone

from subsystems.line.order_pre_start_notification_source import (
    OrderPreStartCandidate,
    OrderPreStartNotificationSourceProjector,
)


def test_projector_runs_scan_and_projects_due_candidates() -> None:
    candidates = (
        OrderPreStartCandidate(
            case_no="CASE-101",
            planned_start_date="2026-08-20",
            first_payment_amount=30000,
            already_settled=False,
            client_line_user_id="U_CLIENT_101",
        ),
        OrderPreStartCandidate(
            case_no="CASE-102",
            planned_start_date="2026-08-20",
            first_payment_amount=0,
            already_settled=True,
            client_line_user_id="U_CLIENT_102",
        ),
    )

    scanned_dates: list[date] = []
    projected_events: list[object] = []

    class MockScanner:
        def find_due_candidates(self, target_date: date) -> tuple[OrderPreStartCandidate, ...]:
            scanned_dates.append(target_date)
            return candidates

    class MockRegistry:
        def register_and_project(self, event) -> int:
            projected_events.append(event)
            return len(projected_events)

    projector = OrderPreStartNotificationSourceProjector(MockScanner(), MockRegistry())
    now = datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)
    count = projector.run_once(now)

    assert count == 2
    assert scanned_dates == [date(2026, 8, 20)]
    assert len(projected_events) == 2

    event1 = projected_events[0]
    assert event1.event_code == "order.pre_start_reminder"
    assert event1.facts["case_no"] == "CASE-101"
    assert event1.facts["already_settled"] is False
    assert event1.facts["line_user_id"] == "U_CLIENT_101"

    event2 = projected_events[1]
    assert event2.event_code == "order.pre_start_reminder"
    assert event2.facts["case_no"] == "CASE-102"
    assert event2.facts["already_settled"] is True


def test_projector_runs_scan_and_projects_second_payment_candidates() -> None:
    from subsystems.line.order_pre_start_notification_source import OrderSecondPaymentCandidate

    second_candidates = (
        OrderSecondPaymentCandidate(
            case_no="CASE-201",
            second_payment_due_date="2026-09-10",
            second_payment_amount=35000,
            already_settled=False,
            client_line_user_id="U_CLIENT_201",
        ),
    )

    projected_events: list[object] = []

    class MockScanner:
        def find_due_candidates(self, _target_date: date) -> tuple[OrderPreStartCandidate, ...]:
            return ()

        def find_second_payment_due_candidates(self, _target_date: date) -> tuple[OrderSecondPaymentCandidate, ...]:
            return second_candidates

    class MockRegistry:
        def register_and_project(self, event) -> int:
            projected_events.append(event)
            return len(projected_events)

    projector = OrderPreStartNotificationSourceProjector(MockScanner(), MockRegistry())
    now = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    count = projector.run_once(now)

    assert count == 1
    assert len(projected_events) == 1
    event = projected_events[0]
    assert event.event_code == "order.second_payment_reminder"
    assert event.facts["case_no"] == "CASE-201"
    assert event.facts["second_payment_due_date"] == "2026-09-10"
    assert event.facts["second_payment_amount"] == "NT$ 35,000"
    assert event.facts["already_settled"] is False
    assert event.facts["line_user_id"] == "U_CLIENT_201"
