"""File: escalation.py
Description: M4 客服 HIGH escalation、bounded hold 與閉合狀態規則。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import re
from typing import Mapping

from domains.customer_service.ticket import CustomerServiceCategory


_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SAFE = re.compile(r"^[^\r\n\x00]{1,500}$")
_CODE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_PHONE = re.compile(r"(?<!\d)(?:\+?886[- ]?)?09\d{2}[- ]?\d{3}[- ]?\d{3}(?!\d)")
_EMAIL = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_LINE_USER_ID = re.compile(r"\bU[0-9a-fA-F]{20,64}\b")
_SENSITIVE_KEY_PARTS = ("line", "phone", "name", "raw", "message", "provider", "schedul", "token")


class TriggerCode(StrEnum):
    EXPLICIT_HUMAN_REQUEST = "explicit_human_request"
    EXPLICIT_WRONG_ANSWER = "explicit_wrong_answer"
    BINDING_FAILURE_THRESHOLD_2 = "binding_failure_threshold_2"
    COMPLAINT = "complaint"
    RUNTIME_CRITICAL = "runtime_critical"


class EscalationWorkflowStatus(StrEnum):
    OPEN = "open"
    CLAIMED = "claimed"
    HANDLING = "handling"
    RESOLVED = "resolved"


class AutomationHoldState(StrEnum):
    ACTIVE = "active"
    RELEASED = "released"


class AlertStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    UNKNOWN = "unknown"


class EscalationEventType(StrEnum):
    CREATED = "created"
    CLAIMED = "claimed"
    HANDLING_STARTED = "handling_started"
    RESOLVED = "resolved"
    HOLD_RELEASED = "hold_released"


class HumanEscalationDomainError(ValueError):
    """M4 domain validation failure; callers map it to a typed error."""

    def __init__(self, code: str, message: str = "客服 escalation 資料不符合契約") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class EscalationContext:
    """Closed complaint.v1 payload; raw source text and identity never enter the domain."""

    summary_code: str
    policy_version: str
    category: str
    redaction_version: str

    def __post_init__(self) -> None:
        for value, name, maximum in (
            (self.summary_code, "summary_code", 128),
            (self.policy_version, "policy_version", 128),
            (self.category, "category", 40),
            (self.redaction_version, "redaction_version", 64),
        ):
            _safe(value, name, maximum)
        if not all(_CODE.fullmatch(value) for value in (self.summary_code, self.policy_version, self.redaction_version)):
            raise HumanEscalationDomainError("human_escalation_redaction_failed")
        _reject_sensitive(
            ("summary_code", self.summary_code),
            ("policy_version", self.policy_version),
            ("category", self.category),
            ("redaction_version", self.redaction_version),
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "summary_code": self.summary_code,
            "policy_version": self.policy_version,
            "category": self.category,
            "redaction_version": self.redaction_version,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "EscalationContext":
        if not isinstance(value, Mapping):
            raise HumanEscalationDomainError("human_escalation_redaction_failed")
        allowed = {"summary_code", "policy_version", "category", "redaction_version"}
        if set(value) - allowed:
            raise HumanEscalationDomainError("human_escalation_redaction_failed")
        try:
            return cls(**{key: value[key] for key in value})  # type: ignore[arg-type]
        except (TypeError, ValueError) as error:
            raise HumanEscalationDomainError("human_escalation_redaction_failed") from error


@dataclass(frozen=True, slots=True)
class EscalationAlertIntent:
    escalation_ref: str
    ticket_ref: str
    trigger_code: TriggerCode
    category: str
    safe_summary: str
    hold_state: AutomationHoldState
    correlation_id: str
    source_digest: str
    urgency: str = "high"

    def __post_init__(self) -> None:
        for value, name, maximum in ((self.escalation_ref, "escalation_ref", 191), (self.ticket_ref, "ticket_ref", 191), (self.category, "category", 40), (self.safe_summary, "safe_summary", 500), (self.correlation_id, "correlation_id", 191)):
            _safe(value, name, maximum)
        if self.urgency != "high":
            raise HumanEscalationDomainError("human_escalation_source_invalid")
        if not _DIGEST.fullmatch(self.source_digest):
            raise HumanEscalationDomainError("human_escalation_redaction_failed")
        _reject_sensitive(("escalation_ref", self.escalation_ref), ("ticket_ref", self.ticket_ref), ("category", self.category), ("safe_summary", self.safe_summary))


def evidence_digest(value: object) -> str:
    """Create a deterministic digest without retaining the evidence payload."""
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise HumanEscalationDomainError("human_escalation_source_invalid") from error
    return hashlib.sha256(encoded).hexdigest()


def validate_source_fingerprint(value: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise HumanEscalationDomainError("human_escalation_source_invalid")
    return value


def validate_trigger(trigger: TriggerCode, source_kind: str, policy_version: str, context: EscalationContext) -> None:
    allowed = {
        TriggerCode.EXPLICIT_HUMAN_REQUEST: {"ticket_referral", "line_inbox"},
        TriggerCode.EXPLICIT_WRONG_ANSWER: {"ticket_referral", "line_inbox"},
        TriggerCode.BINDING_FAILURE_THRESHOLD_2: {"binding_failure"},
        TriggerCode.COMPLAINT: {"line_inbox"},
        TriggerCode.RUNTIME_CRITICAL: {"runtime_health"},
    }
    if not isinstance(trigger, TriggerCode) or source_kind not in allowed.get(trigger, set()):
        raise HumanEscalationDomainError("human_escalation_source_invalid")
    _safe(policy_version, "trigger_policy_version", 191)
    if trigger is TriggerCode.COMPLAINT:
        if (
            policy_version != "complaint.v1"
            or context.policy_version != "complaint.v1"
            or context.summary_code != "complaint_explicit"
            or context.category != "other"
            or context.redaction_version != "m4-mask.v1"
        ):
            raise HumanEscalationDomainError("human_escalation_source_invalid")


def _safe(value: object, name: str, maximum: int) -> None:
    if not isinstance(value, str) or len(value) == 0 or len(value) > maximum or not _SAFE.fullmatch(value):
        raise HumanEscalationDomainError("human_escalation_redaction_failed", f"{name} 不符合bounded 格式")


def _reject_sensitive(*pairs: tuple[str, str]) -> None:
    for key, value in pairs:
        lowered = f"{key}:{value}".lower()
        if _PHONE.search(value) or _EMAIL.search(value) or _LINE_USER_ID.search(value):
            raise HumanEscalationDomainError("human_escalation_redaction_failed")
        if any(part in lowered for part in _SENSITIVE_KEY_PARTS):
            # The allowlisted field names are safe; only reject obvious raw identity markers.
            if key not in {"category", "hold_scope_label"} and any(part in value.lower() for part in ("line_user_id", "phone", "provider", "raw_message", "scheduling_id")):
                raise HumanEscalationDomainError("human_escalation_redaction_failed")


__all__ = [
    "AlertStatus", "AutomationHoldState", "EscalationEventType", "EscalationWorkflowStatus",
    "HumanEscalationDomainError", "EscalationAlertIntent", "EscalationContext", "TriggerCode",
    "evidence_digest", "validate_source_fingerprint", "validate_trigger",
]
