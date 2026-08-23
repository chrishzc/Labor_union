"""
File: summary_query.py
Description: 提供正式與歷史案件的唯讀訂單摘要，保留待補件欄位空值。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from typing import Mapping, Protocol

from shared_kernel.validation import require_canonical_text, require_positive_integer


MAXIMUM_PAGE_SIZE = 200
_MAXIMUM_CASE_NO_LENGTH = 50
_MAXIMUM_QUERY_TEXT_LENGTH = 100
_SUMMARY_FIELDS = frozenset({
    "actual_end_date",
    "actual_start_date",
    "case_no",
    "client_name",
    "end_date",
    "identity_status",
    "order_status",
    "service_days",
    "staff_name",
    "start_date",
    "total_employer_self_pay_payable",
})


class OrderSummaryContractError(ValueError):
    """Raised when the repository violates the Orders summary projection contract."""


class OrderSummaryRepository(Protocol):
    def fetch_page(
        self, *, after_case_no: str | None, page_size: int, query_text: str | None
    ) -> tuple[Mapping[str, object], ...]: ...


@dataclass(frozen=True)
class OrderSummaryQueryRequest:
    page_size: int
    after_case_no: str | None
    query_text: str | None = None

    def __post_init__(self) -> None:
        require_positive_integer(self.page_size, "page_size")
        if self.page_size > MAXIMUM_PAGE_SIZE:
            raise ValueError("page_size must not exceed 200")
        if self.after_case_no is not None:
            require_canonical_text(
                self.after_case_no, "after_case_no", _MAXIMUM_CASE_NO_LENGTH
            )
        if self.query_text is not None:
            require_canonical_text(
                self.query_text, "query_text", _MAXIMUM_QUERY_TEXT_LENGTH
            )


@dataclass(frozen=True)
class OrderSummaryItem:
    case_no: str
    client_name: str
    order_status: str
    staff_name: str | None
    identity_status: str | None
    start_date: date | None
    end_date: date | None
    actual_start_date: date | None
    actual_end_date: date | None
    service_days: int | None
    total_employer_self_pay_payable: int | None


@dataclass(frozen=True)
class OrderSummaryPage:
    items: tuple[OrderSummaryItem, ...]
    next_cursor: str | None
    etag: str


class OrderSummaryQueryService:
    def __init__(self, repository: OrderSummaryRepository) -> None:
        self._repository = repository

    def query(self, request: OrderSummaryQueryRequest) -> OrderSummaryPage:
        rows = self._repository.fetch_page(
            after_case_no=request.after_case_no,
            page_size=request.page_size,
            query_text=request.query_text,
        )
        _validate_repository_page(rows, request)
        items = tuple(_summary_item(row) for row in rows[: request.page_size])
        _validate_item_identity(items)
        next_cursor = items[-1].case_no if len(rows) > request.page_size else None
        return OrderSummaryPage(items, next_cursor, _page_etag(items, next_cursor))


def _validate_repository_page(
    rows: object, request: OrderSummaryQueryRequest
) -> None:
    if not isinstance(rows, tuple):
        raise OrderSummaryContractError("repository page must be a tuple")
    if len(rows) > request.page_size + 1:
        raise OrderSummaryContractError("repository page exceeded page_size + 1")


def _summary_item(row: object) -> OrderSummaryItem:
    if not isinstance(row, Mapping) or set(row) != _SUMMARY_FIELDS:
        raise OrderSummaryContractError("repository row fields are not canonical")
    case_no = _required_text(row, "case_no", _MAXIMUM_CASE_NO_LENGTH)
    return OrderSummaryItem(
        case_no=case_no,
        client_name=_client_name(row, case_no),
        order_status=_required_text(row, "order_status", 100),
        staff_name=_optional_text(row, "staff_name", 200),
        identity_status=_optional_text(row, "identity_status", 100),
        start_date=_optional_date(row, "start_date"),
        end_date=_optional_date(row, "end_date"),
        actual_start_date=_optional_date(row, "actual_start_date"),
        actual_end_date=_optional_date(row, "actual_end_date"),
        service_days=_optional_planned_service_days(row),
        total_employer_self_pay_payable=_optional_nonnegative_ntd(
            row, "total_employer_self_pay_payable"
        ),
    )


def _client_name(row: Mapping[str, object], case_no: str) -> str:
    value = row["client_name"]
    if value is None or (isinstance(value, str) and not value.strip()):
        return f"待補姓名（{case_no}）"
    return _required_text(row, "client_name", 200)


def _required_text(row: Mapping[str, object], field: str, maximum_length: int) -> str:
    try:
        return require_canonical_text(row[field], field, maximum_length)
    except ValueError as exc:
        raise OrderSummaryContractError(str(exc)) from exc


def _optional_text(
    row: Mapping[str, object], field: str, maximum_length: int
) -> str | None:
    value = row[field]
    if value is None:
        return None
    return _required_text(row, field, maximum_length)


def _required_date(row: Mapping[str, object], field: str) -> date:
    value = row[field]
    if isinstance(value, datetime) or not isinstance(value, date):
        raise OrderSummaryContractError(f"{field} must be a date")
    return value


def _optional_date(row: Mapping[str, object], field: str) -> date | None:
    value = row[field]
    if value is None:
        return None
    return _required_date(row, field)


def _positive_integer(row: Mapping[str, object], field: str) -> int:
    try:
        return require_positive_integer(row[field], field)
    except ValueError as exc:
        raise OrderSummaryContractError(str(exc)) from exc


def _optional_positive_integer(
    row: Mapping[str, object], field: str
) -> int | None:
    return None if row[field] is None else _positive_integer(row, field)


def _optional_planned_service_days(row: Mapping[str, object]) -> int | None:
    service_days = row["service_days"]
    if service_days is None:
        return None
    if service_days == 0 and row["start_date"] is None:
        return None
    return _optional_positive_integer(row, "service_days")


def _nonnegative_ntd(row: Mapping[str, object], field: str) -> int:
    value = row[field]
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise OrderSummaryContractError(f"{field} must be integer NTD")
    if value < 0:
        raise OrderSummaryContractError(f"{field} must be integer NTD")
    if isinstance(value, Decimal) and value != value.to_integral_value():
        raise OrderSummaryContractError(f"{field} must be integer NTD")
    return int(value)


def _optional_nonnegative_ntd(
    row: Mapping[str, object], field: str
) -> int | None:
    return None if row[field] is None else _nonnegative_ntd(row, field)


def _validate_item_identity(items: tuple[OrderSummaryItem, ...]) -> None:
    case_numbers = tuple(item.case_no for item in items)
    if len(case_numbers) != len(set(case_numbers)):
        raise OrderSummaryContractError("repository page contains duplicate case numbers")


def _page_etag(items: tuple[OrderSummaryItem, ...], next_cursor: str | None) -> str:
    representation = {
        "items": [_item_representation(item) for item in items],
        "next_cursor": next_cursor,
    }
    encoded = json.dumps(
        representation, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _item_representation(item: OrderSummaryItem) -> dict[str, object]:
    return {
        "case_no": item.case_no,
        "client_name": item.client_name,
        "order_status": item.order_status,
        "staff_name": item.staff_name,
        "identity_status": item.identity_status,
        "start_date": _date_representation(item.start_date),
        "end_date": _date_representation(item.end_date),
        "actual_start_date": _date_representation(item.actual_start_date),
        "actual_end_date": _date_representation(item.actual_end_date),
        "service_days": item.service_days,
        "total_employer_self_pay_payable": item.total_employer_self_pay_payable,
    }


def _date_representation(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


__all__ = [
    "MAXIMUM_PAGE_SIZE",
    "OrderSummaryContractError",
    "OrderSummaryItem",
    "OrderSummaryPage",
    "OrderSummaryQueryRequest",
    "OrderSummaryQueryService",
    "OrderSummaryRepository",
]
