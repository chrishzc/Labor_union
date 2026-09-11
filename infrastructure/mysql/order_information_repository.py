"""MySQL adapter for the typed staff order-information projection."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import time, timedelta
import json
from typing import Any

from domains.case_import.order_information import project_order_information
from infrastructure.mysql.order_terms_read_model import load_preview_facts
from subsystems.orders.order_information import (
    OrderInformationOwnerSnapshot,
    projection_fingerprint,
    build_candidate_information,
)


class MySqlOrderInformationRepository:
    """Read-only exact-case/assignment adapter.

    BeClass source data is read only for the Case Import owner projection.  It
    is parsed into named scalar facts before this adapter returns anything;
    raw survey data never crosses the repository boundary.
    """

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_owner_snapshot(
        self, case_no: str, assignment_id: int | None = None
    ) -> OrderInformationOwnerSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_CASE_SQL, (case_no,))
            case = cursor.fetchone()
            if not isinstance(case, Mapping):
                return None
            cursor.execute(_ASSIGNMENTS_SQL, (case_no,))
            assignments = tuple(cursor.fetchall() or ())
        selected = _select_assignment(assignments, assignment_id)
        if selected is None:
            return None
        facts, field_issues = _facts(case, selected)
        owners = {
            "orders": projection_fingerprint(
                {key: facts.get(key) for key in _ORDER_FACT_KEYS}
            ),
            "clients": projection_fingerprint(
                {key: facts.get(key) for key in _CLIENT_FACT_KEYS}
            ),
            "scheduling": projection_fingerprint(
                {key: selected.get(key) for key in _ASSIGNMENT_FACT_KEYS}
            ),
            "staff_payables": projection_fingerprint(
                {"assignment_id": selected.get("assignment_id"), "total_salary": facts.get("total_salary"), "salary_payment_date": facts.get("salary_payment_date")}
            ),
            "case_import": projection_fingerprint(
                {
                    **{key: facts.get(key) for key in _CASE_IMPORT_FACT_KEYS},
                    "issues": dict(sorted(field_issues.items())),
                }
            ),
        }
        _load_typed_payroll_facts(
            self._connection,
            case_no,
            int(selected["assignment_id"]),
            facts,
            owners,
        )
        return OrderInformationOwnerSnapshot(
            case_no=str(case["case_no"]),
            assignment_id=int(selected["assignment_id"]),
            facts=facts,
            owner_fingerprints=owners,
            field_issues=field_issues,
        )

    def preview_candidate_information(
        self,
        case_no: str,
        candidate_id: int,
        info_type: int,
        *,
        for_update: bool = False,
        service_period: tuple[object, object] | None = None,
    ):
        with self._connection.cursor() as cursor:
            cursor.execute(_CASE_SQL + (" FOR UPDATE" if for_update else ""), (case_no,))
            case = cursor.fetchone()
            cursor.execute("""SELECT s.name AS staff_name, s.line_user_id,
                e.service_start_date AS assigned_start_date, e.service_end_date AS assigned_end_date
                FROM caregiver_candidate_contact_entries e
                JOIN caregiver_candidate_contact_pools p ON p.id=e.pool_id
                JOIN staff s ON s.id=e.staff_id
                WHERE p.case_no=%s AND e.id=%s AND e.active_marker=1""", (case_no, candidate_id))
            candidate = cursor.fetchone()
        if not isinstance(case, Mapping) or not isinstance(candidate, Mapping):
            raise ValueError("candidate_contact_not_found")
        if service_period is not None:
            start_date, end_date = service_period
            candidate = {
                **candidate,
                "assigned_start_date": start_date,
                "assigned_end_date": end_date,
            }
        facts, issues = _facts(case, candidate)
        return build_candidate_information(case_no, candidate_id, info_type, facts, issues, candidate.get("line_user_id"))


def _select_assignment(
    assignments: tuple[Mapping[str, object], ...], assignment_id: int | None
) -> Mapping[str, object] | None:
    if assignment_id is not None:
        return next(
            (
                row
                for row in assignments
                if row.get("assignment_id") == assignment_id
                and row.get("status") not in {"cancelled", "replaced"}
            ),
            None,
        )
    active = tuple(row for row in assignments if row.get("status") == "active")
    candidates = active or assignments
    return candidates[0] if len(candidates) == 1 else None


def _facts(
    case: Mapping[str, object], assignment: Mapping[str, object]
) -> tuple[dict[str, object], Mapping[str, str]]:
    # Case Import is the only boundary allowed to parse the source payload.
    # Consumers receive named facts, never the raw survey mapping.
    projection = project_order_information(case.get("_case_import_payload"))
    formal_service_time = _formal_service_time(case)
    facts = {
        "case_no": case.get("case_no"),
        "staff_name": assignment.get("staff_name"),
        "client_name": case.get("client_name"),
        "assigned_start_date": assignment.get("assigned_start_date"),
        "assigned_end_date": assignment.get("assigned_end_date"),
        "service_days": case.get("service_days"),
        "service_hours_per_day": case.get("service_hours_per_day"),
        "requires_cooking": (
            None
            if case.get("requires_cooking") is None
            else bool(case.get("requires_cooking"))
        ),
        "address": case.get("client_address"),
        "phone": case.get("client_phone"),
        "total_salary": None,
        "salary_payment_date": None,
        "special_holidays": _special_holidays_text(case.get("custom_rest_dates")),
        "notes": case.get("client_notes"),
        "service_time": formal_service_time,
        "service_type": case.get("service_type"),
        "baby_info": case.get("baby_info"),
        **projection.values,
    }
    return facts, projection.issues


def _load_typed_payroll_facts(
    connection: Any,
    case_no: str,
    assignment_id: int,
    facts: dict[str, object],
    owners: dict[str, str],
) -> None:
    """Read existing Payroll/Staff Payables projections when available.

    This optional read is still typed: an unavailable owner leaves the field
    missing and therefore fail-closed according to template requiredness.
    """
    try:
        with connection.cursor() as cursor:
            typed = load_preview_facts(cursor, case_no)
        obligations = tuple(
            item
            for item in typed.payroll.existing_obligations
            if item.source_assignment_id == assignment_id
            and item.obligation_kind.value == "service_pay"
            and item.direction.value == "payable_to_staff"
        )
        if len(obligations) == 1:
            obligation = obligations[0]
            facts["total_salary"] = obligation.contracted_amount.amount
            facts["salary_payment_date"] = obligation.due_date
            owners["staff_payables"] = projection_fingerprint(
                {
                    "obligation_identity": obligation.obligation_identity,
                    "assignment_id": assignment_id,
                    "total_salary": facts["total_salary"],
                    "salary_payment_date": facts["salary_payment_date"],
                }
            )
        owners["payroll"] = projection_fingerprint(
            {
                "payroll_version": typed.payroll.payroll_version,
                "assignment_id": assignment_id,
                "staff_payment_due_date": typed.payroll.staff_payment_due_date,
            }
        )
    except Exception:
        # A missing bootstrap is an owner-source blocker, never a raw fallback.
        return


_ORDER_FACT_KEYS = (
    "case_no",
    "service_days",
    "service_hours_per_day",
    "requires_cooking",
    "service_time",
    "special_holidays",
)
_CLIENT_FACT_KEYS = (
    "client_name",
    "phone",
    "address",
    "notes",
    "service_type",
    "baby_info",
)
_ASSIGNMENT_FACT_KEYS = (
    "assignment_id",
    "case_no",
    "staff_id",
    "assigned_start_date",
    "assigned_end_date",
    "hourly_rate",
    "status",
)
_CASE_IMPORT_FACT_KEYS = (
    "dietary_habits",
    "vegetarian_preference",
    "alcohol_ratio",
    "cooking_oil_type",
    "maternal_allergy",
    "special_care_notes",
    "meal_preferences",
    "cooking_tools",
    "bath_water_prep",
    "breastfeeding_method",
    "holiday_pricing_terms",
    "multi_birth_count",
    "stair_floor_fee_mode",
    "parking_space_provided",
    "other_babies_present",
)

_CASE_SQL = """
SELECT o.case_no, o.service_days, o.service_hours_per_day, o.requires_cooking,
       o.service_start_time, o.service_end_time, o.service_end_day_offset,
       o.floor_fee, o.custom_rest_dates,
       c.service_time, c.service_type, c.baby_info,
       c.name AS client_name, c.phone AS client_phone, c.address AS client_address,
       c.notes AS client_notes, b.survey_details AS _case_import_payload
  FROM orders o
  JOIN clients c ON c.id=o.client_id
  LEFT JOIN beclass_records b ON b.bound_case_no=o.case_no
 WHERE o.case_no=%s
