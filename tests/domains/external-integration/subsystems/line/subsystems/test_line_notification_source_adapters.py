"""
File: test_line_notification_source_adapters.py
Description: 驗證 owner outbox 只會被轉為可稽核 LINE source event，不能由 raw bank row 偽造。
"""

from datetime import datetime, timezone

import pytest

from subsystems.line.notification_source_adapters import (
    from_client_finance_deposit_outbox,
    from_orders_lifecycle_outbox,
)


def test_adapts_committed_orders_lifecycle_outbox_without_current_state_read() -> None:
    event = from_orders_lifecycle_outbox(
        outbox_id=9,
        case_no="C-001",
        lifecycle_event_id=4,
        payload={
            "resulting_order_version": 7,
            "before_status": "訂單成立",
            "after_status": "服務中",
            "actual_end_date": "2026-08-16",
            "service_completion_reached": False,
        },
        occurred_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
    )

    assert event.identity == "orders-domain-outbox:9"
    assert event.event_code == "order_lifecycle_transition"
    assert event.facts["case_no"] == "C-001"


def test_rejects_unsettled_or_raw_client_finance_payload() -> None:
    with pytest.raises(ValueError, match="settlement identity"):
        from_client_finance_deposit_outbox(
            outbox_id=1,
            case_no="C-001",
            payload={"settlement_identity": "not-a-settlement", "resulting_account_version": 2},
            occurred_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
        )


@pytest.mark.parametrize('amount', [24000, 0])
def test_adapts_formal_start_day_for_group_only(amount):
    from datetime import date
    from subsystems.line.notification_source_adapters import from_order_service_start_day
    from subsystems.line.service_start_day import ServiceStartDayCandidate, StartDayCaregiver
    candidate=ServiceStartDayCandidate('CASE-001',date(2026,8,20),'C_SERVICE',7,amount,(StartDayCaregiver(1,'測試月嫂'),))
    event=from_order_service_start_day(candidate,occurred_at=datetime(2026,8,20,tzinfo=timezone.utc))
    assert event.identity == 'order-service-start-day:'+candidate.token
    assert event.event_code == 'order.service_start_day'
    assert event.facts['group_id'] == 'C_SERVICE'
    assert 'line_user_id' not in event.facts
    assert event.facts['first_payment_notice']==''
    assert event.facts['caregiver_names'] == '測試月嫂'
