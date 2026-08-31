"""
File: process_reminder_anomaly_source.py
Description: 載入流程提醒根事實並投影 HCM／BeClass 等 current-state anomalies。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from domains.anomalies.registry import default_anomaly_registry
from infrastructure.mysql.anomaly_registry_repository import MySqlAnomalyRepository
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId
from subsystems.anomalies.alert_workflow import AnomalyApplication
from subsystems.anomalies.process_reminder_anomaly_source import (
    build_beclass_missing_requests,
    build_client_missing_line_requests,
    build_client_payable_requests,
    build_client_receivable_requests,
    build_line_identity_conflict_requests,
    build_line_task_no_reply_requests,
    build_order_matching_requests,
    build_resume_not_sent_requests,
    build_schedule_holiday_undecided_requests,
    build_schedule_overlap_requests,
    build_schedule_replaced_assignment_requests,
    build_staff_missing_line_requests,
    build_subsidy_return_requests,
    build_subsidy_advance_due_requests,
)


@dataclass(frozen=True, slots=True)
class ProcessReminderConsumeResult:
    projected_count: int
    active_count: int
    error: TypedError | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None


def consume_process_reminder_anomaly_sources(
    connection: Any,
    *,
    as_of: date,
    unit_of_work_factory: Callable[[], object],
) -> ProcessReminderConsumeResult:
    """Scan and project reminders using the caller's outer transaction.

    The MySQL source owns only root-fact reads.  The subsystem supplies the
    UoW used by the anomaly application and owns transaction finalization.
    """
    try:
        requests = _scan_all(connection, as_of)
        application = AnomalyApplication(
            default_anomaly_registry(),
            MySqlAnomalyRepository(connection),
            unit_of_work_factory,
        )
        for request in requests:
            application.project(request)
        return ProcessReminderConsumeResult(
            len(requests), sum(request.desired.active for request in requests)
        )
    except Exception as error:
        category = ErrorCategory.VALIDATION if isinstance(error, (TypeError, ValueError)) else ErrorCategory.INTERNAL
        code = "process_reminder_anomaly_source_invalid" if category is ErrorCategory.VALIDATION else "transaction_failed"
        message = "流程提醒異常來源資料不符合契約。" if category is ErrorCategory.VALIDATION else "流程提醒異常投影失敗。"
        return ProcessReminderConsumeResult(
            0, 0, TypedError(category, code, message, CorrelationId(f"process-reminder-anomaly-scan:{as_of.isoformat()}"))
        )


def _scan_all(connection, as_of: date) -> tuple:
    with connection.cursor() as cursor:
        order_rows = _fetch(cursor, _ORDER_SQL)
        beclass_rows = _fetch(cursor, _BECLASS_SQL)
        resume_rows = _fetch(cursor, _RESUME_SQL)
        client_candidate_rows = _fetch(cursor, _CLIENT_OBLIGATION_CANDIDATE_CASES_SQL)
        client_case_nos = _candidate_case_nos(client_candidate_rows)
        client_account_rows = _fetch_scoped_for_update(
            cursor, _CLIENT_FINANCE_ACCOUNT_LOCK_SQL, client_case_nos
        )
        client_obligation_rows = _fetch_scoped_for_update(
            cursor, _CLIENT_OBLIGATION_REMINDER_SQL, client_case_nos
        )
        client_obligation_rows = _prepare_locked_client_obligation_rows(
            client_candidate_rows, client_account_rows, client_obligation_rows
        )
        subsidy_advance_rows = _fetch(cursor, _SUBSIDY_ADVANCE_REMINDER_SQL)
        holiday_undecided_rows = _fetch(cursor, _SCHEDULE_HOLIDAY_UNDECIDED_SQL)
        replaced_rows = _fetch(cursor, _SCHEDULE_REPLACED_SQL)
        overlap_rows = _fetch(cursor, _SCHEDULE_OVERLAP_SQL)
        client_line_rows = _fetch(cursor, _CLIENT_LINE_SQL)
        staff_line_rows = _fetch(cursor, _STAFF_LINE_SQL)
        line_task_rows = _fetch(cursor, _LINE_TASK_SQL)
        line_conflict_rows = _line_identity_conflict_rows(cursor)

    return (
        build_order_matching_requests(order_rows, as_of=as_of)
        + build_beclass_missing_requests(beclass_rows, as_of=as_of)
        + build_resume_not_sent_requests(resume_rows, as_of=as_of)
        + build_client_receivable_requests(client_obligation_rows, as_of=as_of)
        + build_client_payable_requests(client_obligation_rows, as_of=as_of)
        + build_subsidy_return_requests(client_obligation_rows, as_of=as_of)
        + build_subsidy_advance_due_requests(subsidy_advance_rows, as_of=as_of)
        + build_schedule_holiday_undecided_requests(holiday_undecided_rows, as_of=as_of)
        + build_schedule_replaced_assignment_requests(replaced_rows, as_of=as_of)
        + build_schedule_overlap_requests(overlap_rows, as_of=as_of)
        + build_client_missing_line_requests(client_line_rows, as_of=as_of)
        + build_staff_missing_line_requests(staff_line_rows, as_of=as_of)
        + build_line_task_no_reply_requests(line_task_rows, as_of=as_of)
        + build_line_identity_conflict_requests(line_conflict_rows, as_of=as_of)
    )


def _line_identity_conflict_rows(cursor) -> list[dict[str, Any]]:
    cursor.execute(_LINE_CONFLICT_CURRENT_SQL)
    current = {
        row["line_user_id"]: {**row, "is_conflicting": True} for row in _mapping_rows(cursor.fetchall())
    }
    cursor.execute(_LINE_CONFLICT_ACTIVE_ALERTS_SQL)
    for row in _mapping_rows(cursor.fetchall()):
        line_user_id = row["source_identity"]
        if line_user_id not in current:
            current[line_user_id] = {
                "line_user_id": line_user_id,
                "client_case_no": None,
                "client_name": None,
                "staff_id": None,
                "staff_name": None,
                "is_conflicting": False,
            }
    return list(current.values())


def _fetch(cursor, sql: str, params=()):
    if params:
        cursor.execute(sql, params)
    else:
        cursor.execute(sql)
    return _mapping_rows(cursor.fetchall())


def _fetch_scoped_for_update(cursor, sql_template: str, case_nos: tuple[str, ...]):
    if not case_nos:
        return []
    placeholders = ", ".join(["%s"] * len(case_nos))
    return _fetch(cursor, sql_template.format(placeholders=placeholders), case_nos)


def _candidate_case_nos(rows: list[dict[str, Any]]) -> tuple[str, ...]:
    case_nos = []
    for row in rows:
        case_no = row.get("case_no")
        if not isinstance(case_no, str) or not case_no:
            raise ValueError("client_finance_case_identity_missing")
        if case_no not in case_nos:
            case_nos.append(case_no)
    return tuple(case_nos)


def _prepare_locked_client_obligation_rows(
    candidate_rows: list[dict[str, Any]],
    account_rows: list[dict[str, Any]],
    obligation_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    case_nos = _candidate_case_nos(candidate_rows)
    accounts: dict[str, dict[str, Any]] = {}
    for account in account_rows:
        case_no = account.get("case_no")
        if not isinstance(case_no, str) or not case_no:
            raise ValueError("client_finance_account_identity_missing")
        if case_no in accounts:
            raise ValueError("client_finance_account_ambiguous")
        if account.get("aggregate_version") is None:
            raise ValueError("client_finance_account_version_missing")
        accounts[case_no] = account

    obligations_by_case: dict[str, list[dict[str, Any]]] = {}
    for obligation in obligation_rows:
        case_no = obligation.get("case_no")
        if not isinstance(case_no, str) or not case_no:
            raise ValueError("client_finance_obligation_identity_missing")
        obligations_by_case.setdefault(case_no, []).append(obligation)

    locked_rows: list[dict[str, Any]] = []
    for case_no in case_nos:
        account = accounts.get(case_no)
        obligations = obligations_by_case.get(case_no, [])
        if account is None:
            raise ValueError("client_finance_account_missing")
        if not obligations:
            raise ValueError("client_finance_obligation_root_missing")
        for obligation in obligations:
            locked_rows.append(
                {
                    **obligation,
                    "account_version": account["aggregate_version"],
                }
            )
    return locked_rows


def _mapping_rows(rows):
    result = list(rows)
    if any(not isinstance(row, dict) for row in result):
        raise ValueError("process reminder scan rows must be mapping rows")
    return result


_ORDER_SQL = (
    "SELECT o.case_no, o.status, o.staff_id, m.id AS match_id, "
    "m.caregiver_accepted, m.sent_info_1_at, m.sent_info_2_at "
    "FROM orders o LEFT JOIN matching_records m ON m.case_no = o.case_no"
)
_BECLASS_SQL = (
    "SELECT o.case_no, b.id AS beclass_id "
    "FROM orders o LEFT JOIN beclass_records b ON b.query_no = o.case_no"
)
_RESUME_SQL = (
    "SELECT o.case_no, o.staff_id, "
    "MAX(CASE WHEN m.caregiver_accepted = 1 AND m.sent_resume_at IS NULL THEN 1 ELSE 0 END) AS pending_resume "
    "FROM orders o LEFT JOIN matching_records m ON m.case_no = o.case_no "
    "GROUP BY o.case_no, o.staff_id"
)
_CLIENT_OBLIGATION_CANDIDATE_CASES_SQL = (
    "SELECT case_no FROM client_obligations "
    "WHERE (direction='receivable_from_client' AND obligation_type IN ('deposit','first','second','adjustment')) "
    "OR (direction='payable_to_client' AND obligation_type IN ('refund','adjustment','subsidy_return')) "
    "UNION "
    "SELECT source_identity AS case_no FROM anomaly_current_alerts "
    "WHERE definition_code IN ('RECEIVABLE-001','CLIENTPAYABLE-001','RETURN-001')"
)
_CLIENT_FINANCE_ACCOUNT_LOCK_SQL = (
    "SELECT case_no, aggregate_version FROM client_finance_accounts "
    "WHERE case_no IN ({placeholders}) FOR UPDATE"
)
_CLIENT_OBLIGATION_REMINDER_SQL = (
    "SELECT obligation.case_no, obligation.obligation_identity, obligation.obligation_type, obligation.direction, "
    "obligation.amount_due_ntd, obligation.due_date, obligation.status "
    "FROM client_obligations obligation "
    "WHERE obligation.case_no IN ({placeholders}) "
    "AND ((obligation.direction='receivable_from_client' "
    "AND obligation.obligation_type IN ('deposit','first','second','adjustment')) "
    "OR (obligation.direction='payable_to_client' "
    "AND obligation.obligation_type IN ('refund','adjustment','subsidy_return'))) "
    "ORDER BY obligation.case_no, obligation.due_date, obligation.obligation_identity FOR UPDATE"
)
_SUBSIDY_ADVANCE_REMINDER_SQL = (
    "SELECT candidates.case_no, orders.actual_end_date, link.entitled_amount_ntd, "
    "COALESCE(allocation.allocated_amount_ntd,0) allocated_amount_ntd "
    "FROM ("
    "SELECT obligation.case_no FROM client_obligations obligation "
    "JOIN client_subsidy_return_claim_item_links link ON link.obligation_identity=obligation.obligation_identity "
    "WHERE obligation.obligation_type='subsidy_return' "
    "UNION SELECT source_identity AS case_no FROM anomaly_current_alerts "
    "WHERE definition_code='SUBSIDYADVANCE-001'"
    ") candidates "
    "LEFT JOIN orders ON orders.case_no=candidates.case_no "
    "LEFT JOIN client_obligations obligation ON obligation.case_no=candidates.case_no "
    "AND obligation.obligation_type='subsidy_return' "
    "LEFT JOIN client_subsidy_return_claim_item_links link ON link.obligation_identity=obligation.obligation_identity "
    "LEFT JOIN (SELECT claim_item_id,SUM(CASE WHEN allocation_type='receipt' THEN allocated_amount "
    "WHEN allocation_type='reversal' THEN -allocated_amount ELSE 0 END) allocated_amount_ntd "
    "FROM government_subsidy_allocations GROUP BY claim_item_id) allocation "
    "ON allocation.claim_item_id=link.claim_item_id "
    "ORDER BY candidates.case_no, link.claim_item_id"
)
_SCHEDULE_HOLIDAY_UNDECIDED_SQL = (
    "SELECT csa.staff_id, csa.case_no, csa.status, h.holiday_date, h.holiday_name, "
    "ss.id AS schedule_id, s.name AS staff_name "
    "FROM case_staff_assignments csa "
    "JOIN holidays h ON h.holiday_date BETWEEN csa.assigned_start_date AND csa.assigned_end_date "
    "LEFT JOIN staff_schedule ss ON ss.staff_id = csa.staff_id AND ss.work_date = h.holiday_date "
    "JOIN staff s ON s.id = csa.staff_id "
    "WHERE csa.assigned_start_date IS NOT NULL AND csa.assigned_end_date IS NOT NULL"
)
_SCHEDULE_REPLACED_SQL = (
    "SELECT id, case_no, staff_id, assigned_start_date, assigned_end_date, "
    "floor_fee_allocated, replacement_reason "
    "FROM case_staff_assignments WHERE status = 'replaced'"
)
_SCHEDULE_OVERLAP_SQL = (
    "SELECT a.id AS a_id, a.case_no AS a_case_no, a.assigned_start_date AS a_start, "
    "a.assigned_end_date AS a_end, a.status AS a_status, "
    "b.id AS b_id, b.case_no AS b_case_no, b.assigned_start_date AS b_start, "
    "b.assigned_end_date AS b_end, b.status AS b_status, a.staff_id, s.name AS staff_name "
    "FROM case_staff_assignments a "
    "JOIN case_staff_assignments b ON a.staff_id = b.staff_id AND a.id < b.id "
    "JOIN staff s ON s.id = a.staff_id "
    "WHERE a.assigned_start_date IS NOT NULL AND a.assigned_end_date IS NOT NULL "
    "AND b.assigned_start_date IS NOT NULL AND b.assigned_end_date IS NOT NULL"
)
_CLIENT_LINE_SQL = (
    "SELECT o.case_no, c.id AS client_id, c.line_user_id, "
    "b.line_user_id AS binding_line_user_id, b.binding_status, "
    "b.subject_type AS binding_subject_type, "
    "b.subject_reference AS binding_subject_reference, "
    "b.aggregate_version AS binding_version "
    "FROM orders o LEFT JOIN clients c "
    "ON c.id = o.client_id AND c.case_no = o.case_no "
    "LEFT JOIN line_identity_bindings b ON b.line_user_id = c.line_user_id"
)
_STAFF_LINE_SQL = (
    "SELECT o.case_no, o.staff_id, s.line_user_id AS staff_line_user_id, "
    "b.line_user_id AS binding_line_user_id, b.binding_status, "
    "b.subject_type AS binding_subject_type, "
    "b.subject_reference AS binding_subject_reference, "
    "b.aggregate_version AS binding_version "
    "FROM orders o LEFT JOIN staff s ON s.id = o.staff_id "
    "LEFT JOIN line_identity_bindings b ON b.line_user_id = s.line_user_id"
)
_LINE_TASK_SQL = (
    "SELECT lt.id, lt.to_user_id, lt.sent_at, lt.message_content, "
    "EXISTS(SELECT 1 FROM line_webhook_events lwe "
    "WHERE lwe.source_user_id = lt.to_user_id AND lwe.received_at > lt.sent_at) AS has_reply "
    "FROM line_tasks lt "
    "WHERE lt.task_type = 'line_push' AND lt.status = 'sent' AND lt.sent_at IS NOT NULL"
)
_LINE_CONFLICT_CURRENT_SQL = (
    "SELECT c.line_user_id, c.case_no AS client_case_no, c.name AS client_name, "
    "s.id AS staff_id, s.name AS staff_name "
    "FROM clients c JOIN staff s ON s.line_user_id = c.line_user_id "
    "WHERE c.line_user_id IS NOT NULL AND c.line_user_id != ''"
)
_LINE_CONFLICT_ACTIVE_ALERTS_SQL = (
    "SELECT source_identity FROM anomaly_current_alerts "
    "WHERE definition_code = 'LINE-004' AND predicate_active = 1"
)


__all__ = [
    "ProcessReminderConsumeResult",
    "consume_process_reminder_anomaly_sources",
]
