"""Read-only facts required by the Form Management template workspace."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from shared_kernel.validation import require_canonical_text


_STATISTICS_FIELDS = frozenset({
    "global_active_orders_count",
    "global_active_staff_count",
    "global_govt_claim_count",
    "global_subsidy_orders_count",
    "global_total_receivable_sum",
})
_CONTEXT_FIELDS = frozenset({
    "case_no",
    "city",
    "delivery_type",
    "identity_status",
    "residence_type",
    "service_time",
    "service_type",
})


class FormManagementQueryContractError(ValueError):
    """The read adapter did not return the declared Form Management facts."""


class FormManagementCaseNotFoundError(LookupError):
    """The requested case no longer has a client context."""


@dataclass(frozen=True, slots=True)
class FormManagementStatistics:
    global_active_orders_count: int
    global_active_staff_count: int
    global_subsidy_orders_count: int
    global_total_receivable_sum: int
    global_govt_claim_count: int


@dataclass(frozen=True, slots=True)
class FormManagementCaseContext:
    case_no: str
    service_time: str | None
    service_type: str | None
    delivery_type: str | None
    residence_type: str | None
    city: str | None
    identity_status: str | None


class FormManagementQueryRepository(Protocol):
    def fetch_statistics(self) -> Mapping[str, object]: ...

    def fetch_case_context(self, case_no: str) -> Mapping[str, object] | None: ...


class FormManagementQueryService:
    def __init__(self, repository: FormManagementQueryRepository) -> None:
        self._repository = repository

    def statistics(self) -> FormManagementStatistics:
        return _statistics(self._repository.fetch_statistics())

    def case_context(self, case_no: str) -> FormManagementCaseContext:
        canonical_case_no = require_canonical_text(case_no, "case_no", 50)
        row = self._repository.fetch_case_context(canonical_case_no)
        if row is None:
            raise FormManagementCaseNotFoundError(canonical_case_no)
        return _case_context(row)


def _statistics(row: object) -> FormManagementStatistics:
    _require_exact_fields(row, _STATISTICS_FIELDS)
    return FormManagementStatistics(
        _nonnegative_integer(row, "global_active_orders_count"),
        _nonnegative_integer(row, "global_active_staff_count"),
        _nonnegative_integer(row, "global_subsidy_orders_count"),
        _nonnegative_integer(row, "global_total_receivable_sum"),
        _nonnegative_integer(row, "global_govt_claim_count"),
    )


def _case_context(row: object) -> FormManagementCaseContext:
    _require_exact_fields(row, _CONTEXT_FIELDS)
    return FormManagementCaseContext(
        require_canonical_text(row["case_no"], "case_no", 50),
        _optional_text(row, "service_time"),
        _optional_text(row, "service_type"),
        _optional_text(row, "delivery_type"),
        _optional_text(row, "residence_type"),
        _optional_text(row, "city"),
        _optional_text(row, "identity_status"),
    )


def _require_exact_fields(row: object, fields: frozenset[str]) -> None:
    if not isinstance(row, Mapping) or set(row) != fields:
        raise FormManagementQueryContractError("repository row fields are not canonical")


def _nonnegative_integer(row: Mapping[str, object], field: str) -> int:
    value = row[field]
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise FormManagementQueryContractError(f"{field} must be a nonnegative integer")
    if value < 0 or (isinstance(value, Decimal) and value != value.to_integral_value()):
        raise FormManagementQueryContractError(f"{field} must be a nonnegative integer")
    return int(value)


def _optional_text(row: Mapping[str, object], field: str) -> str | None:
    value = row[field]
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 500:
        raise FormManagementQueryContractError(f"{field} must be text or null")
    return value


__all__ = [
    "FormManagementCaseContext",
    "FormManagementCaseNotFoundError",
    "FormManagementQueryContractError",
    "FormManagementQueryService",
    "FormManagementStatistics",
]
