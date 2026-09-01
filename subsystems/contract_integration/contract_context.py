"""Typed query contract for one formal staff-service contract context."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from shared_kernel.validation import require_canonical_text, require_positive_integer


class ContractContextNotFound(LookupError):
    """The requested case or formal assignment does not exist."""


class ContractContextAmbiguous(ValueError):
    """The case has more than one possible formal assignment."""


class ContractContextContractError(ValueError):
    """A repository row does not satisfy the bounded query contract."""


DateValue = date | datetime | str | None
NumberValue = int | float | None
SurveyDetails = Mapping[str, object] | str | None


@dataclass(frozen=True, slots=True)
class ContractOrderContext:
    case_no: str
    status: str | None
    contract_identity: str | None
    service_days: int | None
    service_hours_per_day: NumberValue
    floor_fee: NumberValue
    start_date: DateValue
    end_date: DateValue
    actual_start_date: DateValue
    actual_end_date: DateValue


@dataclass(frozen=True, slots=True)
class ContractClientContext:
    id: int
    name: str | None
    phone: str | None
    city: str | None
    address: str | None
    identity_status: str | None
    service_type: str | None
    service_time: str | None
    baby_info: str | None
    delivery_type: str | None
    residence_type: str | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class ContractBeClassContext:
    query_no: str | None
    survey_details: SurveyDetails
    admin_notes: str | None


@dataclass(frozen=True, slots=True)
class ContractAssignmentContext:
    assignment_id: int
    case_no: str
    staff_id: int
    assignment_sequence: int | None
    assigned_start_date: DateValue
    assigned_end_date: DateValue
    planned_hours: NumberValue
    actual_hours: NumberValue
    hourly_rate: NumberValue
    floor_fee_allocated: NumberValue
    status: str | None
    replacement_reason: str | None


@dataclass(frozen=True, slots=True)
class ContractStaffContext:
    id: int
    name: str | None
    identity_card: str | None
    phone: str | None
    email: str | None
    city: str | None
    address: str | None


@dataclass(frozen=True, slots=True)
class ContractContextView:
    """Owner projection returned by the Contract Signing query."""

    order: ContractOrderContext
    client: ContractClientContext
    beclass: ContractBeClassContext
    assignment: ContractAssignmentContext
    staff: ContractStaffContext
    unmapped_template_fields: None = None


class ContractContextRepositoryPort(Protocol):
    def load_case_facts(self, case_no: str) -> Mapping[str, object] | None: ...

    def load_assignments(self, case_no: str) -> tuple[Mapping[str, object], ...]: ...


class ContractContextQueryService:
    """Project repository rows into one bounded, typed contract context."""

    def __init__(self, repository: ContractContextRepositoryPort) -> None:
        self._repository = repository

    def query(
        self, case_no: str, assignment_id: int | None = None
    ) -> ContractContextView:
        require_canonical_text(case_no, "case number", 50)
        if assignment_id is not None:
            require_positive_integer(assignment_id, "assignment id")
        case_facts = self._repository.load_case_facts(case_no)
        if case_facts is None:
            raise ContractContextNotFound("case_no_not_found")
        assignments = self._repository.load_assignments(case_no)
        selected = _select_assignment(assignments, assignment_id)
        return ContractContextView(
            order=_order(case_facts),
            client=_client(case_facts),
            beclass=_beclass(case_facts),
            assignment=_assignment(selected),
            staff=_staff(selected),
        )


def _select_assignment(
    assignments: tuple[Mapping[str, object], ...], assignment_id: int | None
) -> Mapping[str, object]:
    if assignment_id is not None:
        selected = next(
            (row for row in assignments if row.get("assignment_id") == assignment_id),
            None,
        )
        if selected is None:
            raise ContractContextNotFound("assignment_not_found")
        return selected
    active = tuple(row for row in assignments if row.get("status") == "active")
    candidates = active or assignments
    if len(candidates) != 1:
        raise ContractContextAmbiguous("assignment_id_required")
    return candidates[0]


def _order(row: Mapping[str, object]) -> ContractOrderContext:
    return ContractOrderContext(
        case_no=_required_text(row, "case_no"),
        status=_optional_text(row, "status"),
        contract_identity=_optional_text(row, "contract_identity"),
        service_days=_optional_int(row, "service_days"),
        service_hours_per_day=_number(row, "service_hours_per_day"),
        floor_fee=_number(row, "floor_fee"),
        start_date=_date_value(row, "start_date"),
        end_date=_date_value(row, "end_date"),
        actual_start_date=_date_value(row, "actual_start_date"),
        actual_end_date=_date_value(row, "actual_end_date"),
    )


def _client(row: Mapping[str, object]) -> ContractClientContext:
    return ContractClientContext(
        id=_required_int(row, "client_id"),
        name=_optional_text(row, "client_name"),
        phone=_optional_text(row, "client_phone"),
        city=_optional_text(row, "client_city"),
        address=_optional_text(row, "client_address"),
        identity_status=_optional_text(row, "client_identity_status"),
        service_type=_optional_text(row, "service_type"),
        service_time=_optional_text(row, "service_time"),
        baby_info=_optional_text(row, "baby_info"),
        delivery_type=_optional_text(row, "delivery_type"),
        residence_type=_optional_text(row, "residence_type"),
        notes=_optional_text(row, "client_notes"),
    )


def _beclass(row: Mapping[str, object]) -> ContractBeClassContext:
    details = row.get("survey_details")
    if details is not None and not isinstance(details, (Mapping, str)):
        raise ContractContextContractError("survey_details is invalid")
    return ContractBeClassContext(
        query_no=_optional_text(row, "beclass_query_no"),
        survey_details=details,
        admin_notes=_optional_text(row, "beclass_admin_notes"),
    )


def _assignment(row: Mapping[str, object]) -> ContractAssignmentContext:
    return ContractAssignmentContext(
        assignment_id=_required_int(row, "assignment_id"),
        case_no=_required_text(row, "case_no"),
        staff_id=_required_int(row, "staff_id"),
        assignment_sequence=_optional_int(row, "assignment_sequence"),
        assigned_start_date=_date_value(row, "assigned_start_date"),
        assigned_end_date=_date_value(row, "assigned_end_date"),
        planned_hours=_number(row, "planned_hours"),
        actual_hours=_number(row, "actual_hours"),
        hourly_rate=_number(row, "hourly_rate"),
        floor_fee_allocated=_number(row, "floor_fee_allocated"),
        status=_optional_text(row, "status"),
        replacement_reason=_optional_text(row, "replacement_reason"),
    )


def _staff(row: Mapping[str, object]) -> ContractStaffContext:
    return ContractStaffContext(
        id=_required_int(row, "staff_id"),
        name=_optional_text(row, "staff_name"),
        identity_card=_optional_text(row, "staff_identity_card"),
        phone=_optional_text(row, "staff_phone"),
        email=_optional_text(row, "staff_email"),
        city=_optional_text(row, "staff_city"),
        address=_optional_text(row, "staff_address"),
    )


def _required_text(row: Mapping[str, object], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise ContractContextContractError(f"{field} is invalid")
    return value


def _optional_text(row: Mapping[str, object], field: str) -> str | None:
    value = row.get(field)
    if value is not None and not isinstance(value, str):
        raise ContractContextContractError(f"{field} is invalid")
    return value


def _required_int(row: Mapping[str, object], field: str) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContractContextContractError(f"{field} is invalid")
    return value


def _optional_int(row: Mapping[str, object], field: str) -> int | None:
    value = row.get(field)
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise ContractContextContractError(f"{field} is invalid")
    return value


def _number(row: Mapping[str, object], field: str) -> NumberValue:
    value = row.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        try:
            value = float(value)
        except (TypeError, ValueError) as error:
            raise ContractContextContractError(f"{field} is invalid") from error
    return value


def _date_value(row: Mapping[str, object], field: str) -> DateValue:
    value = row.get(field)
    if value is not None and not isinstance(value, (date, datetime, str)):
        raise ContractContextContractError(f"{field} is invalid")
    return value


__all__ = [
    "ContractAssignmentContext",
    "ContractBeClassContext",
    "ContractClientContext",
    "ContractContextAmbiguous",
    "ContractContextContractError",
    "ContractContextNotFound",
    "ContractContextQueryService",
    "ContractContextRepositoryPort",
    "ContractContextView",
    "ContractOrderContext",
    "ContractStaffContext",
]
