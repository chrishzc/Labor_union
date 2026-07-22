"""Read-only contract context endpoints.

The staff-service contract is tied to a formal assignment, not the legacy
``orders.staff_id`` convenience field.  This router deliberately returns raw
facts only; generating or changing a workbook belongs to the UI/export layer.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.schemas.base import BaseResponse
from services.db_service import get_connection


router = APIRouter(prefix="/api/v1/contracts", tags=["Contracts"])


def _load_case_facts(cursor: Any, case_no: str) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT o.case_no, o.status, o.contract_id, o.service_days,
               o.service_hours_per_day, o.floor_fee,
               o.start_date, o.end_date, o.actual_start_date, o.actual_end_date,
               c.id AS client_id, c.name AS client_name, c.phone AS client_phone,
               c.city AS client_city, c.address AS client_address,
               c.identity_status AS client_identity_status,
               c.service_type, c.service_time, c.baby_info, c.notes AS client_notes,
               b.query_no AS beclass_query_no, b.survey_details, b.admin_notes AS beclass_admin_notes
        FROM orders o
        JOIN clients c ON c.case_no = o.case_no
        LEFT JOIN beclass_records b ON b.query_no = o.case_no
        WHERE o.case_no = %s
        """,
        (case_no,),
    )
    return cursor.fetchone()


def _load_assignments(cursor: Any, case_no: str) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT a.id AS assignment_id, a.case_no, a.staff_id, a.assignment_sequence,
               a.assigned_start_date, a.assigned_end_date, a.planned_hours,
               a.actual_hours, a.hourly_rate, a.floor_fee_allocated, a.status,
               a.replacement_reason,
               s.name AS staff_name, s.identity_card AS staff_identity_card,
               s.phone AS staff_phone, s.email AS staff_email, s.city AS staff_city,
               s.address AS staff_address, s.weekly_rest_days, s.service_regions
        FROM case_staff_assignments a
        JOIN staff s ON s.id = a.staff_id
        WHERE a.case_no = %s AND a.status <> 'cancelled'
        ORDER BY a.assignment_sequence, a.id
        """,
        (case_no,),
    )
    return cursor.fetchall()


def get_staff_contract_context(case_no: str, assignment_id: int | None = None) -> dict[str, Any]:
    """Return contract facts for exactly one formal staff assignment."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            case_facts = _load_case_facts(cursor, case_no)
            if not case_facts:
                raise HTTPException(status_code=404, detail="case_no does not exist")

            assignments = _load_assignments(cursor, case_no)
            active_assignments = [item for item in assignments if item["status"] == "active"]

            if assignment_id is None:
                if len(active_assignments) > 1:
                    raise HTTPException(
                        status_code=422,
                        detail="assignment_id is required when multiple active assignments exist",
                    )
                candidates = active_assignments or assignments
                if len(candidates) != 1:
                    raise HTTPException(
                        status_code=422,
                        detail="assignment_id is required when the formal assignment is ambiguous",
                    )
                selected = candidates[0]
            else:
                selected = next(
                    (item for item in assignments if item["assignment_id"] == assignment_id),
                    None,
                )
                if not selected:
                    raise HTTPException(status_code=404, detail="assignment_id does not belong to case_no")

            order = {
                key: case_facts.get(key)
                for key in (
                    "case_no", "status", "contract_id", "service_days",
                    "service_hours_per_day", "floor_fee",
                    "start_date", "end_date", "actual_start_date", "actual_end_date",
                )
            }
            client = {
                key.removeprefix("client_"): case_facts.get(key)
                for key in (
                    "client_id", "client_name", "client_phone", "client_city",
                    "client_address", "client_identity_status", "service_type", "service_time", "baby_info",
                    "client_notes",
                )
            }
            beclass = {
                key.removeprefix("beclass_"): case_facts.get(key)
                for key in ("beclass_query_no", "survey_details", "beclass_admin_notes")
            }
            staff = {
                key.removeprefix("staff_"): selected.get(key)
                for key in (
                    "staff_id", "staff_name", "staff_identity_card", "staff_phone",
                    "staff_email", "staff_city", "staff_address",
                )
            }
            assignment = {
                key: selected.get(key)
                for key in (
                    "assignment_id", "case_no", "staff_id", "assignment_sequence",
                    "assigned_start_date", "assigned_end_date", "planned_hours",
                    "actual_hours", "hourly_rate", "floor_fee_allocated", "status",
                    "replacement_reason",
                )
            }
            return {
                "order": order,
                "client": client,
                "beclass": beclass,
                "assignment": assignment,
                "staff": staff,
                "unmapped_template_fields": None,
            }
    finally:
        conn.close()


@router.get("/staff/{case_no}", response_model=BaseResponse[dict[str, Any]])
def get_staff_contract_by_case_no(
    case_no: str,
    assignment_id: int | None = Query(default=None, ge=1),
) -> BaseResponse[dict[str, Any]]:
    """Read the contract context; this endpoint never writes a workbook or database row."""
    return BaseResponse(data=get_staff_contract_context(case_no, assignment_id), message="contract context loaded")
