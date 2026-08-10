"""Pure Client Finance decisions for deposit receipt and reversal effects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_canonical_text


class DepositLifecycleEvent(StrEnum):
    RECEIPT = "deposit_reconciled"
    REVERSAL = "deposit_reversed"


@dataclass(frozen=True, slots=True)
class DepositLifecycleFacts:
    case_no: str
    event: DepositLifecycleEvent
    deposit_settled: bool
    settlement_identity: PreviewFingerprint | None
    actual_start_exists: bool
    service_started: bool
    service_completed: bool
    confirmed_settlement_identity: PreviewFingerprint | None

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        if not isinstance(self.event, DepositLifecycleEvent):
            raise TypeError("deposit lifecycle event is invalid")
        if self.deposit_settled != (self.settlement_identity is not None):
            raise ValueError("deposit settlement identity is inconsistent")
        if self.service_completed and not self.service_started:
            raise ValueError("completed service must have started")
        if self.confirmed_settlement_identity and not self.actual_start_exists:
            raise ValueError("actual-start confirmation requires an actual start")


@dataclass(frozen=True, slots=True)
class DepositLifecycleImpact:
    lifecycle_intent: DepositLifecycleEvent
    block_enter_service: bool
    preserve_service_state: bool
    require_actual_start_reconfirmation: bool
    anomaly_code: str | None
    fingerprint: PreviewFingerprint


def decide_deposit_lifecycle_impact(
    facts: DepositLifecycleFacts,
) -> DepositLifecycleImpact:
    """Decide lifecycle effect without changing Finance, Orders, or Scheduling."""
    _validate_event_matches_settlement(facts)
    service_state_is_fixed = facts.service_started or facts.service_completed
    confirmation_is_stale = _confirmation_is_stale(facts)
    return _impact(
        facts,
        block_enter_service=not service_state_is_fixed and not facts.deposit_settled,
        preserve_service_state=service_state_is_fixed,
        require_reconfirmation=confirmation_is_stale,
        anomaly_code=_anomaly_code(facts, service_state_is_fixed),
    )


def _validate_event_matches_settlement(facts: DepositLifecycleFacts) -> None:
    if facts.event is DepositLifecycleEvent.RECEIPT and not facts.deposit_settled:
        raise ValueError("deposit receipt must settle the deposit")
    if facts.event is DepositLifecycleEvent.REVERSAL and facts.deposit_settled:
        raise ValueError("deposit reversal must leave the deposit unsettled")


def _confirmation_is_stale(facts: DepositLifecycleFacts) -> bool:
    if not facts.actual_start_exists or not facts.deposit_settled:
        return False
    if facts.confirmed_settlement_identity is None:
        return facts.deposit_settled
    return facts.confirmed_settlement_identity != facts.settlement_identity


def _anomaly_code(
    facts: DepositLifecycleFacts,
    service_state_is_fixed: bool,
) -> str | None:
    if facts.event is DepositLifecycleEvent.REVERSAL and service_state_is_fixed:
        return "finance.deposit_reversal_after_service_started"
    return None


def _impact(
    facts: DepositLifecycleFacts,
    *,
    block_enter_service: bool,
    preserve_service_state: bool,
    require_reconfirmation: bool,
    anomaly_code: str | None,
) -> DepositLifecycleImpact:
    fingerprint = fingerprint_payload(
        {
            "case_no": facts.case_no,
            "event": facts.event.value,
            "deposit_settled": facts.deposit_settled,
            "settlement_identity": _identity_value(facts.settlement_identity),
            "actual_start_exists": facts.actual_start_exists,
            "service_started": facts.service_started,
            "service_completed": facts.service_completed,
            "confirmed_settlement_identity": _identity_value(
                facts.confirmed_settlement_identity
            ),
            "block_enter_service": block_enter_service,
            "preserve_service_state": preserve_service_state,
            "require_actual_start_reconfirmation": require_reconfirmation,
            "anomaly_code": anomaly_code,
        }
    )
    return DepositLifecycleImpact(
        facts.event,
        block_enter_service,
        preserve_service_state,
        require_reconfirmation,
        anomaly_code,
        fingerprint,
    )


def _identity_value(value: PreviewFingerprint | None) -> str | None:
    return None if value is None else value.value
