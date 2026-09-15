"""MySQL adapter for the typed staff order-information projection."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, time, timedelta
from decimal import Decimal
import json
from typing import Any

from domains.case_import.order_information import project_order_information
from domains.payroll.payment_due_date import calculate_staff_payment_due_date
from domains.orders.floor_fee import allocate_largest_remainder
from infrastructure.mysql.order_terms_read_model import load_preview_facts
from infrastructure.mysql.effective_case_service_rate import (
    load_explicit_case_service_rate,
)
from shared_kernel.money import MoneyNTD
from subsystems.orders.order_information import (
    OrderInformationOwnerSnapshot,
    projection_fingerprint,
    build_candidate_information,
    build_order_information_message,
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
            case = _apply_explicit_rate_correction(cursor, case, case_no)
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
            if isinstance(case, Mapping):
                case = _apply_explicit_rate_correction(cursor, case, case_no)
            cursor.execute("""SELECT s.name AS staff_name, binding.line_user_id,
                e.service_start_date AS assigned_start_date, e.service_end_date AS assigned_end_date
                FROM caregiver_candidate_contact_entries e
                JOIN caregiver_candidate_contact_pools p ON p.id=e.pool_id
                JOIN staff s ON s.id=e.staff_id
                LEFT JOIN line_identity_role_bindings binding ON binding.subject_type='staff'
                AND binding.subject_reference=CAST(s.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci
                AND binding.binding_status='bound' AND binding.line_user_id=s.line_user_id
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

    def preview_matching_plan_information(
        self, case_no: str, plan_id: int, info_type: int, *, for_update: bool = False,
    ) -> tuple[dict[str, object], ...]:
        """Use the existing sheet formatter for every formal-plan segment.

        A formal plan has no candidate-pool identity, so it supplies its own
        authoritative period and staff facts without pretending to be a
        candidate contact record.
        """
        with self._connection.cursor() as cursor:
            cursor.execute(_CASE_SQL + (" FOR UPDATE" if for_update else ""), (case_no,))
            case = cursor.fetchone()
            if isinstance(case, Mapping):
                case = _apply_explicit_rate_correction(cursor, case, case_no)
            cursor.execute(_FORMAL_PLAN_SEGMENTS_SQL, (plan_id, case_no))
            segments = tuple(cursor.fetchall() or ())
        if not isinstance(case, Mapping) or not segments:
            raise ValueError("matching_plan_information_not_found")
        estimates = _matching_plan_payroll_estimates(case, segments)
        result: list[dict[str, object]] = []
        for segment in segments:
            segment_facts = {**segment, **estimates[int(segment["assignment_id"])]}
            facts, issues = _facts(case, segment_facts)
            text, blockers = build_order_information_message(
                info_type, facts, issues,
                "正式推薦方案資訊；服務期間以目前正式媒合方案為準。",
            )
            if blockers:
                raise ValueError(blockers[0])
            result.append({
                "segment_id": int(segment["assignment_id"]),
                "staff_id": int(segment["staff_id"]),
                "staff_name": str(segment["staff_name"]),
                "text": text,
            })
        return tuple(result)


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
        "total_salary": assignment.get("estimated_total_salary"),
        "salary_payment_date": assignment.get("estimated_salary_payment_date"),
        "special_holidays": _special_holidays_text(case.get("custom_rest_dates")),
        "notes": case.get("client_notes"),
        "service_time": formal_service_time,
        "service_type": case.get("service_type"),
        "baby_info": case.get("baby_info"),
        **projection.values,
        **(
            {"multi_birth_count": case["_effective_multi_birth_count"]}
            if case.get("_effective_multi_birth_count") is not None
            else {}
        ),
    }
    issues = dict(projection.issues)
    if case.get("_effective_multi_birth_count") is not None:
        issues.pop("multi_birth_count", None)
    return facts, issues


def _apply_explicit_rate_correction(cursor, case, case_no):
    rate = load_explicit_case_service_rate(cursor, case_no)
    if rate is None:
        return case
    return {
        **dict(case),
        "client_hourly_rate_ntd": rate.hourly_rate_ntd,
        "payroll_hourly_rate_ntd": rate.hourly_rate_ntd,
        "_effective_multi_birth_count": rate.multi_birth_count,
    }


