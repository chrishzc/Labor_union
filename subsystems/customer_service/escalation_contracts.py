"""File: escalation_contracts.py
Description: M4 escalation commands、views、ports 與bounded 通知契約。
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
    EscalationAlertIntent,
    EscalationContext,
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
class HumanEscalationAttemptWindow:
    """Safe readback of a bounded retry window; it contains no proof or identity."""

    attempt_count: int
    maximum_attempts: int
    generation: int

    def __post_init__(self) -> None:
        if self.attempt_count < 1 or self.attempt_count > self.maximum_attempts:
            raise ValueError("human escalation attempt count is invalid")
        if self.maximum_attempts < 1 or self.generation < 0:
            raise ValueError("human escalation attempt window is invalid")


@dataclass(frozen=True, slots=True)
class CreateHumanEscalation:
    source_event_identity: str
    source_kind: str
    source_fingerprint: str
    trigger_code: TriggerCode
    trigger_policy_version: str
    ticket_category: CustomerServiceCategory
    context: EscalationContext | Mapping[str, object]
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
        context = _context(self.context)
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
    context: Mapping[str, str]
    alert_status: AlertStatus
    current_version: str
    created_at: datetime
    updated_at: datetime
    available_actions: tuple[str, ...]
    delivery_task_ref: str | None = None
    delivery_outcome_ref: str | None = None
    trigger_identity: str | None = None
    attempt_window: HumanEscalationAttemptWindow | None = None
    owner_selector: str | None = None

    def __post_init__(self) -> None:
        require_positive_integer(self.escalation_id, "escalation ID")
        require_canonical_text(self.ticket_ref, "ticket reference", 191)
        if self.urgency != "high":
            raise ValueError("M4 escalation urgency must be high")
        if self.workflow_version < 0:
            raise ValueError("workflow version must be nonnegative")
        require_canonical_text(self.hold_scope_label, "hold scope label", 80)
        require_canonical_text(self.current_version, "current version", 191)
        if not isinstance(self.context, Mapping):
            raise TypeError("context must be a mapping")
        if set(self.context) - {"summary_code", "policy_version", "category", "redaction_version"}:
            raise ValueError("context contains a non-allowlisted field")
        for value, name in ((self.delivery_task_ref, "delivery task reference"), (self.delivery_outcome_ref, "delivery outcome reference")):
            if value is not None:
                require_canonical_text(value, name, 191)
        if self.trigger_identity is not None:
            require_canonical_text(self.trigger_identity, "trigger identity", 191)
        if self.attempt_window is not None and not isinstance(self.attempt_window, HumanEscalationAttemptWindow):
            raise TypeError("attempt_window must be HumanEscalationAttemptWindow")
        if self.owner_selector is not None:
            require_canonical_text(self.owner_selector, "owner selector", 191)


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
    def enqueue_alert(self, intent: EscalationAlertIntent) -> None: ...
    def save_receipt(self, key: str, fingerprint: str, receipt: HumanEscalationReceipt) -> None: ...
    def active_hold(self, hold_scope: str) -> AutomationHoldDecision | None: ...
    def record_alert_delivery_task(self, escalation_ref: str, task_id: int) -> None: ...
    def record_alert_delivery_outcome(self, escalation_ref: str, outcome_ref: str, alert_status: str) -> None: ...


class HumanEscalationTicketPort(Protocol):
    def create_or_append_escalation_ticket(self, command: CreateHumanEscalation) -> object: ...
    def get(self, ticket_id: int, *, lock: bool = False) -> object: ...
    def resolve_for_escalation(self, ticket_id: int, expected_version: int, actor_id: str, resolution_code: str) -> object: ...


class HumanEscalationSourcePort(Protocol):
    def can_release(self, escalation: object) -> bool: ...


def _context(value: EscalationContext | Mapping[str, object]) -> EscalationContext:
    if isinstance(value, EscalationContext):
        return value
    return EscalationContext.from_mapping(value)


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
