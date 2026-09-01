"""P5 adapter for committed Scheduling matching notification intents.

The M3 outbox is immutable and intentionally has no delivery lease columns.  This
adapter therefore consumes a committed row by projecting it into the existing
LINE delivery-task owner.  Replaying a row is safe because the delivery task
repository owns the unique idempotency key.

No provider call is made here.  ``LocalLineDeliveryAdapter`` is only the bounded
development/mock result required by the P5 contract.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Callable, Mapping, Protocol

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineDeliveryStatus,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import (
    LineGroupId,
    LineProviderMessageId,
    LineRoomId,
    LineUserId,
)
from shared_kernel.identities import CorrelationId, IdempotencyKey
from shared_kernel.validation import require_canonical_text, require_positive_integer
from subsystems.line.delivery_contracts import (
    LineProviderOutcome,
    LineProviderOutcomeType,
)
from subsystems.line.notification_failure_current_fact import (
    LineNotificationFailureCurrentFactReadback,
    LineNotificationFailureCurrentFactQuery,
    LineNotificationFailureReason,
)


class MatchingCoordinationDeliveryError(ValueError):
    """A committed M3 handoff cannot be safely projected into LINE delivery."""

    def __init__(self, code: str) -> None:
        require_canonical_text(code, "matching delivery error code", 191)
        self.code = code
        super().__init__(code)


class MatchingDeliveryProviderStatus(StrEnum):
    NOT_RUN = "provider-not-run"
    LOCAL_SUCCESS = "local-success"


@dataclass(frozen=True, slots=True)
class MatchingCoordinationOutboxItem:
    """Typed read shape for one committed M3 owner-outbox row."""

    reference_id: str
    event_id: int
    receipt_id: str
    case_no: str
    intent_type: str
    target_owner: str
    intent_payload: Mapping[str, Any]
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        for value, label in (
            (self.reference_id, "matching outbox reference ID"),
            (self.receipt_id, "matching outbox receipt ID"),
            (self.case_no, "matching outbox case number"),
            (self.intent_type, "matching outbox intent type"),
            (self.target_owner, "matching outbox target owner"),
        ):
            require_canonical_text(value, label, 191)
        require_positive_integer(self.event_id, "matching outbox event ID")
        if not isinstance(self.intent_payload, Mapping):
            raise TypeError("matching outbox intent payload must be an object")
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise TypeError("matching outbox idempotency key must be typed")
        if not isinstance(self.correlation_id, CorrelationId):
            raise TypeError("matching outbox correlation ID must be typed")


@dataclass(frozen=True, slots=True)
class MatchingCoordinationDeliveryReceipt:
    reference_id: str
    event_id: int
    receipt_id: str
    source_event_identity: str
    source_identity: str
    recipient_selector: str
    recipient_snapshot: Mapping[str, str]
    task_id: int
    task_status: LineDeliveryStatus
    replayed: bool
    provider_status: MatchingDeliveryProviderStatus
    line006_readback: LineNotificationFailureCurrentFactReadback | None

    def __post_init__(self) -> None:
        require_canonical_text(self.reference_id, "matching delivery reference ID", 191)
        require_positive_integer(self.event_id, "matching delivery event ID")
        require_canonical_text(self.receipt_id, "matching delivery receipt ID", 191)
        require_canonical_text(self.source_event_identity, "matching delivery source event identity", 191)
        require_canonical_text(self.source_identity, "matching delivery source identity", 191)
        require_canonical_text(self.recipient_selector, "matching delivery recipient selector", 191)
        require_positive_integer(self.task_id, "matching delivery task ID")
        if not isinstance(self.task_status, LineDeliveryStatus):
            raise TypeError("matching delivery task status is invalid")
        if not isinstance(self.replayed, bool):
            raise TypeError("matching delivery replay flag is invalid")
        if not isinstance(self.provider_status, MatchingDeliveryProviderStatus):
            raise TypeError("matching delivery provider status is invalid")


class MatchingDeliveryTaskRepositoryPort(Protocol):
    def enqueue(self, request: LineDeliveryRequest): ...

    def get(self, task_id): ...


class MatchingDeliveryUnitOfWorkPort(Protocol):
    delivery_tasks: MatchingDeliveryTaskRepositoryPort
    notification_rules: Any
    matching_notifications: Any

    def __enter__(self): ...

    def __exit__(self, exception_type, exception, traceback) -> bool: ...

    def commit(self) -> None: ...


class MatchingCoordinationDeliveryApplication:
    """Project one M3 owner intent inside one caller-owned LINE transaction."""

    def __init__(
        self,
        unit_of_work_factory: Callable[[], MatchingDeliveryUnitOfWorkPort],
        now: Callable[[], datetime],
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._now = now

    def consume(self, item: MatchingCoordinationOutboxItem) -> MatchingCoordinationDeliveryReceipt:
        request, metadata = normalize_matching_coordination_intent(item, now=self._now())
        with self._unit_of_work_factory() as unit_of_work:
            _open_client_decision_interaction(unit_of_work, item.intent_payload)
            result = unit_of_work.delivery_tasks.enqueue(request)
            task = unit_of_work.delivery_tasks.get(result.task_id)
            if task is None:
                raise MatchingCoordinationDeliveryError("line_matching_delivery_task_readback_missing")
            line006 = _line006_readback(unit_of_work, item.case_no, item.intent_payload)
            unit_of_work.commit()
        return MatchingCoordinationDeliveryReceipt(
            item.reference_id,
            item.event_id,
            item.receipt_id,
            metadata["source_event_identity"],
            metadata["source_identity"],
            metadata["recipient_selector"],
            metadata["recipient_snapshot"],
            task.task_id.value,
            task.status,
            result.outcome.value == "existing",
            MatchingDeliveryProviderStatus.NOT_RUN,
            line006,
        )


def _open_client_decision_interaction(
    unit_of_work: MatchingDeliveryUnitOfWorkPort,
    payload: Mapping[str, Any],
) -> None:
    """Persist a zero-pool token through the existing LINE interaction owner."""

    interaction = payload.get("interaction")
    if not isinstance(interaction, Mapping):
        return
    token = interaction.get("token")
    plan_id = interaction.get("plan_id")
    expires_at = interaction.get("expires_at_utc")
    if not isinstance(token, str) or not token.strip():
        raise MatchingCoordinationDeliveryError("line_matching_interaction_token_missing")
    if not isinstance(plan_id, int) or isinstance(plan_id, bool) or plan_id <= 0:
        raise MatchingCoordinationDeliveryError("line_matching_interaction_plan_missing")
    if not isinstance(expires_at, str):
        raise MatchingCoordinationDeliveryError("line_matching_interaction_expiry_missing")
    try:
        expiry = datetime.fromisoformat(expires_at)
    except ValueError as error:
        raise MatchingCoordinationDeliveryError("line_matching_interaction_expiry_invalid") from error
    if expiry.tzinfo is None or expiry.utcoffset() is None:
        raise MatchingCoordinationDeliveryError("line_matching_interaction_expiry_invalid")
    repository = getattr(unit_of_work, "matching_notifications", None)
    if repository is None or not callable(getattr(repository, "interaction", None)):
        raise MatchingCoordinationDeliveryError("line_matching_interaction_owner_unavailable")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if repository.interaction(token_hash) is not None:
        return
    repository.open_interaction(
        token_hash=token_hash,
        plan_id=plan_id,
        segment_id=None,
        action_scope="customer_decision",
        recipient=LineUserId(str(payload["recipient_snapshot"]["recipient_identity"])),
        expires_at=expiry,
    )


class LocalLineDeliveryAdapter:
    """Deterministic local result; it has no network or provider credentials."""

    def send(self, request: LineDeliveryRequest) -> LineProviderOutcome:
        digest = hashlib.sha256(
            request.idempotency_key.value.encode("utf-8")
        ).hexdigest()[:48]
        return LineProviderOutcome(
            LineProviderOutcomeType.SUCCESS,
            provider_message_id=LineProviderMessageId("local:" + digest),
        )


def normalize_matching_coordination_intent(
    item: MatchingCoordinationOutboxItem,
    *,
    now: datetime,
) -> tuple[LineDeliveryRequest, dict[str, Any]]:
    """Validate and construct an existing typed delivery request.

    M3 must provide the exact recipient/configuration snapshot and a rendered
    message envelope.  Missing values fail closed rather than resolving a live
    recipient or inventing a template in the LINE adapter.
    """

    if item.target_owner != "line_integration":
        raise MatchingCoordinationDeliveryError("line_matching_outbox_owner_mismatch")
    if item.intent_type not in {"line_bilateral_notification", "line_client_decision"}:
        raise MatchingCoordinationDeliveryError("line_matching_outbox_intent_unsupported")
    payload = dict(item.intent_payload)
    source_identity = _text(payload, "source_identity", "line_matching_source_identity_missing")
    source_event_identity = _text(
        payload, "source_event_identity", "line_matching_source_event_missing"
    )
    selector = _text(payload, "recipient_selector", "line_matching_recipient_selector_missing")
    snapshot = payload.get("recipient_snapshot")
    if not isinstance(snapshot, Mapping):
        raise MatchingCoordinationDeliveryError("line_matching_recipient_snapshot_missing")
    recipient_type = _text(snapshot, "recipient_type", "line_matching_recipient_binding_missing")
    recipient_identity = _text(snapshot, "recipient_identity", "line_matching_recipient_binding_missing")
    binding = payload.get("binding")
    configuration = payload.get("configuration")
    if not _active_snapshot(binding):
        raise MatchingCoordinationDeliveryError("line_matching_recipient_binding_invalid")
    if not _active_snapshot(configuration):
        raise MatchingCoordinationDeliveryError("line_matching_configuration_invalid")
    message = payload.get("message")
    if not isinstance(message, Mapping):
        raise MatchingCoordinationDeliveryError("line_matching_delivery_message_missing")
    message_kind = _message_kind(payload, message)
    scheduled_at = _scheduled_at(payload, now)
    recipient = _recipient(recipient_type, recipient_identity)
    request = LineDeliveryRequest(
        recipient,
        message_kind,
        canonical_line_payload_json(message),
        scheduled_at,
        item.idempotency_key,
        item.correlation_id,
        "matching_coordination_outbox",
        item.reference_id,
    )
    return request, {
        "source_identity": source_identity,
        "source_event_identity": source_event_identity,
        "recipient_selector": selector,
        "recipient_snapshot": {
            "recipient_type": recipient_type,
            "recipient_identity": recipient_identity,
        },
    }


def _line006_readback(
    unit_of_work: MatchingDeliveryUnitOfWorkPort,
    case_no: str,
    payload: Mapping[str, Any],
) -> LineNotificationFailureCurrentFactReadback | None:
    reason_value = payload.get("notification_reason")
    if reason_value is None:
        return None
    try:
        reason = LineNotificationFailureReason(str(reason_value))
    except ValueError as error:
        raise MatchingCoordinationDeliveryError("line_matching_notification_reason_invalid") from error
    reader = getattr(getattr(unit_of_work, "notification_rules", None), "current_failure_fact", None)
    if not callable(reader):
        raise MatchingCoordinationDeliveryError("line006_typed_readback_unavailable")
    readback = reader(LineNotificationFailureCurrentFactQuery(case_no, reason))
    if not isinstance(readback, LineNotificationFailureCurrentFactReadback):
        raise MatchingCoordinationDeliveryError("line006_typed_readback_invalid")
    return readback


def _text(payload: Mapping[str, Any], key: str, error_code: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MatchingCoordinationDeliveryError(error_code)
    return value.strip()


def _active_snapshot(value: object) -> bool:
    if not isinstance(value, Mapping) or value.get("active") is not True:
        return False
    revision = value.get("revision")
    try:
        require_positive_integer(revision, "LINE matching snapshot revision")
    except (TypeError, ValueError):
        return False
    return True


def _recipient(recipient_type: str, identity: str) -> LineRecipient:
    try:
        kind = LineRecipientType(recipient_type)
    except ValueError as error:
        raise MatchingCoordinationDeliveryError("line_matching_recipient_type_invalid") from error
    if kind is LineRecipientType.USER:
        return LineRecipient(kind, LineUserId(identity))
    if kind is LineRecipientType.GROUP:
        return LineRecipient(kind, LineGroupId(identity))
    return LineRecipient(kind, LineRoomId(identity))


def _message_kind(payload: Mapping[str, Any], message: Mapping[str, Any]) -> LineMessageKind:
    value = payload.get("message_kind", message.get("type"))
    try:
        return LineMessageKind(str(value))
    except ValueError as error:
        raise MatchingCoordinationDeliveryError("line_matching_message_kind_invalid") from error


def _scheduled_at(payload: Mapping[str, Any], now: datetime) -> datetime:
    value = payload.get("scheduled_at")
    if value is None:
        return now
    if not isinstance(value, str):
        raise MatchingCoordinationDeliveryError("line_matching_scheduled_at_invalid")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as error:
        raise MatchingCoordinationDeliveryError("line_matching_scheduled_at_invalid") from error
    if result.tzinfo is None or result.utcoffset() is None:
        raise MatchingCoordinationDeliveryError("line_matching_scheduled_at_invalid")
    return result


__all__ = [
    "LocalLineDeliveryAdapter",
    "MatchingCoordinationDeliveryApplication",
    "MatchingCoordinationDeliveryError",
    "MatchingCoordinationDeliveryReceipt",
    "MatchingCoordinationOutboxItem",
    "MatchingDeliveryProviderStatus",
    "normalize_matching_coordination_intent",
]
