"""
File: notification_source_adapters.py
Description: 將 owner 已提交 outbox snapshot 轉為 LINE notification source event，拒絕以現況掃描補造事件。
"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from subsystems.line.notification_policy import NotificationSourceEvent


def from_orders_lifecycle_outbox(
    *,
    outbox_id: int,
    case_no: str,
    lifecycle_event_id: int,
    payload: Mapping[str, object],
    occurred_at: datetime,
) -> NotificationSourceEvent:
    """Adapt one committed Orders outbox row without reading mutable Orders state."""
    _positive(outbox_id, "orders outbox ID")
    _positive(lifecycle_event_id, "Orders lifecycle event ID")
    _text(case_no, "case number")
    resulting_version = _positive(payload.get("resulting_order_version"), "order version")
    before_status = _text(payload.get("before_status"), "before status")
    after_status = _text(payload.get("after_status"), "after status")
    return NotificationSourceEvent(
        identity=f"orders-domain-outbox:{outbox_id}",
        event_code="order_lifecycle_transition",
        historical_silent=False,
        facts={
            "case_no": case_no,
            "lifecycle_event_id": lifecycle_event_id,
            "before_status": before_status,
            "after_status": after_status,
            "actual_end_date": payload.get("actual_end_date"),
            "service_completion_reached": payload.get("service_completion_reached"),
        },
        source_domain="orders",
        source_aggregate_type="order",
        source_aggregate_identity=case_no,
        source_version=resulting_version,
        occurred_at=occurred_at,
    )


def from_client_finance_deposit_outbox(
    *,
    outbox_id: int,
    case_no: str,
    payload: Mapping[str, object],
    occurred_at: datetime,
) -> NotificationSourceEvent:
    """Adapt only an already-settled deposit projection, never a raw bank import row."""
    _positive(outbox_id, "Client Finance outbox ID")
    _text(case_no, "case number")
    settlement_identity = _text(payload.get("settlement_identity"), "settlement identity")
    if len(settlement_identity) != 64:
        raise ValueError("settlement identity is invalid")
    version = _positive(payload.get("resulting_account_version"), "account version")
    return NotificationSourceEvent(
        identity=f"client-finance-outbox:{outbox_id}",
        event_code="deposit_confirmed",
        historical_silent=False,
        facts={
            "case_no": case_no,
            "settlement_identity": settlement_identity,
        },
        source_domain="client_finance",
        source_aggregate_type="client_finance_account",
        source_aggregate_identity=case_no,
        source_version=version,
        occurred_at=occurred_at,
    )


def from_scheduling_service_day_checkpoint_outbox(
    *,
    outbox_id: int,
    event_id: int,
    payload: Mapping[str, object],
    occurred_at: datetime,
) -> NotificationSourceEvent:
    """Adapt an immutable Scheduling service-end checkpoint, never a current-state scan."""
    _positive(outbox_id, "Scheduling checkpoint outbox ID")
    _positive(event_id, "Scheduling checkpoint event ID")
    case_no = _text(payload.get("case_no"), "case number")
    assignment_id = _positive(payload.get("assignment_id"), "assignment ID")
    staff_id = _positive(payload.get("staff_id"), "staff ID")
    service_date = _text(payload.get("service_date"), "service date")
    requires_cooking = payload.get("requires_cooking")
    baby_log_completed = payload.get("baby_log_completed")
    if not isinstance(requires_cooking, bool) or not isinstance(baby_log_completed, bool):
        raise ValueError("Scheduling checkpoint completion facts are invalid")
    return NotificationSourceEvent(
        identity=f"scheduling-service-day-checkpoint-outbox:{outbox_id}",
        event_code="service_time_checkpoint",
        historical_silent=False,
        facts={
            "assignment_id": assignment_id,
            "baby_log_completed": baby_log_completed,
            "case_no": case_no,
            "requires_cooking": requires_cooking,
            "service_date": service_date,
            "staff_id": staff_id,
        },
        source_domain="scheduling",
        source_aggregate_type="case_staff_assignment",
        source_aggregate_identity=str(assignment_id),
        source_version=1,
        occurred_at=occurred_at,
    )


def from_order_pre_start_checkpoint(
    *,
    case_no: str,
    planned_start_date: str,
    first_payment_amount: int,
    already_settled: bool,
    occurred_at: datetime,
    client_line_user_id: str | None = None,
) -> NotificationSourceEvent:
    """Adapt a pre-start order checkpoint (3 days before service start) without ad-hoc push side-effects."""
    _text(case_no, "case number")
    _text(planned_start_date, "planned start date")
    if not isinstance(first_payment_amount, int) or isinstance(first_payment_amount, bool) or first_payment_amount < 0:
        raise ValueError("first payment amount is invalid")
    if not isinstance(already_settled, bool):
        raise ValueError("already settled flag is invalid")

    payment_amount_str = f"NT$ {first_payment_amount:,}" if not already_settled else "NT$ 0（已結清）"
    payment_status_str = "已核銷完成" if already_settled else "待繳納（請於服務開始日繳納）"

    facts: dict[str, object] = {
        "case_no": case_no,
        "planned_start_date": planned_start_date,
        "first_payment_amount": payment_amount_str,
        "first_payment_status": payment_status_str,
        "already_settled": already_settled,
        "service_date": planned_start_date,
    }
    if client_line_user_id:
        facts["line_user_id"] = client_line_user_id
        facts["recipient_projection"] = {
            "selector": "client.bound_case",
            "type": "user",
            "identity": client_line_user_id,
        }

    return NotificationSourceEvent(
        identity=f"order-pre-start-reminder:{case_no}:{planned_start_date}",
        event_code="order.pre_start_reminder",
        historical_silent=False,
        facts=facts,
        source_domain="orders",
        source_aggregate_type="order",
        source_aggregate_identity=case_no,
        source_version=1,
        occurred_at=occurred_at,
    )


def from_order_second_payment_checkpoint(
    *,
    case_no: str,
    second_payment_due_date: str,
    second_payment_amount: int,
    already_settled: bool,
    occurred_at: datetime,
    client_line_user_id: str | None = None,
) -> NotificationSourceEvent:
    """Adapt a second payment reminder checkpoint (3 days before second payment due date)."""
    _text(case_no, "case number")
    _text(second_payment_due_date, "second payment due date")
    if not isinstance(second_payment_amount, int) or isinstance(second_payment_amount, bool) or second_payment_amount < 0:
        raise ValueError("second payment amount is invalid")
    if not isinstance(already_settled, bool):
        raise ValueError("already settled flag is invalid")

    payment_amount_str = f"NT$ {second_payment_amount:,}" if not already_settled else "NT$ 0（已結清）"
    payment_status_str = "已核銷完成" if already_settled else "待繳納（請於繳納期限前完成匯款）"

    facts: dict[str, object] = {
        "case_no": case_no,
        "second_payment_due_date": second_payment_due_date,
        "second_payment_amount": payment_amount_str,
        "second_payment_status": payment_status_str,
        "already_settled": already_settled,
        "service_date": second_payment_due_date,
    }
    if client_line_user_id:
        facts["line_user_id"] = client_line_user_id
        facts["recipient_projection"] = {
            "selector": "client.bound_case",
            "type": "user",
            "identity": client_line_user_id,
        }

    return NotificationSourceEvent(
        identity=f"order-second-payment-reminder:{case_no}:{second_payment_due_date}",
        event_code="order.second_payment_reminder",
        historical_silent=False,
        facts=facts,
        source_domain="orders",
        source_aggregate_type="order",
        source_aggregate_identity=case_no,
        source_version=1,
        occurred_at=occurred_at,
    )


def _positive(value: object, name: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} is invalid")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is invalid")
    return value


__all__ = [
    "from_client_finance_deposit_outbox",
    "from_order_pre_start_checkpoint",
    "from_order_second_payment_checkpoint",
    "from_orders_lifecycle_outbox",
    "from_scheduling_service_day_checkpoint_outbox",
]
