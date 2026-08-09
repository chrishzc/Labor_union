"""Pure eligibility and lifecycle candidate for controlled order reopening."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_CASE_NUMBER_MAXIMUM_LENGTH = 50
_FINANCIAL_IDENTITY_MAXIMUM_LENGTH = 191


class ReopenBlocker(StrEnum):
    NOT_CANCELLED = "order_reopen_requires_cancelled_order"
    FINANCIAL_HISTORY_EXISTS = "order_reopen_financial_history_exists"
    SERVICE_DATA_LOCKED = "service_data_locked"


class ReopenFinancialEventKind(StrEnum):
    CLIENT_REFUND = "client_refund"
    CLIENT_REVERSAL = "client_reversal"
    CLIENT_SETTLEMENT = "client_settlement"
    STAFF_PAYOUT = "staff_payout"
    STAFF_RETURN = "staff_return"
    STAFF_REVERSAL = "staff_reversal"


class ReopenCandidateError(ValueError):
    def __init__(self, blocker: ReopenBlocker) -> None:
        self.blocker = blocker
        super().__init__(blocker.value)


@dataclass(frozen=True, slots=True)
class ReopenFinancialEventFact:
    identity: str
    event_kind: ReopenFinancialEventKind

    def __post_init__(self) -> None:
        require_canonical_text(
            self.identity,
            "reopen financial event identity",
            _FINANCIAL_IDENTITY_MAXIMUM_LENGTH,
        )
        if not isinstance(self.event_kind, ReopenFinancialEventKind):
            raise TypeError("reopen financial event kind is invalid")


@dataclass(frozen=True, slots=True)
class ReopenOrderFacts:
    case_no: str
    order_version: int
    current_status: OrderLifecycleStatus
    cancellation_event_id: int
    cancellation_effective: bool
    contract_completed: bool
    deposit_settled: bool
    actual_start_date: date | None
    service_started: bool
    actual_start_reconfirmed: bool
    service_data_locked: bool

    def __post_init__(self) -> None:
        _validate_order_identity(self)
        _validate_order_booleans(self)
        _validate_actual_start(self)


@dataclass(frozen=True, slots=True)
class ReopenCandidate:
    case_no: str
    expected_order_version: int
    cancellation_event_id: int
    before_status: OrderLifecycleStatus
    after_status: OrderLifecycleStatus
    requires_fresh_scheduling_preview: bool
    restored_assignment_ids: tuple[int, ...]
    restored_schedule_ids: tuple[int, ...]
    restored_lock_ids: tuple[int, ...]
    fingerprint: PreviewFingerprint


def build_reopen_candidate(
    order: ReopenOrderFacts,
    financial_events: tuple[ReopenFinancialEventFact, ...],
) -> ReopenCandidate:
    _validate_financial_events(financial_events)
    _raise_if_ineligible(order, financial_events)
    after_status = _after_status(order)
    return _candidate(order, financial_events, after_status)


def _validate_order_identity(order) -> None:
    require_canonical_text(
        order.case_no,
        "case number",
        _CASE_NUMBER_MAXIMUM_LENGTH,
    )
    require_nonnegative_integer(order.order_version, "order version")
    require_positive_integer(
        order.cancellation_event_id,
        "cancellation event id",
    )
    if not isinstance(order.current_status, OrderLifecycleStatus):
        raise TypeError("current order status is invalid")


def _validate_order_booleans(order) -> None:
    values = (
        order.cancellation_effective,
        order.contract_completed,
        order.deposit_settled,
        order.service_started,
        order.actual_start_reconfirmed,
        order.service_data_locked,
    )
    if any(not isinstance(value, bool) for value in values):
        raise TypeError("reopen order boolean fact is invalid")


def _validate_actual_start(order) -> None:
    value = order.actual_start_date
    if value is not None and not _is_date(value):
        raise TypeError("actual start date must be a date")
    if order.service_started and value is None:
        raise ValueError("service start requires actual start date")
    if order.actual_start_reconfirmed and value is None:
        raise ValueError("actual start reconfirmation requires actual start date")


def _validate_financial_events(financial_events) -> None:
    if not isinstance(financial_events, tuple):
        raise TypeError("reopen financial events must be a tuple")
    if any(
        not isinstance(item, ReopenFinancialEventFact)
        for item in financial_events
    ):
        raise TypeError("reopen financial events contain an invalid value")
    identities = tuple(item.identity for item in financial_events)
    if identities != tuple(sorted(set(identities))):
        raise ValueError("reopen financial events must be sorted and unique")


def _raise_if_ineligible(order, financial_events) -> None:
    if (
        not order.cancellation_effective
        or order.current_status is not OrderLifecycleStatus.CANCELLED
    ):
        raise ReopenCandidateError(ReopenBlocker.NOT_CANCELLED)
    if order.service_data_locked:
        raise ReopenCandidateError(ReopenBlocker.SERVICE_DATA_LOCKED)
    if financial_events:
        raise ReopenCandidateError(
            ReopenBlocker.FINANCIAL_HISTORY_EXISTS
        )


def _after_status(order) -> OrderLifecycleStatus:
    if order.service_started:
        return OrderLifecycleStatus.IN_SERVICE
    if order.contract_completed and order.deposit_settled:
        return OrderLifecycleStatus.ESTABLISHED
    return OrderLifecycleStatus.DISCUSSION


def _candidate(order, financial_events, after_status):
    fingerprint = fingerprint_payload(
        _fingerprint_payload(order, financial_events, after_status)
    )
    return ReopenCandidate(
        order.case_no,
        order.order_version,
        order.cancellation_event_id,
        order.current_status,
        after_status,
        True,
        (),
        (),
        (),
        fingerprint,
    )


def _fingerprint_payload(order, financial_events, after_status):
    return {
        "actual_start_date": _optional_iso_date(order.actual_start_date),
        "actual_start_reconfirmed": order.actual_start_reconfirmed,
        "after_status": after_status.value,
        "cancellation_effective": order.cancellation_effective,
        "cancellation_event_id": order.cancellation_event_id,
        "case_no": order.case_no,
        "contract_completed": order.contract_completed,
        "deposit_settled": order.deposit_settled,
        "financial_events": tuple(
            (item.identity, item.event_kind.value)
            for item in financial_events
        ),
        "order_version": order.order_version,
        "service_data_locked": order.service_data_locked,
        "service_started": order.service_started,
    }


def _is_date(value) -> bool:
    return isinstance(value, date) and not isinstance(value, datetime)


def _optional_iso_date(value) -> str | None:
    return None if value is None else value.isoformat()


__all__ = [
    "ReopenBlocker",
    "ReopenCandidate",
    "ReopenCandidateError",
    "ReopenFinancialEventFact",
    "ReopenFinancialEventKind",
    "ReopenOrderFacts",
    "build_reopen_candidate",
]
