"""
File: order_pre_start_notification_source_repository.py
Description: 依服務開始日掃描即將開始服務之有效案件，並查詢其第一期款應繳與實收事實。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from subsystems.line.order_pre_start_notification_source import (
    OrderPreStartCandidate,
    OrderPreStartScannerPort,
    OrderSecondPaymentCandidate,
)

_SCAN_DUE_ORDERS_SQL = (
    "SELECT "
    "  o.case_no, "
    "  o.service_start_date, "
    "  p.first_payment_due_date, "
    "  ( "
    "    SELECT e.after_amount_ntd FROM client_obligations ob "
    "    JOIN client_obligation_events e ON e.id=ob.current_event_id "
    "    WHERE ob.case_no=o.case_no AND ob.obligation_type='first' LIMIT 1 "
    "  ) AS first_payment_required, "
    "  COALESCE(( "
    "    SELECT SUM(CASE l.entry_type "
    "                 WHEN 'receipt' THEN x.amount_ntd "
    "                 WHEN 'adjustment' THEN x.amount_ntd "
    "                 WHEN 'refund' THEN -x.amount_ntd "
    "                 WHEN 'reversal' THEN -x.amount_ntd END) "
    "    FROM client_obligations ob "
    "    JOIN client_ledger_obligation_allocations x ON x.obligation_identity=ob.obligation_identity "
    "    JOIN client_ledger_entries l ON l.id=x.ledger_entry_id "
    "    WHERE ob.case_no=o.case_no AND ob.obligation_type='first' "
    "  ), 0) AS first_payment_received, "
    "  COALESCE(( "
    "    SELECT line_user_id FROM line_order_group_participants "
    "    WHERE case_no=o.case_no AND participant_type='customer' "
    "      AND invitation_status='joined' AND line_user_id IS NOT NULL AND line_user_id != '' "
    "    ORDER BY id DESC LIMIT 1 "
    "  ), ( "
    "    SELECT line_user_id FROM clients WHERE case_no=o.case_no AND line_user_id IS NOT NULL AND line_user_id != '' LIMIT 1 "
    "  )) AS client_line_user_id "
    "FROM orders o "
    "LEFT JOIN client_payment_terms p ON p.case_no=o.case_no "
    "WHERE o.status NOT IN ('訂單取消', '已取消', '終止', '已結案', '取消') "
    "  AND o.service_start_date = %s "
    "ORDER BY o.case_no ASC"
)


class MySqlOrderPreStartNotificationSourceRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def find_due_candidates(self, target_date: date) -> tuple[OrderPreStartCandidate, ...]:
        date_str = target_date.isoformat()
        with self._connection.cursor() as cursor:
            cursor.execute(_SCAN_DUE_ORDERS_SQL, (date_str,))
            rows = cursor.fetchall() or ()

        candidates: list[OrderPreStartCandidate] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            case_no = str(row.get("case_no") or "")
            if not case_no:
                continue
            start_date_val = row.get("service_start_date")
            start_date_str = str(start_date_val) if start_date_val is not None else date_str
            due_date_val = row.get("first_payment_due_date")
            due_date_str = str(due_date_val) if due_date_val is not None else None
            amount, already_settled, payment_state = _project_payment(
                row.get("first_payment_required"),
                row.get("first_payment_received"),
            )

            client_line_user_id = row.get("client_line_user_id")
            if isinstance(client_line_user_id, str):
                client_line_user_id = client_line_user_id.strip() or None
            else:
                client_line_user_id = None

            candidates.append(
                OrderPreStartCandidate(
                    case_no=case_no,
                    planned_start_date=start_date_str,
                    first_payment_amount=amount,
                    already_settled=already_settled,
                    client_line_user_id=client_line_user_id,
                    first_payment_due_date=due_date_str,
                    payment_state=payment_state,
                )
            )
        return tuple(candidates)

    def find_second_payment_due_candidates(self, target_date: date) -> tuple[OrderSecondPaymentCandidate, ...]:
        date_str = target_date.isoformat()
        with self._connection.cursor() as cursor:
            cursor.execute(_SCAN_DUE_SECOND_PAYMENTS_SQL, (date_str,))
            rows = cursor.fetchall() or ()

        candidates: list[OrderSecondPaymentCandidate] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            case_no = str(row.get("case_no") or "")
            if not case_no:
                continue
            amount, already_settled, payment_state = _project_payment(
                row.get("second_payment_required"),
                row.get("second_payment_received"),
            )

            client_line_user_id = row.get("client_line_user_id")
            if isinstance(client_line_user_id, str):
                client_line_user_id = client_line_user_id.strip() or None
            else:
                client_line_user_id = None

            due_date_val = row.get("second_payment_due_date")
            due_date_str = str(due_date_val) if due_date_val is not None else date_str
            service_date_val = row.get("service_start_date")
            service_date_str = str(service_date_val) if service_date_val is not None else None

            candidates.append(
                OrderSecondPaymentCandidate(
                    case_no=case_no,
                    second_payment_due_date=due_date_str,
                    second_payment_amount=amount,
                    already_settled=already_settled,
                    client_line_user_id=client_line_user_id,
                    service_start_date=service_date_str,
                    payment_state=payment_state,
                )
            )
        return tuple(candidates)


def _project_payment(required_value: object, received_value: object) -> tuple[int, bool, str]:
    if required_value is None:
        return 0, False, "missing"

    required = int(required_value)
    received = int(received_value or 0)
    if required <= 0:
        return 0, True, "not_required"
    if received >= required:
        return 0, True, "settled"

    outstanding = max(0, required - received)
    if received > 0:
        return outstanding, False, "partial"
    return outstanding, False, "outstanding"


_SCAN_DUE_SECOND_PAYMENTS_SQL = (
    "SELECT "
    "  o.case_no, "
    "  o.service_start_date, "
    "  p.second_payment_due_date, "
    "  ( "
    "    SELECT e.after_amount_ntd FROM client_obligations ob "
    "    JOIN client_obligation_events e ON e.id=ob.current_event_id "
    "    WHERE ob.case_no=o.case_no AND ob.obligation_type='second' LIMIT 1 "
    "  ) AS second_payment_required, "
    "  COALESCE(( "
    "    SELECT SUM(CASE l.entry_type "
    "                 WHEN 'receipt' THEN x.amount_ntd "
    "                 WHEN 'adjustment' THEN x.amount_ntd "
    "                 WHEN 'refund' THEN -x.amount_ntd "
    "                 WHEN 'reversal' THEN -x.amount_ntd END) "
    "    FROM client_obligations ob "
    "    JOIN client_ledger_obligation_allocations x ON x.obligation_identity=ob.obligation_identity "
    "    JOIN client_ledger_entries l ON l.id=x.ledger_entry_id "
    "    WHERE ob.case_no=o.case_no AND ob.obligation_type='second' "
    "  ), 0) AS second_payment_received, "
    "  COALESCE(( "
    "    SELECT line_user_id FROM line_order_group_participants "
    "    WHERE case_no=o.case_no AND participant_type='customer' "
    "      AND invitation_status='joined' AND line_user_id IS NOT NULL AND line_user_id != '' "
    "    ORDER BY id DESC LIMIT 1 "
    "  ), ( "
    "    SELECT line_user_id FROM clients WHERE case_no=o.case_no AND line_user_id IS NOT NULL AND line_user_id != '' LIMIT 1 "
    "  )) AS client_line_user_id "
    "FROM orders o "
    "JOIN client_payment_terms p ON p.case_no=o.case_no "
    "WHERE o.status NOT IN ('訂單取消', '已取消', '終止', '已結案', '取消') "
    "  AND p.second_payment_due_date IS NOT NULL "
    "  AND p.second_payment_due_date = %s "
    "ORDER BY o.case_no ASC"
)


__all__ = ["MySqlOrderPreStartNotificationSourceRepository"]
