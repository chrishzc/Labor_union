"""
File: card_projection_query.py
Description: 建立案件範圍的 Orders 卡片唯讀 typed projection。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Generic, Literal, Protocol, TypeVar

from shared_kernel.validation import require_canonical_text


MAXIMUM_ASSIGNMENT_SEGMENTS = 32
Availability = Literal["available", "unavailable", "blocked"]
T = TypeVar("T")


class OrdersCardProjectionContractError(ValueError):
    """The adapter returned facts outside the card projection contract."""


class OrdersCardProjectionNotFoundError(LookupError):
    """The requested case has no Orders root."""


@dataclass(frozen=True, slots=True)
class CardProjectionField(Generic[T]):
    value: T | None
    owner: str
    source_identity: str
    source_version: str | None
    availability: Availability
    availability_reason: str | None


@dataclass(frozen=True, slots=True)
class AssignmentSegmentProjection:
    assignment_id: CardProjectionField[int]
    staff_id: CardProjectionField[int]
    staff_name: CardProjectionField[str]
    sequence: CardProjectionField[int]
    assigned_start_date: CardProjectionField[date]
    assigned_end_date: CardProjectionField[date]
    status: CardProjectionField[str]


@dataclass(frozen=True, slots=True)
class OrdersCardProjection:
    case_no: str
    contact_phone: CardProjectionField[str]
    contact_address: CardProjectionField[str]
    requires_cooking: CardProjectionField[bool]
    floor_fee_ntd: CardProjectionField[int]
    deposit_amount_ntd: CardProjectionField[int]
    deposit_settlement_state: CardProjectionField[Literal["unsettled", "settled"]]
    deposit_settled_on: CardProjectionField[date]
    actual_start_date: CardProjectionField[date]
    actual_end_date: CardProjectionField[date]
    assignment_segments: CardProjectionField[tuple[AssignmentSegmentProjection, ...]]


class OrdersCardProjectionRepository(Protocol):
    def fetch_by_case_no(
        self, case_no: str
    ) -> tuple[Mapping[str, object], ...]: ...


class OrdersCardProjectionQueryService:
    """Translate one bounded repository read into a redacted typed card."""

    def __init__(self, repository: OrdersCardProjectionRepository) -> None:
        self._repository = repository

    def query(self, case_no: str) -> OrdersCardProjection:
        canonical_case_no = require_canonical_text(case_no, "case_no", 50)
        rows = self._repository.fetch_by_case_no(canonical_case_no)
        _validate_rows(rows)
        if not rows:
            raise OrdersCardProjectionNotFoundError(canonical_case_no)
        return _project(canonical_case_no, rows)


_ROW_FIELDS = frozenset(
    {
        "case_no",
        "client_id",
        "client_source_version",
        "phone",
        "address",
        "lifecycle_version",
        "requires_cooking",
        "floor_fee",
        "actual_start_date",
        "actual_end_date",
        "deposit_obligation_count",
        "deposit_amount_ntd",
        "deposit_obligation_identity",
        "deposit_obligation_status",
        "deposit_projection_state",
        "deposit_allocated_ntd",
        "deposit_source_version",
        "deposit_settled_on",
        "scheduling_version",
        "assignment_id",
        "assignment_staff_id",
        "assignment_sequence",
        "assigned_start_date",
        "assigned_end_date",
        "assignment_status",
        "staff_name",
        "staff_source_version",
    }
)


def _validate_rows(rows: object) -> None:
    if not isinstance(rows, tuple):
        raise OrdersCardProjectionContractError("repository rows must be a tuple")
    if len(rows) > MAXIMUM_ASSIGNMENT_SEGMENTS:
        raise OrdersCardProjectionContractError(
            "repository returned more than the bounded assignment slice"
        )
    for row in rows:
        if not isinstance(row, Mapping) or frozenset(row) != _ROW_FIELDS:
            raise OrdersCardProjectionContractError(
                "repository row fields are not canonical"
            )


def _project(
    case_no: str, rows: tuple[Mapping[str, object], ...]
) -> OrdersCardProjection:
    first = rows[0]
    for row in rows:
        if row["case_no"] != case_no:
            raise OrdersCardProjectionContractError("repository case identity drifted")

    client_id = _positive_int(first, "client_id")
    lifecycle_version = _nonnegative_int(first, "lifecycle_version")
    lifecycle_source = f"orders:{case_no}:lifecycle"
    order_version = str(lifecycle_version)
    client_source = f"client:{client_id}"
    client_version = _source_version(first["client_source_version"])

    assignment_rows = tuple(row for row in rows if row["assignment_id"] is not None)
    assignment_ids = tuple(_positive_int(row, "assignment_id") for row in assignment_rows)
    if len(assignment_ids) != len(set(assignment_ids)):
        raise OrdersCardProjectionContractError(
            "repository returned duplicate assignment identities"
        )
    segments = tuple(_assignment_segment(row) for row in assignment_rows)
    scheduling_version = _source_version(first["scheduling_version"])

    return OrdersCardProjection(
        case_no=case_no,
        contact_phone=_contact_phone(first, client_source, client_version),
        contact_address=_contact_address(first, client_source, client_version),
        requires_cooking=_requires_cooking(first, lifecycle_source, order_version),
        floor_fee_ntd=_floor_fee(first, lifecycle_source, order_version),
        deposit_amount_ntd=_deposit_amount(first),
        deposit_settlement_state=_deposit_state(first),
        deposit_settled_on=_deposit_settled_on(first),
        actual_start_date=_actual_date(
            first,
            "actual_start_date",
            lifecycle_source,
            order_version,
            "actual_start_not_confirmed",
        ),
        actual_end_date=_actual_date(
            first,
            "actual_end_date",
            lifecycle_source,
            order_version,
            "actual_end_not_recorded",
        ),
        assignment_segments=_assignment_segments(
            case_no, segments, scheduling_version
        ),
    )


def _contact_phone(
    row: Mapping[str, object], source_identity: str, source_version: str | None
) -> CardProjectionField[str]:
    raw = _optional_text(row, "phone", 20)
    value = None if raw is None else f"***{raw[-4:]}"
    return _field(
        value,
        "Client",
        source_identity,
        source_version,
        "client_phone_not_provided",
    )


def _contact_address(
    row: Mapping[str, object], source_identity: str, source_version: str | None
) -> CardProjectionField[str]:
    raw = _optional_text(row, "address", 255)
    value = None if raw is None else "地址已遮罩"
    return _field(
        value,
        "Client",
        source_identity,
        source_version,
        "client_address_not_provided",
    )


def _requires_cooking(
    row: Mapping[str, object], source_identity: str, source_version: str
) -> CardProjectionField[bool]:
    raw = row["requires_cooking"]
    if raw is None:
        return _unavailable(
            "Orders",
            source_identity,
            source_version,
            "orders_requires_cooking_unknown",
        )
    if isinstance(raw, bool):
        value = raw
    elif isinstance(raw, int) and raw in (0, 1):
        value = bool(raw)
    else:
        raise OrdersCardProjectionContractError("requires_cooking is not boolean")
    return _field(value, "Orders", source_identity, source_version, "")


def _floor_fee(
    row: Mapping[str, object], source_identity: str, source_version: str
) -> CardProjectionField[int]:
    raw = row["floor_fee"]
    if raw is None:
        return _unavailable(
            "Orders", source_identity, source_version, "floor_fee_not_provided"
        )
    try:
        value = Decimal(str(raw))
    except (ArithmeticError, ValueError) as error:
        raise OrdersCardProjectionContractError("floor_fee is not numeric") from error
    if value < 0 or value != value.to_integral_value():
        raise OrdersCardProjectionContractError("floor_fee must be integer NTD")
    return _field(int(value), "Orders", source_identity, source_version, "")


def _deposit_amount(row: Mapping[str, object]) -> CardProjectionField[int]:
    source_identity = _deposit_source_identity(row)
    source_version = _source_version(row["deposit_source_version"])
    count = _nonnegative_int(row, "deposit_obligation_count")
    if count == 0:
        return _unavailable(
            "Client Finance",
            source_identity,
            source_version,
            "deposit_obligation_missing",
        )
    if count != 1:
        return _blocked(
            "Client Finance",
            source_identity,
            source_version,
            "deposit_obligation_ambiguous",
        )
    raw = row["deposit_amount_ntd"]
    if raw is None:
        return _unavailable(
            "Client Finance",
            source_identity,
            source_version,
            "deposit_amount_missing",
        )
    value = _nonnegative_int(row, "deposit_amount_ntd")
    return _field(value, "Client Finance", source_identity, source_version, "")


def _deposit_state(
    row: Mapping[str, object],
) -> CardProjectionField[Literal["unsettled", "settled"]]:
    source_identity = _deposit_source_identity(row)
    source_version = _source_version(row["deposit_source_version"])
    if row["deposit_projection_state"] is None:
        return _unavailable(
            "Client Finance",
            source_identity,
            source_version,
            "deposit_settlement_projection_missing",
        )
    state = str(row["deposit_projection_state"])
    if state not in {"unsettled", "settled"}:
        raise OrdersCardProjectionContractError("deposit settlement state is invalid")
    return _field(state, "Client Finance", source_identity, source_version, "")


def _deposit_settled_on(row: Mapping[str, object]) -> CardProjectionField[date]:
    source_identity = _deposit_source_identity(row)
    source_version = _source_version(row["deposit_source_version"])
    state = row["deposit_projection_state"]
    if state != "settled":
        return _unavailable(
            "Client Finance",
            source_identity,
            source_version,
            "deposit_not_settled",
        )
    value = _optional_date(row, "deposit_settled_on")
    if value is None:
        return _unavailable(
            "Client Finance",
            source_identity,
            source_version,
            "deposit_settlement_date_missing",
        )
    return _field(value, "Client Finance", source_identity, source_version, "")


def _actual_date(
    row: Mapping[str, object],
    field_name: str,
    source_identity: str,
    source_version: str,
    missing_reason: str,
) -> CardProjectionField[date]:
    value = _optional_date(row, field_name)
    if value is None:
        return _unavailable("Orders", source_identity, source_version, missing_reason)
    return _field(value, "Orders", source_identity, source_version, "")


def _assignment_segment(row: Mapping[str, object]) -> AssignmentSegmentProjection:
    assignment_id = _positive_int(row, "assignment_id")
    source_identity = f"assignment:{assignment_id}"
    source_version = _source_version(row["scheduling_version"])
    return AssignmentSegmentProjection(
        assignment_id=_field(
            assignment_id,
            "Scheduling",
            source_identity,
            source_version,
            "",
        ),
        staff_id=_assignment_staff_id(row, source_identity, source_version),
        staff_name=_assignment_staff_name(row, source_identity),
        sequence=_assignment_sequence(row, source_identity, source_version),
        assigned_start_date=_assignment_date(
            row, "assigned_start_date", source_identity, source_version
        ),
        assigned_end_date=_assignment_date(
            row, "assigned_end_date", source_identity, source_version
        ),
        status=_assignment_status(row, source_identity, source_version),
    )


def _assignment_staff_id(
    row: Mapping[str, object], source_identity: str, source_version: str | None
) -> CardProjectionField[int]:
    raw = row["assignment_staff_id"]
    if raw is None:
        return _unavailable(
            "Scheduling", source_identity, source_version, "assignment_staff_missing"
        )
    return _field(
        _positive_int(row, "assignment_staff_id"),
        "Scheduling",
        source_identity,
        source_version,
        "",
    )


def _assignment_staff_name(
    row: Mapping[str, object], source_identity: str
) -> CardProjectionField[str]:
    value = _optional_text(row, "staff_name", 100)
    source_version = _source_version(row["staff_source_version"])
    return _field(
        value,
        "Staff",
        source_identity,
        source_version,
        "assignment_staff_name_missing",
    )


def _assignment_sequence(
    row: Mapping[str, object], source_identity: str, source_version: str | None
) -> CardProjectionField[int]:
    value = _positive_int(row, "assignment_sequence")
    return _field(value, "Scheduling", source_identity, source_version, "")


def _assignment_date(
    row: Mapping[str, object],
    field_name: str,
    source_identity: str,
    source_version: str | None,
) -> CardProjectionField[date]:
    value = _optional_date(row, field_name)
    return _field(
        value,
        "Scheduling",
        source_identity,
        source_version,
        "assignment_service_dates_incomplete",
    )


def _assignment_status(
    row: Mapping[str, object], source_identity: str, source_version: str | None
) -> CardProjectionField[str]:
    value = _required_text(row, "assignment_status", 20)
    return _field(value, "Scheduling", source_identity, source_version, "")


def _assignment_segments(
    case_no: str,
    segments: tuple[AssignmentSegmentProjection, ...],
    source_version: str | None,
) -> CardProjectionField[tuple[AssignmentSegmentProjection, ...]]:
    source_identity = f"scheduling:{case_no}:formal-assignments"
    if not segments:
        return _unavailable(
            "Scheduling",
            source_identity,
            source_version,
            "formal_assignment_segments_missing",
        )
    return _field(segments, "Scheduling", source_identity, source_version, "")


def _deposit_source_identity(row: Mapping[str, object]) -> str:
    identity = row["deposit_obligation_identity"]
    return (
        f"client-finance:deposit:{identity}"
        if identity is not None
        else "client-finance:deposit"
    )


def _field(
    value: T | None,
    owner: str,
    source_identity: str,
    source_version: str | None,
    missing_reason: str,
) -> CardProjectionField[T]:
    if value is None:
        return _unavailable(owner, source_identity, source_version, missing_reason)
    if source_version is None:
        return _blocked(owner, source_identity, source_version, "source_version_missing")
    return CardProjectionField(value, owner, source_identity, source_version, "available", None)


def _unavailable(
    owner: str,
    source_identity: str,
    source_version: str | None,
    reason: str,
) -> CardProjectionField[T]:
    return CardProjectionField(None, owner, source_identity, source_version, "unavailable", reason)


def _blocked(
    owner: str,
    source_identity: str,
    source_version: str | None,
    reason: str,
) -> CardProjectionField[T]:
    return CardProjectionField(None, owner, source_identity, source_version, "blocked", reason)


def _required_text(row: Mapping[str, object], field_name: str, maximum: int) -> str:
    value = row[field_name]
    try:
        return require_canonical_text(value, field_name, maximum)
    except ValueError as error:
        raise OrdersCardProjectionContractError(str(error)) from error


def _optional_text(row: Mapping[str, object], field_name: str, maximum: int) -> str | None:
    value = row[field_name]
    if value is None:
        return None
    try:
        return require_canonical_text(value, field_name, maximum)
    except ValueError as error:
        raise OrdersCardProjectionContractError(str(error)) from error


def _positive_int(row: Mapping[str, object], field_name: str) -> int:
    value = _nonnegative_int(row, field_name)
    if value <= 0:
        raise OrdersCardProjectionContractError(f"{field_name} must be positive")
    return value


def _nonnegative_int(row: Mapping[str, object], field_name: str) -> int:
    value = row[field_name]
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise OrdersCardProjectionContractError(f"{field_name} must be an integer")
    if value < 0 or isinstance(value, Decimal) and value != value.to_integral_value():
        raise OrdersCardProjectionContractError(f"{field_name} must be nonnegative integer")
    return int(value)


def _optional_date(row: Mapping[str, object], field_name: str) -> date | None:
    value = row[field_name]
    if value is None:
        return None
    if isinstance(value, datetime) or not isinstance(value, date):
        raise OrdersCardProjectionContractError(f"{field_name} must be a date or null")
    return value


def _source_version(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bool):
        raise OrdersCardProjectionContractError("source version must not be boolean")
    if isinstance(value, (int, str)):
        text = str(value).strip()
        return text or None
    raise OrdersCardProjectionContractError("source version has unsupported type")


__all__ = [
    "AssignmentSegmentProjection",
    "Availability",
    "CardProjectionField",
    "MAXIMUM_ASSIGNMENT_SEGMENTS",
    "OrdersCardProjection",
    "OrdersCardProjectionContractError",
    "OrdersCardProjectionNotFoundError",
    "OrdersCardProjectionQueryService",
    "OrdersCardProjectionRepository",
]
