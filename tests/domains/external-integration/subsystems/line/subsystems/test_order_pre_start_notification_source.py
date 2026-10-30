"""
File: test_order_pre_start_notification_source.py
Description: 驗證正式開工當天群組投影器正確掃描案件並派發 LINE notification source event。
"""

from datetime import date, datetime, timezone
from subsystems.line.service_start_day import ServiceStartDayCandidate, StartDayCaregiver

from subsystems.line.order_pre_start_notification_source import (
    OrderPreStartNotificationSourceProjector,
)


def test_projector_runs_scan_and_projects_due_candidates() -> None:
    candidates = (
        ServiceStartDayCandidate('CASE-101',date(2026,8,20),'C_GROUP',7,30000,(StartDayCaregiver(1,'測試月嫂'),)),
        ServiceStartDayCandidate('CASE-102',date(2026,8,20),'C_GROUP2',8,0,(StartDayCaregiver(2,'測試月嫂二'),)),
    )

    scanned_dates: list[date] = []
    projected_events: list[object] = []

    class MockScanner:
        def find_due_candidates(self, target_date: date) -> tuple[ServiceStartDayCandidate, ...]:
            scanned_dates.append(target_date)
            return candidates

    class MockRegistry:
        def register_and_project(self, event) -> int:
            projected_events.append(event)
            return len(projected_events)

    projector = OrderPreStartNotificationSourceProjector(MockScanner(), MockRegistry())
    now = datetime(2026, 8, 19, 17, 0, tzinfo=timezone.utc)
    count = projector.run_once(now)

    assert count == 2
    assert scanned_dates == [date(2026, 8, 20)]
    assert len(projected_events) == 2

    event1 = projected_events[0]
    assert event1.event_code == "order.service_start_day"
    assert event1.facts["case_no"] == "CASE-101"
    assert event1.facts["first_payment_amount_ntd"] == 30000
    assert event1.facts["group_id"] == "C_GROUP"

    event2 = projected_events[1]
    assert event2.event_code == "order.service_start_day"
    assert event2.facts["case_no"] == "CASE-102"
    assert event2.facts["first_payment_notice"] == ""


def test_projector_does_not_automatically_project_payment_or_receipt_notices():
    from subsystems.line.second_payment_notifications import SecondPaymentNotification
    today=date(2026,9,10)
    due=SecondPaymentNotification('CASE-201','second:201',3,5,today,35000,35000,'C_ORIGINAL')
    paid=SecondPaymentNotification('CASE-202','second:202',4,6,today,35000,0,'C_ORIGINAL',True,'a'*64,35000)
    scanned=[];events=[]
    class Scanner:
        def find_due_candidates(self,_):return ()
        def find_second_payment_due_candidates(self,day):scanned.append(day);return (due,)
        def find_second_payment_settlement_candidates(self):return (paid,)
    class Registry:
        def register_and_project(self,event):events.append(event);return len(events)
    assert OrderPreStartNotificationSourceProjector(Scanner(),Registry()).run_once(datetime(2026,9,9,17,tzinfo=timezone.utc))==0
    assert scanned==[]  # Reminders now belong to the private payment schedule worker.
    assert events==[]
    assert all(e.facts['group_id']=='C_ORIGINAL' and 'line_user_id' not in e.facts for e in events)
