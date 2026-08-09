"""Typed query service for one formal staff-service contract context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ContractContextNotFound(LookupError):
    pass


class ContractContextAmbiguous(ValueError):
    pass


class ContractContextRepositoryPort(Protocol):
    def load_case_facts(self, case_no: str) -> dict | None: ...
    def load_assignments(self, case_no: str) -> tuple[dict, ...]: ...


class ContractContextQueryService:
    def __init__(self, repository: ContractContextRepositoryPort) -> None:
        self._repository = repository

    def query(self, case_no: str, assignment_id: int | None = None) -> dict:
        case_facts = self._repository.load_case_facts(case_no)
        if case_facts is None:
            raise ContractContextNotFound("case_no_not_found")
        assignments = self._repository.load_assignments(case_no)
        selected = _select_assignment(assignments, assignment_id)
        return _context_payload(case_facts, selected)


def _select_assignment(assignments, assignment_id):
    if assignment_id is not None:
        selected = next((row for row in assignments if row["assignment_id"] == assignment_id), None)
        if selected is None:
            raise ContractContextNotFound("assignment_not_found")
        return selected
    active = tuple(row for row in assignments if row["status"] == "active")
    candidates = active or assignments
    if len(candidates) != 1:
        raise ContractContextAmbiguous("assignment_id_required")
    return candidates[0]


# Kept as one projection map so contract field ownership is reviewable in one place.
def _context_payload(case_facts, selected):
    return {
        "order": _select(case_facts, (
            "case_no", "status", "contract_id", "service_days", "service_hours_per_day",
            "floor_fee", "start_date", "end_date", "actual_start_date", "actual_end_date",
        )),
        "client": _prefixed(case_facts, "client_", (
            "client_id", "client_name", "client_phone", "client_city", "client_address",
            "client_identity_status", "service_type", "service_time", "baby_info", "client_notes",
        )),
        "beclass": _prefixed(case_facts, "beclass_", (
            "beclass_query_no", "survey_details", "beclass_admin_notes",
        )),
        "assignment": _select(selected, (
            "assignment_id", "case_no", "staff_id", "assignment_sequence",
            "assigned_start_date", "assigned_end_date", "planned_hours", "actual_hours",
            "hourly_rate", "floor_fee_allocated", "status", "replacement_reason",
        )),
        "staff": _prefixed(selected, "staff_", (
            "staff_id", "staff_name", "staff_identity_card", "staff_phone", "staff_email",
            "staff_city", "staff_address",
        )),
        "unmapped_template_fields": None,
    }


def _select(source, names):
    return {name: source.get(name) for name in names}


def _prefixed(source, prefix, names):
    return {name.removeprefix(prefix): source.get(name) for name in names}


__all__ = [
    "ContractContextAmbiguous",
    "ContractContextNotFound",
    "ContractContextQueryService",
    "ContractContextRepositoryPort",
]
