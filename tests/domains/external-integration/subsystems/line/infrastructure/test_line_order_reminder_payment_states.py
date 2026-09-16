from datetime import date, datetime, timezone

import pytest

from infrastructure.mysql.order_pre_start_notification_source_repository import (
    MySqlOrderPreStartNotificationSourceRepository,
)
from subsystems.line.notification_source_adapters import (
    from_order_pre_start_checkpoint,
    from_order_second_payment_checkpoint,
)


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params):
        self.executed = (sql, params)

    def fetchall(self):
        return self._rows


class _Connection:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _Cursor(self._rows)


_CASES = (
    (None, 0, 0, False, "missing", "帳務資料尚未確認", "帳務資料尚未確認"),
    (0, 0, 0, True, "not_required", "NT$ 0（本期無需繳納）", "本期無需繳納"),
    (10000, 0, 10000, False, "outstanding", "NT$ 10,000", "待繳納"),
    (10000, 4000, 6000, False, "partial", "NT$ 6,000", "部分已收，尚有餘額"),
    (10000, 10000, 0, True, "settled", "NT$ 0（已結清）", "已核銷完成"),
)


@pytest.mark.parametrize(
    "required,received,amount,settled,state,display_amount,display_status",
    _CASES,
)
def test_first_payment_projection_and_visible_facts_distinguish_accounting_states(
    required,
    received,
    amount,
    settled,
    state,
    display_amount,
    display_status,
):
    repository = MySqlOrderPreStartNotificationSourceRepository(
        _Connection(
            [
                {
                    "case_no": "CASE-310-FIRST",
                    "service_start_date": date(2026, 9, 20),
                    "first_payment_due_date": date(2026, 9, 18),
                    "first_payment_required": required,
                    "first_payment_received": received,
                    "client_line_user_id": "U310",
                }
            ]
        )
    )

    candidate = repository.find_due_candidates(date(2026, 9, 20))[0]
    assert candidate.first_payment_amount == amount
    assert candidate.already_settled is settled
    assert candidate.payment_state == state

    event = from_order_pre_start_checkpoint(
        case_no=candidate.case_no,
        planned_start_date=candidate.planned_start_date,
        first_payment_due_date=candidate.first_payment_due_date,
        first_payment_amount=candidate.first_payment_amount,
        payment_state=candidate.payment_state,
        already_settled=candidate.already_settled,
        client_line_user_id=candidate.client_line_user_id,
        occurred_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
    )
    assert event.facts["first_payment_amount"] == display_amount
    assert event.facts["first_payment_status"] == display_status
    assert event.facts["payment_state"] == state


@pytest.mark.parametrize(
    "required,received,amount,settled,state,display_amount,display_status",
    _CASES,
)
def test_second_payment_projection_and_visible_facts_distinguish_accounting_states(
    required,
    received,
    amount,
    settled,
    state,
    display_amount,
    display_status,
):
    repository = MySqlOrderPreStartNotificationSourceRepository(
        _Connection(
            [
                {
                    "case_no": "CASE-310-SECOND",
                    "service_start_date": date(2026, 9, 20),
                    "second_payment_due_date": date(2026, 10, 1),
                    "second_payment_required": required,
                    "second_payment_received": received,
                    "client_line_user_id": "U310",
                }
            ]
        )
    )

    candidate = repository.find_second_payment_due_candidates(date(2026, 10, 1))[0]
    assert candidate.second_payment_amount == amount
    assert candidate.already_settled is settled
    assert candidate.payment_state == state

    event = from_order_second_payment_checkpoint(
        case_no=candidate.case_no,
        service_start_date=candidate.service_start_date,
        second_payment_due_date=candidate.second_payment_due_date,
        second_payment_amount=candidate.second_payment_amount,
        payment_state=candidate.payment_state,
        already_settled=candidate.already_settled,
        client_line_user_id=candidate.client_line_user_id,
        occurred_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
    )
    assert event.facts["second_payment_amount"] == display_amount
    assert event.facts["second_payment_status"] == display_status
    assert event.facts["payment_state"] == state
