"""Validate the immutable facts used for an Orders lifecycle decision."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import Mapping
import re
from zoneinfo import ZoneInfo

CANONICAL_ORDER_STATUSES = frozenset({"洽談中", "訂單成立", "服務中", "訂單完成", "訂單取消"})
CANONICAL_LIFECYCLE_TRIGGERS = frozenset({"case_created", "schedule_applied", "deposit_reconciled", "deposit_reversed", "actual_start_updated", "actual_start_reconfirmed", "evaluation_time_reached", "cancelled", "hold_activated", "hold_released", "manual_correction"})
_REQUIRED_FACT_KEYS = frozenset({"cancellation", "cancellation_reason", "deposit_reconciled", "deposit_settlement_identity", "actual_start_date", "actual_end_date", "evaluation_at", "completion_instant", "completion_facts_consistent", "actual_start_reconfirmed", "transition_blockers", "manual_correction_target"})
_BOOLEAN_FACT_KEYS = ("cancellation", "deposit_reconciled", "completion_facts_consistent", "actual_start_reconfirmed")
_BLOCKER_SCOPES = frozenset({"enter_service", "auto_complete"})
_ISO_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_MACHINE_CODE_PATTERN = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*\Z")
_SETTLEMENT_IDENTITY_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_TAIPEI = ZoneInfo("Asia/Taipei")


@dataclass(frozen=True)
class ValidatedLifecycleFacts:
    cancellation: bool
    cancellation_reason: str | None
    deposit_reconciled: bool
    deposit_settlement_identity: str | None
    actual_start_date: date | None
    actual_end_date: date | None
    evaluation_at: datetime
    completion_instant: datetime | None
    completion_facts_consistent: bool
    actual_start_reconfirmed: bool
    transition_blockers: Mapping[str, tuple[str, ...]]
    manual_correction_target: str | None


@dataclass(frozen=True)
class OrderLifecycleFactsValidation:
    validated_status: str
    validated_trigger: str
    validated_facts: ValidatedLifecycleFacts


def _parse_iso_date(value: object, *, field_name: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _ISO_DATE_PATTERN.fullmatch(value):
        raise TypeError(f"{field_name} must be an ISO YYYY-MM-DD string or None")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field_name} must be a valid calendar date") from error


def _parse_aware_instant(value: object, *, field_name: str, nullable: bool) -> datetime | None:
    if value is None and nullable:
        return None
    suffix = " or None" if nullable else ""
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be an aware ISO datetime string{suffix}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field_name} must be a valid ISO datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a UTC offset")
    return parsed.astimezone(_TAIPEI)


def _normalize_transition_blockers(value: object) -> Mapping[str, tuple[str, ...]]:
    if not isinstance(value, Mapping) or set(value) != set(_BLOCKER_SCOPES):
        raise ValueError("transition_blockers must be an exact enter_service/auto_complete mapping")
    normalized: dict[str, tuple[str, ...]] = {}
    for scope in _BLOCKER_SCOPES:
        codes = value[scope]
        if not isinstance(codes, tuple):
            raise TypeError(f"transition_blockers.{scope} must be a tuple")
        for code in codes:
            if not isinstance(code, str):
                raise TypeError("transition blocker codes must be strings")
            if not _MACHINE_CODE_PATTERN.fullmatch(code):
                raise ValueError("transition blocker codes must be machine-readable codes")
        if codes != tuple(sorted(set(codes))):
            raise ValueError(f"transition_blockers.{scope} must be unique and stably sorted")
        normalized[scope] = codes
    return MappingProxyType(normalized)


def _normalize_settlement_identity(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("deposit_settlement_identity must be a string or None")
    if not _SETTLEMENT_IDENTITY_PATTERN.fullmatch(value):
        raise ValueError("deposit_settlement_identity must be a lowercase SHA-256 or None")
    return value


def validate_order_lifecycle_facts(current_status: str, trigger_event: str, authoritative_facts: Mapping[str, object]) -> OrderLifecycleFactsValidation:
    """Fail closed unless a lifecycle decision is based on the exact facts schema."""
    if current_status not in CANONICAL_ORDER_STATUSES:
        raise ValueError(f"unsupported current_status: {current_status!r}")
    if trigger_event not in CANONICAL_LIFECYCLE_TRIGGERS:
        raise ValueError(f"unsupported trigger_event: {trigger_event!r}")
    if not isinstance(authoritative_facts, Mapping):
        raise TypeError("authoritative_facts must be a mapping")
    supplied = frozenset(authoritative_facts)
    missing, unknown = _REQUIRED_FACT_KEYS - supplied, supplied - _REQUIRED_FACT_KEYS
    if missing:
        raise ValueError(f"authoritative_facts missing keys: {sorted(missing)!r}")
    if unknown:
        raise ValueError(f"authoritative_facts contains unknown keys: {sorted(unknown)!r}")
    for key in _BOOLEAN_FACT_KEYS:
        if type(authoritative_facts[key]) is not bool:
            raise TypeError(f"{key} must be bool")
    reason = authoritative_facts["cancellation_reason"]
    if authoritative_facts["cancellation"]:
        if not isinstance(reason, str) or not reason.strip() or reason != reason.strip():
            raise ValueError("cancellation_reason must be a non-empty canonical string when cancellation is active")
    elif reason is not None:
        raise ValueError("cancellation_reason must be None when cancellation is inactive")
    correction_target = authoritative_facts["manual_correction_target"]
    if correction_target is not None and correction_target not in CANONICAL_ORDER_STATUSES:
        raise ValueError("manual_correction_target must be a canonical status or None")
    if trigger_event == "manual_correction" and correction_target is None:
        raise ValueError("manual_correction requires manual_correction_target")
    if trigger_event != "manual_correction" and correction_target is not None:
        raise ValueError("manual_correction_target is only valid for manual_correction")
    facts = ValidatedLifecycleFacts(authoritative_facts["cancellation"], reason, authoritative_facts["deposit_reconciled"], _normalize_settlement_identity(authoritative_facts["deposit_settlement_identity"]), _parse_iso_date(authoritative_facts["actual_start_date"], field_name="actual_start_date"), _parse_iso_date(authoritative_facts["actual_end_date"], field_name="actual_end_date"), _parse_aware_instant(authoritative_facts["evaluation_at"], field_name="evaluation_at", nullable=False), _parse_aware_instant(authoritative_facts["completion_instant"], field_name="completion_instant", nullable=True), authoritative_facts["completion_facts_consistent"], authoritative_facts["actual_start_reconfirmed"], _normalize_transition_blockers(authoritative_facts["transition_blockers"]), correction_target)
    return OrderLifecycleFactsValidation(current_status, trigger_event, facts)
