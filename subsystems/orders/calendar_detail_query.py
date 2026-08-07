"""Validate the bounded Orders calendar detail read projection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

SUPPORTED_SERVICE_MODES = frozenset({"週休2日", "週休1日", "連續服務"})
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
    service_mode: str


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
    if frozenset(row) != _EXPECTED_FIELDS:
        raise OrderCalendarDetailContractError("unexpected projection fields")
    case_no = row.get("case_no")
    service_mode = row.get("service_mode")
    if case_no != expected_case_no:
        raise OrderCalendarDetailContractError("case identity drift")
    if service_mode not in SUPPORTED_SERVICE_MODES:
        raise OrderCalendarDetailContractError("unsupported service mode")
    return OrderCalendarDetail(case_no, service_mode)


__all__ = [
    "OrderCalendarDetail",
    "OrderCalendarDetailContractError",
    "OrderCalendarDetailNotFoundError",
    "OrderCalendarDetailQueryService",
]

