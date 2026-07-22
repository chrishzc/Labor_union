"""Read raw accounting facts for a case without using legacy finance formulas."""

from __future__ import annotations

from typing import Any

from services.db_service import get_connection


def _case_no(value: Any) -> str:
    case_no = str(value or "").strip()
    if not case_no:
        raise ValueError("case_no is required")
    return case_no


def _missing_terms(source: dict[str, Any]) -> list[str]:
    """List terms that do not have an approved normalized raw-data source yet."""
    missing = ["collection_schedule"]
    for assignment in source["staff_assignments"]:
        if assignment.get("status") != "cancelled" and assignment.get("hourly_rate") is None:
            missing.append(f"assignment:{assignment['assignment_id']}:hourly_rate")
    return missing


def load_case_accounting_source(case_no: str) -> dict[str, Any]:
    """Load normalized source facts and explicit gaps for a single ``case_no``.

    The result intentionally preserves BeClass survey data as raw input.  It
    does not infer subsidy hours or rates from identity labels, old views, or
    historic payment records.
    """
    case_no = _case_no(case_no)
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT o.case_no, o.status, o.service_days, o.service_hours_per_day,
                       o.floor_fee, o.start_date, o.end_date,
                       o.actual_start_date, o.actual_end_date,
                       c.id AS client_id, c.name AS client_name, c.identity_status,
                       c.phone AS client_phone, c.city AS client_city,
                       c.address AS client_address, c.service_time, c.service_type,
                       b.query_no AS beclass_query_no, b.refund_bank_code,
                       b.refund_account_no, b.survey_details
                FROM orders o
                JOIN clients c ON c.case_no = o.case_no
                LEFT JOIN beclass_records b ON b.query_no = o.case_no
                WHERE o.case_no = %s
                """,
                (case_no,),
            )
            case_row = cursor.fetchone()
            if not case_row:
                raise ValueError("case_no does not exist")

            cursor.execute(
                """
                SELECT a.id AS assignment_id, a.case_no, a.staff_id,
                       a.assignment_sequence, a.assigned_start_date,
                       a.assigned_end_date, a.planned_hours, a.actual_hours,
                       a.hourly_rate, a.floor_fee_allocated, a.status,
                       s.name AS staff_name, s.identity_card AS staff_identity_card,
                       s.phone AS staff_phone, s.city AS staff_city, s.address AS staff_address
                FROM case_staff_assignments a
                JOIN staff s ON s.id = a.staff_id
                WHERE a.case_no = %s
                ORDER BY a.assignment_sequence, a.id
                """,
                (case_no,),
            )
            assignments = cursor.fetchall()

            cursor.execute(
                """
                SELECT sba.staff_id, sba.bank_code, sba.branch_code, sba.account_no
                FROM staff_bank_accounts sba
                JOIN case_staff_assignments a ON a.staff_id = sba.staff_id
                WHERE a.case_no = %s AND sba.is_primary = 1
                ORDER BY a.assignment_sequence, sba.id
                """,
                (case_no,),
            )
            primary_bank_accounts = cursor.fetchall()
    finally:
        conn.close()

    source = {
        "case_no": case_no,
        "order": {
            key: case_row.get(key)
            for key in (
                "status", "service_days", "service_hours_per_day",
                "floor_fee", "start_date", "end_date", "actual_start_date", "actual_end_date",
            )
        },
        "client": {
            key: case_row.get(key)
            for key in (
                "client_id", "client_name", "identity_status", "client_phone", "client_city",
                "client_address", "service_time", "service_type",
            )
        },
        "beclass": {
            key: case_row.get(key)
            for key in ("beclass_query_no", "refund_bank_code", "refund_account_no", "survey_details")
        },
        "staff_assignments": assignments,
        "staff_primary_bank_accounts": primary_bank_accounts,
    }
    source["missing_terms"] = _missing_terms(source)
    return source
