"""Validate the bounded Orders calendar detail read projection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

SUPPORTED_SERVICE_MODES = frozenset({"休周六", "休周日", "週休2日", "連續服務"})
_LEGACY_SERVICE_MODE_ALIASES = {
    "週休1日": "休周日",
    "週休一日": "休周日",
    "週休二日": "週休2日",
    "周休二日": "週休2日",
}
_EXPECTED_FIELDS = frozenset({"case_no", "service_mode"})


class OrderCalendarDetailNotFoundError(LookupError):
    pass


class OrderCalendarDetailContractError(ValueError):
    pass


class OrderCalendarDetailRepository(Protocol):
    def fetch_by_case_no(self, case_no: str) -> Mapping[str, object] | None:
        ...


@dataclass(frozen=True)
class OrderCalendarDetail:
    case_no: str
    service_mode: str | None
    original_service_type: str | None = None


class OrderCalendarDetailQueryService:
    def __init__(self, repository: OrderCalendarDetailRepository) -> None:
        self._repository = repository

    def query(self, case_no: str) -> OrderCalendarDetail:
        canonical_case_no = _canonical_case_no(case_no)
        row = self._repository.fetch_by_case_no(canonical_case_no)
        if row is None:
            raise OrderCalendarDetailNotFoundError(canonical_case_no)
        return _validated_detail(row, canonical_case_no)


def _canonical_case_no(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("case_no is required")
    if value.strip() != value or len(value) > 50:
        raise ValueError("case_no must be canonical")
    return value


def _validated_detail(row: Mapping[str, object], expected_case_no: str) -> OrderCalendarDetail:
    if frozenset(row) not in {_EXPECTED_FIELDS, _EXPECTED_FIELDS | {"original_service_type"}}:
        raise OrderCalendarDetailContractError("unexpected projection fields")
    case_no = row.get("case_no")
    service_mode = row.get("service_mode")
    original = row.get("original_service_type", service_mode)
    if original is not None and (not isinstance(original, str) or len(original) > 100):
        raise OrderCalendarDetailContractError("invalid original service type")
    if service_mode is not None and not isinstance(service_mode, str):
        raise OrderCalendarDetailContractError("unsupported service mode")
    if isinstance(service_mode, str):
        service_mode = _LEGACY_SERVICE_MODE_ALIASES.get(service_mode, service_mode)
    if case_no != expected_case_no:
        raise OrderCalendarDetailContractError("case identity drift")
    # Unrecognized source text is display evidence, never an inferred calendar rule.
    if service_mode not in SUPPORTED_SERVICE_MODES:
        service_mode = None
    return OrderCalendarDetail(case_no, service_mode, original)


__all__ = [
    "OrderCalendarDetail",
    "OrderCalendarDetailContractError",
    "OrderCalendarDetailNotFoundError",
    "OrderCalendarDetailQueryService",
]
