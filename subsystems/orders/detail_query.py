"""Typed, intentional detail projection for one selected order."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from shared_kernel.validation import require_canonical_text


_DETAIL_FIELDS = frozenset({
    "actual_end_date", "actual_start_date", "cancel_reason", "case_no",
    "client_id", "client_name", "contract_id", "custom_rest_dates",
    "deposit_date", "deposit_service_days", "end_date", "floor_fee",
    "identity_status", "line_group_id", "order_status", "service_days",
    "service_hours_per_day", "staff_id", "staff_name", "start_date",
})


class OrderDetailContractError(ValueError):
    """The detail adapter returned facts outside the declared projection."""


class OrderDetailNotFoundError(LookupError):
    """The selected case has no canonical order projection."""


class OrderDetailRepository(Protocol):
    def fetch_by_case_no(self, case_no: str) -> Mapping[str, object] | None: ...


@dataclass(frozen=True, slots=True)
class OrderDetail:
    case_no: str
    client_id: int
    staff_id: int | None
    client_name: str
    staff_name: str | None
    order_status: str
    identity_status: str
    cancel_reason: str | None
    line_group_id: str | None
    contract_id: str | None
    actual_start_date: date | None
    actual_end_date: date | None
    deposit_date: date | None
    start_date: date | None
    end_date: date | None
    service_days: int
    service_hours_per_day: int
    deposit_service_days: int | None
    floor_fee: int
    custom_rest_dates: str | None


class OrderDetailQueryService:
    def __init__(self, repository: OrderDetailRepository) -> None:
        self._repository = repository

    def query(self, case_no: str) -> OrderDetail:
        canonical_case_no = require_canonical_text(case_no, "case_no", 50)
        row = self._repository.fetch_by_case_no(canonical_case_no)
        if row is None:
            raise OrderDetailNotFoundError(canonical_case_no)
        return _detail(row)


def _detail(row: object) -> OrderDetail:
    if not isinstance(row, Mapping) or set(row) != _DETAIL_FIELDS:
        raise OrderDetailContractError("repository row fields are not canonical")
    return OrderDetail(
        case_no=_text(row, "case_no", 50), client_id=_positive_id(row, "client_id"),
        staff_id=_optional_id(row, "staff_id"), client_name=_text(row, "client_name", 200),
        staff_name=_optional_text(row, "staff_name", 200), order_status=_text(row, "order_status", 100),
        identity_status=_text(row, "identity_status", 100), cancel_reason=_optional_text(row, "cancel_reason", 10000),
        line_group_id=_optional_text(row, "line_group_id", 100), contract_id=_optional_text(row, "contract_id", 100),
        actual_start_date=_optional_date(row, "actual_start_date"), actual_end_date=_optional_date(row, "actual_end_date"),
        deposit_date=_optional_date(row, "deposit_date"), start_date=_optional_date(row, "start_date"),
        end_date=_optional_date(row, "end_date"), service_days=_nonnegative_integer(row, "service_days"),
        service_hours_per_day=_nonnegative_integer(row, "service_hours_per_day"),
        deposit_service_days=_optional_nonnegative_integer(row, "deposit_service_days"),
        floor_fee=_nonnegative_integer(row, "floor_fee"), custom_rest_dates=_optional_text(row, "custom_rest_dates", 10000),
    )


def _text(row: Mapping[str, object], field: str, maximum_length: int) -> str:
    try:
        return require_canonical_text(row[field], field, maximum_length)
    except ValueError as error:
        raise OrderDetailContractError(str(error)) from error


def _optional_text(row: Mapping[str, object], field: str, maximum_length: int) -> str | None:
    value = row[field]
    if value is None:
        return None
    return _text(row, field, maximum_length)


def _optional_date(row: Mapping[str, object], field: str) -> date | None:
    value = row[field]
    if value is None:
        return None
    if isinstance(value, datetime) or not isinstance(value, date):
        raise OrderDetailContractError(f"{field} must be a date or null")
    return value


def _positive_id(row: Mapping[str, object], field: str) -> int:
    value = _nonnegative_integer(row, field)
    if value <= 0:
        raise OrderDetailContractError(f"{field} must be a positive integer")
    return value


def _optional_id(row: Mapping[str, object], field: str) -> int | None:
    if row[field] is None:
        return None
    return _positive_id(row, field)


def _optional_nonnegative_integer(row: Mapping[str, object], field: str) -> int | None:
    if row[field] is None:
        return None
    return _nonnegative_integer(row, field)


def _nonnegative_integer(row: Mapping[str, object], field: str) -> int:
    value = row[field]
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise OrderDetailContractError(f"{field} must be a nonnegative integer")
    if value < 0 or isinstance(value, Decimal) and value != value.to_integral_value():
        raise OrderDetailContractError(f"{field} must be a nonnegative integer")
    return int(value)


__all__ = [
    "OrderDetail", "OrderDetailContractError", "OrderDetailNotFoundError",
    "OrderDetailQueryService", "OrderDetailRepository",
]
