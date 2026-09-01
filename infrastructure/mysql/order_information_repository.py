"""MySQL adapter for the typed staff order-information projection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from domains.case_import.order_information import project_order_information
from infrastructure.mysql.order_terms_read_model import load_preview_facts
from subsystems.orders.order_information import (
    OrderInformationOwnerSnapshot,
    projection_fingerprint,
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
            "payroll": projection_fingerprint(
                {"assignment_id": selected.get("assignment_id"), "service_unit_price": facts.get("caregiver_rate")}
            ),
            "staff_payables": projection_fingerprint(
                {"assignment_id": selected.get("assignment_id"), "service_salary": facts.get("service_salary"), "salary_payment_date_1": facts.get("salary_payment_date_1")}
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
    facts = {
        "case_no": case.get("case_no"),
        "staff_name": assignment.get("staff_name"),
        "client_name": case.get("client_name"),
        "assigned_start_date": assignment.get("assigned_start_date"),
        "assigned_end_date": assignment.get("assigned_end_date"),
        "service_hours_per_day": case.get("service_hours_per_day"),
        "service_days": case.get("service_days"),
        "address": case.get("client_address"),
        "phone": case.get("client_phone"),
        "caregiver_rate": assignment.get("hourly_rate"),
        "service_salary": None,
        "salary_payment_date_1": None,
        "floor_fee": case.get("floor_fee"),
        "notes": case.get("client_notes"),
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
            facts["service_salary"] = obligation.contracted_amount.amount
            facts["salary_payment_date_1"] = obligation.due_date
            owners["staff_payables"] = projection_fingerprint(
                {
                    "obligation_identity": obligation.obligation_identity,
                    "assignment_id": assignment_id,
                    "service_salary": facts["service_salary"],
                    "salary_payment_date_1": facts["salary_payment_date_1"],
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
    "service_hours_per_day",
    "service_days",
    "floor_fee",
)
_CLIENT_FACT_KEYS = ("client_name", "phone", "address", "notes")
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
SELECT o.case_no, o.service_days, o.service_hours_per_day, o.floor_fee,
       c.name AS client_name, c.phone AS client_phone, c.address AS client_address,
       c.notes AS client_notes, b.survey_details AS _case_import_payload
  FROM orders o
  JOIN clients c ON c.id=o.client_id
  LEFT JOIN beclass_records b ON b.bound_case_no=o.case_no
 WHERE o.case_no=%s
"""

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
