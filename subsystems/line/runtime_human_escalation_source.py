"""File: runtime_human_escalation_source.py
Description: M4 canonical source normalization、complaint.v1 與 runtime allowlist。
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Iterable, Mapping

from domains.customer_service.escalation import HumanEscalationDomainError, TriggerCode, evidence_digest


COMPLAINT_POLICY_VERSION = "complaint.v1"
COMPLAINT_V1_CATALOG = frozenset({"客訴", "投訴", "投诉", "申訴", "申诉"})
COMPLAINT_V1_PREFIXES = frozenset(
    {
        "我要客訴", "我要投訴", "我要投诉", "我要申訴", "我要申诉",
        "提出客訴", "提出投訴", "提出投诉", "提出申訴", "提出申诉",
    }
)
# First release accepts exactly one component/scope pair.  A capability alone
# is insufficient because another runtime component must not create a global
# Customer Service hold by reusing the LINE delivery scope.
RUNTIME_CRITICAL_CAPABILITY_ALLOWLIST = frozenset(
    {("LINE Worker", "line_delivery")}
)


class HumanEscalationSourceError(ValueError):
    """Canonical source is unknown, ambiguous, or fails a closed allowlist."""

    def __init__(self, code: str) -> None:
        super().__init__("M4 escalation source is not accepted")
        self.code = code


@dataclass(frozen=True, slots=True)
class BindingFailureEvent:
    flow_scope: str
    subject_scope: str
    event_identity: str
    sequence: int
    fingerprint: str
    success: bool = False

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                self.flow_scope,
                self.subject_scope,
                self.event_identity,
                self.fingerprint,
            )
        ):
            raise HumanEscalationSourceError("human_escalation_source_invalid")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 1:
            raise HumanEscalationSourceError("human_escalation_source_invalid")


@dataclass(frozen=True, slots=True)
class RuntimeCriticalSource:
    event_identity: str
    source_fingerprint: str
    capability_scope: str
    component: str


def binding_failure_threshold_2(events: Iterable[BindingFailureEvent]) -> bool:
    """Return true only for two adjacent failures in one flow/subject sequence."""
    values = tuple(events)
    if len(values) < 2:
        return False
    ordered = sorted(values, key=lambda event: event.sequence)
    if len({event.event_identity for event in ordered}) != len(ordered):
        raise HumanEscalationSourceError("human_escalation_source_conflict")
    if any(event.flow_scope != ordered[0].flow_scope or event.subject_scope != ordered[0].subject_scope for event in ordered):
        return False
    last_success_index = max(
        (index for index, event in enumerate(ordered) if event.success),
        default=-1,
    )
    eligible = ordered[last_success_index + 1 :]
    if len(eligible) < 2:
        return False
    first, second = eligible[-2:]
    return (
        second.sequence == first.sequence + 1
        and not first.success
        and not second.success
    )


def normalize_complaint_text(text: str) -> dict[str, str] | None:
    if not isinstance(text, str):
        raise HumanEscalationSourceError("human_escalation_source_invalid")
    normalized = " ".join(unicodedata.normalize("NFKC", text).split())
    if normalized not in COMPLAINT_V1_CATALOG and not any(
        normalized.startswith(prefix) for prefix in COMPLAINT_V1_PREFIXES
    ):
        return None
    return {
        "summary_code": "complaint_explicit",
        "policy_version": COMPLAINT_POLICY_VERSION,
        "category": "other",
        "redaction_version": "m4-mask.v1",
    }


def validate_complaint_code(code: str) -> str:
    # Retain a small compatibility helper, but never accept guessed urgency or
    # safety labels.  All accepted complaint events are category=other.
    if code not in COMPLAINT_V1_CATALOG:
        raise HumanEscalationSourceError("human_escalation_source_invalid")
    return "other"


def normalize_runtime_critical(
    event: Mapping[str, object],
    *,
    capability_allowlist: frozenset[tuple[str, str]] = RUNTIME_CRITICAL_CAPABILITY_ALLOWLIST,
) -> RuntimeCriticalSource:
    """Normalize only submitted critical runtime facts; unknown capability fails closed."""
    if not isinstance(event, Mapping):
        raise HumanEscalationSourceError("human_escalation_source_invalid")
    allowed_fields = {"event_identity", "resulting_status", "component", "capability_scope", "source_payload"}
    if set(event) - allowed_fields:
        raise HumanEscalationSourceError("human_escalation_source_invalid")
    identity = event.get("event_identity")
    status = event.get("resulting_status")
    component = event.get("component")
    capability = event.get("capability_scope")
    if not all(isinstance(value, str) and value.strip() for value in (identity, component, capability)) or status != "critical":
        raise HumanEscalationSourceError("human_escalation_source_invalid")
    if (component, capability) not in capability_allowlist:
        raise HumanEscalationSourceError("human_escalation_source_invalid")
    payload = event.get("source_payload", {"event_identity": identity, "component": component, "capability_scope": capability, "resulting_status": status})
    if not isinstance(payload, Mapping):
        raise HumanEscalationSourceError("human_escalation_source_invalid")
    return RuntimeCriticalSource(identity, evidence_digest(payload), capability, component)


def canonical_binding_trigger(events: Iterable[BindingFailureEvent]) -> tuple[TriggerCode, str] | None:
    return (TriggerCode.BINDING_FAILURE_THRESHOLD_2, "identity.v1") if binding_failure_threshold_2(events) else None


__all__ = [
    "BindingFailureEvent", "COMPLAINT_POLICY_VERSION", "COMPLAINT_V1_CATALOG",
    "COMPLAINT_V1_PREFIXES", "HumanEscalationSourceError", "RUNTIME_CRITICAL_CAPABILITY_ALLOWLIST",
    "RuntimeCriticalSource", "binding_failure_threshold_2", "canonical_binding_trigger",
    "normalize_complaint_text", "normalize_runtime_critical", "validate_complaint_code",
]