def _matching_plan_payroll_estimates(
    case: Mapping[str, object],
    segments: tuple[Mapping[str, object], ...],
) -> dict[int, dict[str, str]]:
    """Project explicitly labelled estimates without creating Payroll facts."""
    hourly_rate = _positive_integer(case.get("payroll_hourly_rate_ntd"))
    hours_per_day = _positive_half_hour(case.get("service_hours_per_day"))
    contracted_days = _positive_integer(case.get("service_days"))
    if hourly_rate is None or hours_per_day is None or contracted_days is None:
        raise ValueError("matching_plan_payroll_estimate_source_missing")
    service_days = {
        str(int(item["assignment_id"])): _inclusive_day_count(
            item.get("assigned_start_date"), item.get("assigned_end_date")
        )
        for item in segments
    }
    total_planned_days = sum(service_days.values())
    if total_planned_days != contracted_days:
        raise ValueError("matching_plan_payroll_estimate_service_days_mismatch")
    floor_allocations = allocate_largest_remainder(
        MoneyNTD(int(case.get("floor_fee") or 0)), service_days
    )
    planned_end = max(_required_date(item.get("assigned_end_date")) for item in segments)
    client_hourly_rate = _positive_integer(
        case.get("client_hourly_rate_ntd"), allow_zero=True
    )
    if client_hourly_rate is None:
        raise ValueError("matching_plan_client_payment_estimate_source_missing")
    client_payable = _whole_ntd(
        Decimal(contracted_days) * Decimal(str(hours_per_day)) * Decimal(client_hourly_rate)
        + Decimal(int(case.get("floor_fee") or 0)),
        "matching_plan_client_payment_estimate_not_whole_ntd",
    )
    full_subsidy = (
        str(case.get("client_identity_status") or "").strip() == "補助市民"
        and contracted_days * hours_per_day <= 120
        and client_payable == 0
    )
    due_date = calculate_staff_payment_due_date(
        planned_end, client_payable, full_subsidy
    )
    return {
        int(item["assignment_id"]): {
            "estimated_total_salary": (
                f"預估 {_whole_ntd(Decimal(service_days[str(int(item['assignment_id']))]) * Decimal(str(hours_per_day)) * Decimal(hourly_rate) + Decimal(floor_allocations[str(int(item['assignment_id']))].amount), 'matching_plan_payroll_estimate_not_whole_ntd')} 元"
            ),
            "estimated_salary_payment_date": f"預估 {due_date.isoformat()}",
        }
        for item in segments
    }


def _positive_integer(value: object, *, allow_zero: bool = False) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= (0 if allow_zero else 1) else None


def _positive_half_hour(value: object) -> float | int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except Exception:
        return None
    if not parsed.is_finite() or parsed <= 0 or parsed > 24 or parsed * 2 != (parsed * 2).to_integral_value():
        return None
    return int(parsed) if parsed == parsed.to_integral_value() else float(parsed)


def _whole_ntd(value: Decimal, error_code: str) -> int:
    if value != value.to_integral_value():
        raise ValueError(error_code)
    return int(value)


def _required_date(value: object) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as error:
        raise ValueError("matching_plan_payroll_estimate_date_invalid") from error


def _inclusive_day_count(start: object, end: object) -> int:
    start_date, end_date = _required_date(start), _required_date(end)
    if start_date > end_date:
        raise ValueError("matching_plan_payroll_estimate_date_invalid")
    return (end_date - start_date).days + 1


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
       o.floor_fee, o.custom_rest_dates, o.staff_payment_due_date,
       c.service_time, c.service_type, c.baby_info,
       c.identity_status AS client_identity_status,
       c.name AS client_name, c.phone AS client_phone, c.address AS client_address,
       c.notes AS client_notes, b.survey_details AS _case_import_payload,
       payment_terms.client_hourly_rate_ntd,
       payroll_policy.hourly_rate_ntd AS payroll_hourly_rate_ntd
  FROM orders o
  JOIN clients c ON c.id=o.client_id
  LEFT JOIN beclass_records b ON b.bound_case_no=o.case_no
  LEFT JOIN client_payment_terms payment_terms ON payment_terms.case_no=o.case_no
  LEFT JOIN case_payroll_rate_policy_snapshots payroll_policy ON payroll_policy.case_no=o.case_no
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

_FORMAL_PLAN_SEGMENTS_SQL = """
SELECT segment.id AS assignment_id,segment.staff_id,segment.assigned_start_date,
       segment.assigned_end_date,staff.name AS staff_name
  FROM caregiver_matching_plans plan
  JOIN caregiver_matching_plan_segments segment ON segment.plan_id=plan.id
  JOIN staff ON staff.id=segment.staff_id
 WHERE plan.id=%s AND plan.case_no=%s
 ORDER BY segment.segment_order,segment.id
"""


__all__ = ["MySqlOrderInformationRepository"]