"""


def _formal_service_time(case: Mapping[str, object]) -> str | None:
    start = case.get("service_start_time")
    end = case.get("service_end_time")
    offset = case.get("service_end_day_offset")
    if start is None or end is None or offset is None:
        return None
    start_text = _clock_text(start)
    end_text = _clock_text(end)
    if start_text is None or end_text is None:
        return None
    suffix = "（翌日）" if int(offset) == 1 else ""
    return f"{start_text}–{end_text}{suffix}"


def _clock_text(value: object) -> str | None:
    if isinstance(value, timedelta):
        seconds = int(value.total_seconds())
        if seconds < 0 or seconds >= 24 * 60 * 60:
            return None
        hours, remainder = divmod(seconds, 60 * 60)
        minutes = remainder // 60
        return f"{hours:02d}:{minutes:02d}"
    if isinstance(value, time):
        return value.strftime("%H:%M")
    text = str(value).strip()
    parts = text.split(":")
    if len(parts) >= 2 and all(part.isdigit() for part in parts[:2]):
        hours, minutes = int(parts[0]), int(parts[1])
        if 0 <= hours <= 23 and 0 <= minutes <= 59:
            return f"{hours:02d}:{minutes:02d}"
    return None


def _special_holidays_text(value: object) -> str | None:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    dates = tuple(str(item).strip() for item in parsed if str(item).strip())
    return "、".join(dates) or None

_ASSIGNMENTS_SQL = """
SELECT a.id AS assignment_id, a.case_no, a.staff_id,
       a.assigned_start_date, a.assigned_end_date, a.hourly_rate, a.status,
       s.name AS staff_name
  FROM case_staff_assignments a
  JOIN staff s ON s.id=a.staff_id
 WHERE a.case_no=%s AND a.status<>'cancelled'
 ORDER BY a.assignment_sequence, a.id
"""


__all__ = ["MySqlOrderInformationRepository"]
