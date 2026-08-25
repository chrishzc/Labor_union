"""File: escalation_contracts.py
Description: M4 escalation commands、views、ports 與去敏通知契約。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Protocol

from domains.customer_service.escalation import (
    AlertStatus,
    AutomationHoldState,
    EscalationEventType,
    EscalationWorkflowStatus,
    MaskedAlertIntent,
    MaskedContext,
    TriggerCode,
    validate_source_fingerprint,
    validate_trigger,
)
from domains.customer_service.ticket import CustomerServiceCategory, CustomerServiceStatus
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer, require_positive_integer


class HumanEscalationError(RuntimeError):
    """Stable typed M4 application error; no raw storage/provider details escape."""

    def __init__(self, category: str, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.category = category
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class CreateHumanEscalation:
    source_event_identity: str
    source_kind: str
    source_fingerprint: str
    trigger_code: TriggerCode
    trigger_policy_version: str
    ticket_category: CustomerServiceCategory
    masked_context: MaskedContext | Mapping[str, object]
    hold_scope: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId
    actor: ActorContext
    preview_fingerprint: PreviewFingerprint | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.source_event_identity, "source event identity", 191)
        require_canonical_text(self.source_kind, "source kind", 64)
        validate_source_fingerprint(self.source_fingerprint)
        require_canonical_text(self.trigger_policy_version, "trigger policy version", 191)
        require_canonical_text(self.hold_scope, "hold scope", 191)
        if not isinstance(self.ticket_category, CustomerServiceCategory):
            raise TypeError("ticket_category must be CustomerServiceCategory")
        context = _context(self.masked_context)
        validate_trigger(self.trigger_code, self.source_kind, self.trigger_policy_version, context)


@dataclass(frozen=True, slots=True)
class ClaimHumanEscalation:
    escalation_id: int
    expected_escalation_version: int
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId
    preview_fingerprint: PreviewFingerprint | None = None

    def __post_init__(self) -> None:
        _ids(self.escalation_id, self.expected_escalation_version)


@dataclass(frozen=True, slots=True)
class StartHumanEscalationHandling:
    escalation_id: int
    expected_escalation_version: int
    expected_ticket_version: int
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId
    preview_fingerprint: PreviewFingerprint | None = None

    def __post_init__(self) -> None:
        _ids(self.escalation_id, self.expected_escalation_version, self.expected_ticket_version)


@dataclass(frozen=True, slots=True)
class ResolveHumanEscalation:
    escalation_id: int
    expected_escalation_version: int
    expected_ticket_version: int
    resolution_code: str
    resolution_evidence_digest: str
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId
    preview_fingerprint: PreviewFingerprint | None = None

    def __post_init__(self) -> None:
        _ids(self.escalation_id, self.expected_escalation_version, self.expected_ticket_version)
        require_canonical_text(self.resolution_code, "resolution code", 64)
        validate_source_fingerprint(self.resolution_evidence_digest)


@dataclass(frozen=True, slots=True)
class HumanEscalationView:
    escalation_id: int
    ticket_ref: str
    category: CustomerServiceCategory
    urgency: str
    trigger_code: TriggerCode
    workflow_status: EscalationWorkflowStatus
    workflow_version: int
    automation_hold: AutomationHoldState
    hold_scope_label: str
    masked_context: Mapping[str, str]
    alert_status: AlertStatus
    current_version: str
    created_at: datetime
    updated_at: datetime
    available_actions: tuple[str, ...]

    def __post_init__(self) -> None:
        require_positive_integer(self.escalation_id, "escalation ID")
        require_canonical_text(self.ticket_ref, "ticket reference", 191)
        if self.urgency != "high":
            raise ValueError("M4 escalation urgency must be high")
        if self.workflow_version < 0:
            raise ValueError("workflow version must be nonnegative")
        require_canonical_text(self.hold_scope_label, "hold scope label", 80)
        require_canonical_text(self.current_version, "current version", 191)
        if not isinstance(self.masked_context, Mapping):
            raise TypeError("masked_context must be a mapping")
        if set(self.masked_context) - {"summary_code", "policy_version", "category", "redaction_version"}:
            raise ValueError("masked_context contains a non-allowlisted field")


@dataclass(frozen=True, slots=True)
class HumanEscalationReceipt:
    receipt_id: str
    command_family: str
    operation: str
    escalation_id: int
    ticket_ref: str
    resulting_workflow_status: EscalationWorkflowStatus
    resulting_hold_state: AutomationHoldState
    current_version: str
    replayed: bool
    correlation_id: str
    committed_at: datetime


@dataclass(frozen=True, slots=True)
class HumanEscalationPreview:
    operation: str
    escalation_id: int | None
    before_workflow_status: str
    resulting_workflow_status: EscalationWorkflowStatus
    before_hold_state: str
    resulting_hold_state: AutomationHoldState
    current_escalation_version: int | None
    current_ticket_version: int | None
    preview_fingerprint: PreviewFingerprint
    apply_ready: bool


@dataclass(frozen=True, slots=True)
class AutomationHoldDecision:
    state: AutomationHoldState
    scope: str


class HumanEscalationPersistencePort(Protocol):
    """Typed persistence boundary; implementations own candidate schema and transaction."""

    def get_by_id(self, escalation_id: int, *, lock: bool = False) -> object | None: ...
    def get_by_source(self, source_event_identity: str, *, lock: bool = False) -> object | None: ...
    def get_by_idempotency(self, key: str, *, lock: bool = False) -> object | None: ...
    def get_active_by_scope(self, hold_scope: str, *, lock: bool = False) -> object | None: ...
    def create(self, command: CreateHumanEscalation, ticket: object) -> object: ...
    def transition(self, escalation_id: int, **changes: object) -> object: ...
    def append_event(self, escalation_id: int, event_type: EscalationEventType, **values: object) -> None: ...
    def enqueue_masked_alert(self, intent: MaskedAlertIntent) -> None: ...
    def save_receipt(self, key: str, fingerprint: str, receipt: HumanEscalationReceipt) -> None: ...
    def active_hold(self, hold_scope: str) -> AutomationHoldDecision | None: ...


class HumanEscalationTicketPort(Protocol):
    def create_or_append_escalation_ticket(self, command: CreateHumanEscalation) -> object: ...
    def get(self, ticket_id: int, *, lock: bool = False) -> object: ...
    def resolve_for_escalation(self, ticket_id: int, expected_version: int, actor_id: str, resolution_code: str) -> object: ...


class HumanEscalationSourcePort(Protocol):
    def can_release(self, escalation: object) -> bool: ...


def _context(value: MaskedContext | Mapping[str, object]) -> MaskedContext:
    if isinstance(value, MaskedContext):
        return value
    return MaskedContext.from_mapping(value)


def _ids(*values: int) -> None:
    for value in values:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("M4 version and IDs must be nonnegative integers")
    if values and values[0] == 0:
        raise ValueError("escalation ID must be positive")


__all__ = [
    "AutomationHoldDecision", "ClaimHumanEscalation", "CreateHumanEscalation",
    "HumanEscalationError", "HumanEscalationPersistencePort", "HumanEscalationPreview", "HumanEscalationReceipt",
    "HumanEscalationSourcePort", "HumanEscalationTicketPort", "HumanEscalationView",
    "ResolveHumanEscalation", "StartHumanEscalationHandling",
]
