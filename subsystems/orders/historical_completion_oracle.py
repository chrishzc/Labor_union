"""
File: historical_completion_oracle.py
Description: 依各 owner terminal readback 判定歷史訂單是否可完成。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Literal

from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer, require_positive_integer

_CASE_NUMBER_MAXIMUM_LENGTH = 50
_IDENTITY_MAXIMUM_LENGTH = 191
_BLOCKER_MAXIMUM_LENGTH = 191


class HistoricalCompletionState(StrEnum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"


class CompletionOwner(StrEnum):
    ORDERS = "orders"
    SCHEDULING = "scheduling"
    CLIENT_FINANCE = "client_finance"
    STAFF_PAYABLES = "staff_payables"


class CompletionReferral(StrEnum):
    ORDERS_COMPLETION = "orders.completion"
    ORDERS_ACTUAL_START = "orders.actual_start"
    SCHEDULING_SERVICE_FACTS = "scheduling.official_service_facts"
    CLIENT_SETTLEMENT = "client_finance.settlement"
    STAFF_PAYOUT = "staff_payables.payout"


class SettlementSourceKind(StrEnum):
    """Persisted Staff Payables roots whose versions form one case readback."""

    PAYROLL_CASE_ACCOUNT = "payroll_case_account"
    STAFF_OBLIGATION = "staff_obligation"
    STAFF_OBLIGATION_EVENT = "staff_obligation_event"
    STAFF_PAYABLE_ACCOUNT = "staff_payable_account"
    STAFF_PAYABLE_PROJECTION = "staff_payable_projection"
    STAFF_PAYOUT_EVENT = "staff_payout_event"
    STAFF_PAYOUT_RETURN_EVENT = "staff_payout_return_event"
    STAFF_PAYOUT_REVERSAL_EVENT = "staff_payout_reversal_event"
    STAFF_PAYOUT_ALLOCATION = "staff_payout_allocation"
    STAFF_BANK_FACT = "staff_bank_fact"
    STAFF_OVERPAYMENT_RECOVERY = "staff_overpayment_recovery"
    STAFF_OVERPAYMENT_RECOVERY_EVENT = "staff_overpayment_recovery_event"


@dataclass(frozen=True, slots=True, order=True)
class HistoricalSettlementSourceVersion:
    """One uncompressed persisted source identity and its current version."""

    kind: SettlementSourceKind
    identity: str
    version: int

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SettlementSourceKind):
            raise TypeError("settlement source kind is invalid")
        require_canonical_text(self.identity, "settlement source identity", _IDENTITY_MAXIMUM_LENGTH)
        require_nonnegative_integer(self.version, "settlement source version")


@dataclass(frozen=True, slots=True)
class HistoricalOrdersCompletionReadback:
    """Orders and Scheduling facts required before Step 11 can be terminal."""

    case_no: str
    lifecycle_version: int
    canonical_status: OrderLifecycleStatus
    completion_lineage_identity: str | None
    actual_start_date: date | None
    official_service_fact_identity: str | None
    official_service_dates: tuple[date, ...]
    required_service_day_count: int
    service_time_tuple_complete: bool
    readback_available: bool = True
    integrity_blockers: tuple[str, ...] = ()
    historical_service_day_count_identity: str | None = None
    historical_assignment_day_counts: tuple[tuple[str, int, int], ...] = ()

    def __post_init__(self) -> None:
        _case(self.case_no)
        require_nonnegative_integer(self.lifecycle_version, "Orders lifecycle version")
        if not isinstance(self.canonical_status, OrderLifecycleStatus):
            raise TypeError("Orders canonical status is invalid")
        _optional_identity(self.completion_lineage_identity, "completion lineage identity")
        _optional_identity(self.official_service_fact_identity, "official service fact identity")
        _optional_identity(
            self.historical_service_day_count_identity,
            "historical service day count identity",
        )
        if self.actual_start_date is not None and type(self.actual_start_date) is not date:
            raise TypeError("actual start date must be date or None")
        if not isinstance(self.official_service_dates, tuple):
            raise TypeError("official service dates must be a tuple")
        if any(type(value) is not date for value in self.official_service_dates):
            raise TypeError("official service dates must contain dates")
        if len(set(self.official_service_dates)) != len(self.official_service_dates):
            raise ValueError("official service dates must be unique")
        require_positive_integer(self.required_service_day_count, "required service day count")
        if type(self.service_time_tuple_complete) is not bool:
            raise TypeError("service time tuple completion must be boolean")
        if type(self.readback_available) is not bool:
            raise TypeError("Orders readback availability must be boolean")
        _blockers(self.integrity_blockers)
        if not isinstance(self.historical_assignment_day_counts, tuple):
            raise TypeError("historical assignment day counts must be a tuple")
        if any(
            not isinstance(item, tuple)
            or len(item) != 3
            or not isinstance(item[0], str)
            or not item[0].strip()
            or not isinstance(item[1], int)
            or isinstance(item[1], bool)
            or item[1] <= 0
            or not isinstance(item[2], int)
            or isinstance(item[2], bool)
            or item[2] <= 0
            for item in self.historical_assignment_day_counts
        ):
            raise ValueError("historical assignment day counts are invalid")
        if self.historical_assignment_day_counts != tuple(
            sorted(set(self.historical_assignment_day_counts))
        ):
            raise ValueError("historical assignment day counts must be sorted and unique")


@dataclass(frozen=True, slots=True)
class HistoricalSettlementReadback:
    """A typed, read-only terminal projection from one settlement owner."""

    case_no: str
    owner: Literal[CompletionOwner.CLIENT_FINANCE, CompletionOwner.STAFF_PAYABLES]
    aggregate_version: int | None
    settlement_lineage_identity: str | None
    obligation_count: int
    open_obligation_count: int
    allocation_lineage_identity: str | None
    source_versions: tuple[HistoricalSettlementSourceVersion, ...] = ()
    readback_available: bool = True
    integrity_blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _case(self.case_no)
        if not isinstance(self.owner, CompletionOwner) or self.owner not in {
            CompletionOwner.CLIENT_FINANCE,
            CompletionOwner.STAFF_PAYABLES,
        }:
            raise ValueError("settlement owner is not supported")
        if self.aggregate_version is not None:
            require_nonnegative_integer(self.aggregate_version, "settlement aggregate version")
        _optional_identity(self.settlement_lineage_identity, "settlement lineage identity")
        _optional_identity(self.allocation_lineage_identity, "allocation lineage identity")
        if not isinstance(self.source_versions, tuple):
            raise TypeError("settlement source versions must be a tuple")
        if any(not isinstance(item, HistoricalSettlementSourceVersion) for item in self.source_versions):
            raise TypeError("settlement source version is invalid")
        if tuple(sorted(self.source_versions)) != self.source_versions:
            raise ValueError("settlement source versions must be sorted")
        if len(set(self.source_versions)) != len(self.source_versions):
            raise ValueError("settlement source versions must be unique")
        identities = tuple((item.kind, item.identity) for item in self.source_versions)
        if len(set(identities)) != len(identities):
            raise ValueError("settlement source identities must be unique")
        if self.owner is CompletionOwner.CLIENT_FINANCE and self.source_versions:
            raise ValueError("Client Finance must use its aggregate version")
        if self.owner is CompletionOwner.STAFF_PAYABLES and self.aggregate_version is not None:
            raise ValueError("Staff Payables must use source versions instead of one aggregate version")
        require_nonnegative_integer(self.obligation_count, "obligation count")
        require_nonnegative_integer(self.open_obligation_count, "open obligation count")
        if self.open_obligation_count > self.obligation_count:
            raise ValueError("open obligations exceed obligations")
        if type(self.readback_available) is not bool:
            raise TypeError("settlement readback availability must be boolean")
        _blockers(self.integrity_blockers)


@dataclass(frozen=True, slots=True)
class HistoricalCompletionFacts:
    """The cross-domain read composition supplied to the pure completion oracle."""

    case_no: str
    orders: HistoricalOrdersCompletionReadback
    client_finance: HistoricalSettlementReadback
    staff_payables: HistoricalSettlementReadback

    def __post_init__(self) -> None:
        _case(self.case_no)
        if not isinstance(self.orders, HistoricalOrdersCompletionReadback):
            raise TypeError("Orders completion readback is invalid")
        if not isinstance(self.client_finance, HistoricalSettlementReadback):
            raise TypeError("Client Finance completion readback is invalid")
        if not isinstance(self.staff_payables, HistoricalSettlementReadback):
            raise TypeError("Staff Payables completion readback is invalid")
        if self.orders.case_no != self.case_no:
            raise ValueError("Orders case identity does not match completion case")
        if self.client_finance.case_no != self.case_no:
            raise ValueError("Client Finance case identity does not match completion case")
        if self.staff_payables.case_no != self.case_no:
            raise ValueError("Staff Payables case identity does not match completion case")
        if self.client_finance.owner is not CompletionOwner.CLIENT_FINANCE:
            raise ValueError("Client Finance readback owner is invalid")
        if self.staff_payables.owner is not CompletionOwner.STAFF_PAYABLES:
            raise ValueError("Staff Payables readback owner is invalid")


@dataclass(frozen=True, slots=True)
class CompletionMissingRoot:
    code: str
    owner: CompletionOwner
    field_path: str
    referral: CompletionReferral
    message: str

    def __post_init__(self) -> None:
        for value, label, maximum in (
            (self.code, "completion blocker code", _IDENTITY_MAXIMUM_LENGTH),
            (self.field_path, "completion blocker field path", _IDENTITY_MAXIMUM_LENGTH),
            (self.message, "completion blocker message", _BLOCKER_MAXIMUM_LENGTH),
        ):
            require_canonical_text(value, label, maximum)
        if not isinstance(self.owner, CompletionOwner):
            raise TypeError("completion blocker owner is invalid")
        if not isinstance(self.referral, CompletionReferral):
            raise TypeError("completion blocker referral is invalid")


@dataclass(frozen=True, slots=True)
class HistoricalCompletionOracleResult:
    case_no: str
    state: HistoricalCompletionState
    missing_roots: tuple[CompletionMissingRoot, ...]
    owner_versions: tuple[tuple[str, int], ...]
    owner_source_versions: tuple[HistoricalSettlementSourceVersion, ...]
    orders_readback: HistoricalOrdersCompletionReadback
    settlement_readbacks: tuple[HistoricalSettlementReadback, ...]
    fingerprint: PreviewFingerprint

    @property
    def step_11_completed(self) -> bool:
        return self.state is HistoricalCompletionState.COMPLETED

    def __post_init__(self) -> None:
        _case(self.case_no)
        if not isinstance(self.state, HistoricalCompletionState):
            raise TypeError("completion state is invalid")
        if not isinstance(self.missing_roots, tuple):
            raise TypeError("completion missing roots must be a tuple")
        if not isinstance(self.orders_readback, HistoricalOrdersCompletionReadback):
            raise TypeError("completion Orders readback is invalid")
        if not isinstance(self.settlement_readbacks, tuple) or len(self.settlement_readbacks) != 2:
            raise TypeError("completion settlement readbacks are invalid")
        if not isinstance(self.fingerprint, PreviewFingerprint):
            raise TypeError("completion fingerprint is invalid")
        if self.fingerprint != fingerprint_payload(self.canonical_payload):
            raise ValueError("completion fingerprint mismatch")

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "case_no": self.case_no,
            "state": self.state.value,
            "missing_roots": tuple(
                {
                    "code": item.code,
                    "owner": item.owner.value,
                    "field_path": item.field_path,
                    "referral": item.referral.value,
                    "message": item.message,
                }
                for item in self.missing_roots
            ),
            "owner_versions": self.owner_versions,
            "owner_source_versions": tuple(
                {"kind": item.kind.value, "identity": item.identity, "version": item.version}
                for item in self.owner_source_versions
            ),
            "orders_readback": _orders_payload(self.orders_readback),
            "settlement_readbacks": tuple(_settlement_payload(item) for item in self.settlement_readbacks),
        }


def evaluate_historical_completion(facts: HistoricalCompletionFacts) -> HistoricalCompletionOracleResult:
    """Evaluate Step 11 without status-only shortcuts or cross-domain writes."""

    if not isinstance(facts, HistoricalCompletionFacts):
        raise TypeError("historical completion facts are invalid")
    missing: list[CompletionMissingRoot] = []
    _check_orders(missing, facts.orders)
    _check_settlement(missing, facts.client_finance)
    _check_settlement(missing, facts.staff_payables)
    missing_roots = tuple(sorted(missing, key=lambda item: (item.owner.value, item.field_path, item.code)))
    unavailable = any(
        item.code.endswith("readback_unavailable") for item in missing_roots
    )
    state = (
        HistoricalCompletionState.UNAVAILABLE
        if unavailable
        else HistoricalCompletionState.COMPLETED
        if not missing_roots
        else HistoricalCompletionState.BLOCKED
    )
    owner_versions = tuple(
        (owner, version)
        for owner, version in (
            (CompletionOwner.ORDERS.value, facts.orders.lifecycle_version),
            (CompletionOwner.CLIENT_FINANCE.value, facts.client_finance.aggregate_version),
        )
        if version is not None
    )
    owner_source_versions = facts.staff_payables.source_versions
    settlement_readbacks = (facts.client_finance, facts.staff_payables)
    payload = {
        "case_no": facts.case_no,
        "state": state.value,
        "missing_roots": tuple(
            {
                "code": item.code,
                "owner": item.owner.value,
                "field_path": item.field_path,
                "referral": item.referral.value,
                "message": item.message,
            }
            for item in missing_roots
        ),
        "owner_versions": owner_versions,
        "owner_source_versions": tuple(
            {"kind": item.kind.value, "identity": item.identity, "version": item.version}
            for item in owner_source_versions
        ),
        "orders_readback": _orders_payload(facts.orders),
        "settlement_readbacks": tuple(_settlement_payload(item) for item in settlement_readbacks),
    }
    return HistoricalCompletionOracleResult(
        facts.case_no,
        state,
        missing_roots,
        owner_versions,
        owner_source_versions,
        facts.orders,
        settlement_readbacks,
        fingerprint_payload(payload),
    )


def _check_orders(missing: list[CompletionMissingRoot], facts: HistoricalOrdersCompletionReadback) -> None:
    if not facts.readback_available:
        _add(missing, "orders_readback_unavailable", CompletionOwner.ORDERS, "orders.readback", CompletionReferral.ORDERS_COMPLETION, "Orders completion root currently unavailable")
        return
    historical_count_path = facts.canonical_status in {
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
    }
    if facts.canonical_status not in {
        OrderLifecycleStatus.COMPLETED,
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
    }:
        _add(missing, "orders_completion_not_terminal", CompletionOwner.ORDERS, "orders.canonical_status", CompletionReferral.ORDERS_COMPLETION, "Orders completion lineage is not terminal")
    if facts.completion_lineage_identity is None:
        _add(missing, "orders_completion_lineage_missing", CompletionOwner.ORDERS, "orders.completion_lineage_identity", CompletionReferral.ORDERS_COMPLETION, "Canonical Orders completion lineage is missing")
    if facts.actual_start_date is None:
        _add(missing, "orders_actual_start_missing", CompletionOwner.ORDERS, "orders.actual_start_date", CompletionReferral.ORDERS_ACTUAL_START, "Actual service start date is missing")
    if historical_count_path:
        if facts.historical_service_day_count_identity is None:
            _add(missing, "historical_actual_service_days_required", CompletionOwner.ORDERS, "orders.historical_service_day_count_identity", CompletionReferral.ORDERS_COMPLETION, "Historical actual service day counts are missing")
        if not facts.historical_assignment_day_counts:
            _add(missing, "historical_actual_service_days_assignment_mismatch", CompletionOwner.ORDERS, "orders.historical_assignment_day_counts", CompletionReferral.ORDERS_COMPLETION, "Historical assignment day counts are incomplete")
    else:
        if facts.official_service_fact_identity is None:
            _add(missing, "scheduling_service_facts_missing", CompletionOwner.SCHEDULING, "scheduling.official_service_fact_identity", CompletionReferral.SCHEDULING_SERVICE_FACTS, "Assignment-owned official service facts are missing")
        if len(facts.official_service_dates) != facts.required_service_day_count:
            _add(missing, "scheduling_service_dates_incomplete", CompletionOwner.SCHEDULING, "scheduling.official_service_dates", CompletionReferral.SCHEDULING_SERVICE_FACTS, "Official service dates do not cover the required service days")
        if not facts.service_time_tuple_complete:
            _add(missing, "scheduling_service_time_missing", CompletionOwner.SCHEDULING, "scheduling.service_time_tuple", CompletionReferral.SCHEDULING_SERVICE_FACTS, "Required service-time tuple is incomplete")
    for blocker in facts.integrity_blockers:
        if blocker.startswith("scheduling.") or blocker.startswith("scheduling_"):
            _add(missing, _integrity_code("scheduling", blocker), CompletionOwner.SCHEDULING, "scheduling.integrity", CompletionReferral.SCHEDULING_SERVICE_FACTS, _integrity_message("Scheduling service facts", blocker))
        else:
            _add(missing, _integrity_code("orders", blocker), CompletionOwner.ORDERS, "orders.integrity", CompletionReferral.ORDERS_COMPLETION, _integrity_message("Orders completion", blocker))


def _check_settlement(missing: list[CompletionMissingRoot], facts: HistoricalSettlementReadback) -> None:
    owner_label = "Client Finance" if facts.owner is CompletionOwner.CLIENT_FINANCE else "Staff Payables"
    referral = CompletionReferral.CLIENT_SETTLEMENT if facts.owner is CompletionOwner.CLIENT_FINANCE else CompletionReferral.STAFF_PAYOUT
    prefix = facts.owner.value
    if not facts.readback_available:
        _add(missing, f"{prefix}_readback_unavailable", facts.owner, f"{prefix}.readback", referral, f"{owner_label} terminal projection currently unavailable")
    if facts.owner is CompletionOwner.CLIENT_FINANCE and facts.aggregate_version is None:
        _add(missing, f"{prefix}_version_missing", facts.owner, f"{prefix}.aggregate_version", referral, f"{owner_label} aggregate version is missing")
    if facts.owner is CompletionOwner.STAFF_PAYABLES and not facts.source_versions:
        _add(missing, f"{prefix}_source_versions_missing", facts.owner, f"{prefix}.source_versions", referral, f"{owner_label} source version vector is missing")
    if facts.owner is CompletionOwner.STAFF_PAYABLES and facts.readback_available:
        required_kinds = {
            SettlementSourceKind.PAYROLL_CASE_ACCOUNT,
            SettlementSourceKind.STAFF_OBLIGATION,
            SettlementSourceKind.STAFF_OBLIGATION_EVENT,
            SettlementSourceKind.STAFF_PAYABLE_ACCOUNT,
            SettlementSourceKind.STAFF_PAYABLE_PROJECTION,
            SettlementSourceKind.STAFF_PAYOUT_EVENT,
            SettlementSourceKind.STAFF_PAYOUT_ALLOCATION,
            SettlementSourceKind.STAFF_BANK_FACT,
        }
        present_kinds = {item.kind for item in facts.source_versions}
        if not required_kinds.issubset(present_kinds):
            _add(missing, f"{prefix}_source_vector_readback_unavailable", facts.owner, f"{prefix}.source_versions", referral, f"{owner_label} source version vector is incomplete")
        recovery_events = {
            item.identity for item in facts.source_versions
            if item.kind is SettlementSourceKind.STAFF_OVERPAYMENT_RECOVERY_EVENT
        }
        for recovery in (
            item for item in facts.source_versions
            if item.kind is SettlementSourceKind.STAFF_OVERPAYMENT_RECOVERY and item.version > 0
        ):
            if not any(identity.startswith(f"{recovery.identity}:") for identity in recovery_events):
                _add(missing, f"{prefix}_recovery_event_readback_unavailable", facts.owner, f"{prefix}.source_versions", referral, f"{owner_label} recovery event lineage is incomplete")
    if facts.settlement_lineage_identity is None:
        _add(missing, f"{prefix}_settlement_lineage_missing", facts.owner, f"{prefix}.settlement_lineage_identity", referral, f"{owner_label} settlement lineage is missing")
    if facts.open_obligation_count:
        _add(missing, f"{prefix}_settlement_open", facts.owner, f"{prefix}.open_obligation_count", referral, f"{owner_label} has unsettled obligations")
    if facts.allocation_lineage_identity is None:
        _add(missing, f"{prefix}_allocation_lineage_missing", facts.owner, f"{prefix}.allocation_lineage_identity", referral, f"{owner_label} bank/allocation lineage is missing")
    for blocker in facts.integrity_blockers:
        _add(missing, _integrity_code(prefix, blocker), facts.owner, f"{prefix}.integrity", referral, _integrity_message(owner_label, blocker))


def _integrity_code(prefix: str, blocker: str) -> str:
    candidate = f"{prefix}_integrity_blocked:{blocker}"
    if len(candidate) <= _BLOCKER_MAXIMUM_LENGTH:
        return candidate
    digest = fingerprint_payload({"integrity_blocker": blocker}).value
    return f"{prefix}_integrity_blocked:{digest}"


def _integrity_message(owner_label: str, blocker: str) -> str:
    candidate = f"{owner_label} integrity blocker: {blocker}"
    if len(candidate) <= _BLOCKER_MAXIMUM_LENGTH:
        return candidate
    digest = fingerprint_payload({"integrity_blocker": blocker}).value
    return f"{owner_label} integrity blocker fingerprint: {digest}"


def _add(missing, code, owner, field_path, referral, message):
    missing.append(CompletionMissingRoot(code, owner, field_path, referral, message))


def _case(value: str) -> None:
    require_canonical_text(value, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)


def _optional_identity(value: str | None, label: str) -> None:
    if value is not None:
        require_canonical_text(value, label, _IDENTITY_MAXIMUM_LENGTH)


def _blockers(values: tuple[str, ...]) -> None:
    if not isinstance(values, tuple):
        raise TypeError("integrity blockers must be a tuple")
    for value in values:
        require_canonical_text(value, "integrity blocker", _BLOCKER_MAXIMUM_LENGTH)


def _settlement_payload(item: HistoricalSettlementReadback) -> dict[str, object]:
    return {
        "owner": item.owner.value,
        "aggregate_version": item.aggregate_version,
        "settlement_lineage_identity": item.settlement_lineage_identity,
        "obligation_count": item.obligation_count,
        "open_obligation_count": item.open_obligation_count,
        "allocation_lineage_identity": item.allocation_lineage_identity,
        "readback_available": item.readback_available,
        "integrity_blockers": item.integrity_blockers,
        "source_versions": tuple(
            (source.kind.value, source.identity, source.version)
            for source in item.source_versions
        ),
    }


def _orders_payload(item: HistoricalOrdersCompletionReadback) -> dict[str, object]:
    return {
        "case_no": item.case_no,
        "lifecycle_version": item.lifecycle_version,
        "canonical_status": item.canonical_status.value,
        "completion_lineage_identity": item.completion_lineage_identity,
        "actual_start_date": item.actual_start_date.isoformat() if item.actual_start_date is not None else None,
        "official_service_fact_identity": item.official_service_fact_identity,
        "official_service_dates": tuple(value.isoformat() for value in item.official_service_dates),
        "required_service_day_count": item.required_service_day_count,
        "service_time_tuple_complete": item.service_time_tuple_complete,
        "historical_service_day_count_identity": item.historical_service_day_count_identity,
        "historical_assignment_day_counts": item.historical_assignment_day_counts,
        "readback_available": item.readback_available,
        "integrity_blockers": item.integrity_blockers,
    }


__all__ = [
    "CompletionOwner",
    "CompletionReferral",
    "CompletionMissingRoot",
    "HistoricalCompletionFacts",
    "HistoricalCompletionOracleResult",
    "HistoricalCompletionState",
    "HistoricalOrdersCompletionReadback",
    "HistoricalSettlementReadback",
    "HistoricalSettlementSourceVersion",
    "SettlementSourceKind",
    "evaluate_historical_completion",
]
