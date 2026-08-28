"""
File: maintenance.py
Description: 定義異常重掃描與 projector 死信人工重試的 typed Domain 契約。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domains.anomalies.root_fact_projection import FinanceManualReviewRootFact
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_MAXIMUM_SCAN_SIZE = 100
_MINIMUM_DEAD_LETTER_ATTEMPTS = 3
_RECLASSIFICATION_EVIDENCE_MAXIMUM_LENGTH = 500


class AnomalyReclassificationDisposition(StrEnum):
    """The only terminal dispositions allowed by the necessity migration."""

    RECLASSIFIED_TO_OWNER_WORK_ITEM = "reclassified_to_owner_work_item"
    RETIRED_FALSE_POSITIVE = "retired_false_positive"
    REPLACED_BY_SUCCESSOR = "replaced_by_successor"


@dataclass(frozen=True, slots=True)
class AnomalyReclassificationAlertIdentity:
    """Immutable alert and owning-root identity captured by a migration preview."""

    alert_fingerprint: PreviewFingerprint
    definition_code: str
    source_identity: str
    source_version: int
    workflow_version: int

    def __post_init__(self) -> None:
        if not isinstance(self.alert_fingerprint, PreviewFingerprint):
            raise TypeError("alert fingerprint must be PreviewFingerprint")
        require_canonical_text(self.definition_code, "anomaly definition code", 191)
        require_canonical_text(self.source_identity, "anomaly source identity", 191)
        require_nonnegative_integer(self.source_version, "anomaly source version")
        require_nonnegative_integer(self.workflow_version, "anomaly workflow version")

    @property
    def fingerprint(self) -> PreviewFingerprint:
        return self.alert_fingerprint

    @property
    def root_identity(self) -> str:
        return self.source_identity

    @property
    def root_version(self) -> int:
        return self.source_version


# Short aliases keep the contract discoverable to callers using alert/root vocabulary.
AnomalyReclassificationAlert = AnomalyReclassificationAlertIdentity


@dataclass(frozen=True, slots=True)
class AnomalyReclassificationTargetBinding:
    """Optional owner target; either every field is present or every field is absent."""

    target_domain: str | None = None
    target_reference: str | None = None
    target_version: int | None = None

    def __post_init__(self) -> None:
        values = (self.target_domain, self.target_reference, self.target_version)
        if all(value is None for value in values):
            return
        if any(value is None for value in values):
            raise ValueError("anomaly reclassification target binding is incomplete")
        require_canonical_text(self.target_domain, "target domain", 191)
        require_canonical_text(self.target_reference, "target reference", 191)
        require_nonnegative_integer(self.target_version, "target version")


@dataclass(frozen=True, slots=True)
class AnomalyReclassificationCandidate:
    """Zero-write, deterministic preview of one immutable disposition."""

    disposition: AnomalyReclassificationDisposition
    alert: AnomalyReclassificationAlertIdentity
    target: AnomalyReclassificationTargetBinding | None
    actor: ActorContext
    reason: str
    evidence_reference: str
    rulebook_reference: str | None
    release_evidence_reference: str | None
    fingerprint: PreviewFingerprint

    def __post_init__(self) -> None:
        _validate_reclassification_payload(
            self.disposition,
            self.alert,
            self.target,
            self.actor,
            self.reason,
            self.evidence_reference,
            self.rulebook_reference,
            self.release_evidence_reference,
        )
        if not isinstance(self.fingerprint, PreviewFingerprint):
            raise TypeError("reclassification fingerprint must be PreviewFingerprint")

    @property
    def disposition_identity(self) -> str:
        return _disposition_identity(self.alert, self.disposition)


AnomalyReclassificationPreview = AnomalyReclassificationCandidate
AnomalyReclassificationPreviewCandidate = AnomalyReclassificationCandidate


@dataclass(frozen=True, slots=True)
class AnomalyReclassificationApplyRequest:
    """Typed Apply input; adapters must re-read the alert and target before writing."""

    disposition_identity: str
    disposition: AnomalyReclassificationDisposition
    alert: AnomalyReclassificationAlertIdentity
    target: AnomalyReclassificationTargetBinding | None
    reason: str
    evidence_reference: str
    rulebook_reference: str | None
    release_evidence_reference: str | None
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(
            self.disposition_identity, "disposition identity", 191
        )
        _validate_reclassification_payload(
            self.disposition,
            self.alert,
            self.target,
            self.actor,
            self.reason,
            self.evidence_reference,
            self.rulebook_reference,
            self.release_evidence_reference,
        )
        if self.disposition_identity != _disposition_identity(
            self.alert, self.disposition
        ):
            raise ValueError("anomaly reclassification disposition identity mismatch")
        if not isinstance(self.preview_fingerprint, PreviewFingerprint):
            raise TypeError("preview fingerprint must be PreviewFingerprint")
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise TypeError("idempotency key must be IdempotencyKey")
        if not isinstance(self.actor, ActorContext):
            raise TypeError("actor must be ActorContext")
        if not isinstance(self.correlation_id, CorrelationId):
            raise TypeError("correlation id must be CorrelationId")

    @classmethod
    def from_preview(
        cls,
        preview: AnomalyReclassificationCandidate,
        *,
        idempotency_key: IdempotencyKey,
        correlation_id: CorrelationId,
    ) -> "AnomalyReclassificationApplyRequest":
        if not isinstance(preview, AnomalyReclassificationCandidate):
            raise TypeError("preview must be AnomalyReclassificationCandidate")
        return cls(
            preview.disposition_identity,
            preview.disposition,
            preview.alert,
            preview.target,
            preview.reason,
            preview.evidence_reference,
            preview.rulebook_reference,
            preview.release_evidence_reference,
            preview.fingerprint,
            idempotency_key,
            preview.actor,
            correlation_id,
        )


AnomalyReclassificationRequest = AnomalyReclassificationApplyRequest


@dataclass(frozen=True, slots=True)
class AnomalyReclassificationReceipt:
    """Immutable Apply receipt; replay is explicit and never changes its identity."""

    disposition_identity: str
    receipt_identity: str
    disposition: AnomalyReclassificationDisposition
    alert: AnomalyReclassificationAlertIdentity
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId
    actor: ActorContext
    created_at: datetime
    workflow_event_id: int
    resulting_workflow_version: int
    before_state_fingerprint: PreviewFingerprint
    after_state_fingerprint: PreviewFingerprint
    resulting_predicate_active: bool = False
    replayed: bool = False

    def __post_init__(self) -> None:
        require_canonical_text(
            self.disposition_identity, "disposition identity", 191
        )
        require_canonical_text(self.receipt_identity, "receipt identity", 191)
        if not isinstance(self.disposition, AnomalyReclassificationDisposition):
            raise TypeError("reclassification disposition is invalid")
        if not isinstance(self.alert, AnomalyReclassificationAlertIdentity):
            raise TypeError("reclassification alert is invalid")
        if self.disposition_identity != _disposition_identity(
            self.alert, self.disposition
        ):
            raise ValueError("anomaly reclassification disposition identity mismatch")
        if not isinstance(self.preview_fingerprint, PreviewFingerprint):
            raise TypeError("preview fingerprint must be PreviewFingerprint")
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise TypeError("idempotency key must be IdempotencyKey")
        if not isinstance(self.correlation_id, CorrelationId):
            raise TypeError("correlation id must be CorrelationId")
        if not isinstance(self.actor, ActorContext):
            raise TypeError("actor must be ActorContext")
        if not isinstance(self.created_at, datetime):
            raise TypeError("reclassification receipt timestamp is invalid")
        require_positive_integer(self.workflow_event_id, "workflow event id")
        require_positive_integer(
            self.resulting_workflow_version, "resulting workflow version"
        )
        if self.resulting_workflow_version != self.alert.workflow_version + 1:
            raise ValueError("reclassification workflow version mismatch")
        if not isinstance(self.before_state_fingerprint, PreviewFingerprint):
            raise TypeError("before state fingerprint must be PreviewFingerprint")
        if not isinstance(self.after_state_fingerprint, PreviewFingerprint):
            raise TypeError("after state fingerprint must be PreviewFingerprint")
        if not isinstance(self.resulting_predicate_active, bool):
            raise TypeError("resulting predicate active must be bool")
        if not isinstance(self.replayed, bool):
            raise TypeError("receipt replayed flag must be bool")
        if self.resulting_predicate_active:
            raise ValueError("reclassification receipt must deactivate predicate")


@dataclass(frozen=True, slots=True)
class AnomalyReclassificationCursor:
    """Lexicographic cursor over the deterministic definition/source key."""

    definition_code: str
    source_identity: str

    def __post_init__(self) -> None:
        require_canonical_text(self.definition_code, "cursor definition code", 191)
        require_canonical_text(self.source_identity, "cursor source identity", 191)

    @property
    def key(self) -> tuple[str, str]:
        return self.definition_code, self.source_identity


@dataclass(frozen=True, slots=True)
class AnomalyReclassificationCursorPageRequest:
    maximum_items: int = 100
    after: AnomalyReclassificationCursor | None = None

    def __post_init__(self) -> None:
        _require_bounded_size(self.maximum_items)
        if self.after is not None and not isinstance(
            self.after, AnomalyReclassificationCursor
        ):
            raise TypeError("reclassification cursor is invalid")


@dataclass(frozen=True, slots=True)
class AnomalyReclassificationPage:
    items: tuple[AnomalyReclassificationAlertIdentity, ...]
    next_cursor: AnomalyReclassificationCursor | None

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            raise TypeError("reclassification page items must be a tuple")
        if len(self.items) > _MAXIMUM_SCAN_SIZE:
            raise ValueError("reclassification page exceeds maximum")
        if any(
            not isinstance(item, AnomalyReclassificationAlertIdentity)
            for item in self.items
        ):
            raise TypeError("reclassification page item is invalid")
        keys = tuple(
            (item.definition_code, item.source_identity) for item in self.items
        )
        if keys != tuple(sorted(set(keys))):
            raise ValueError("reclassification page items must be strictly ordered")
        if self.next_cursor is not None:
            if not isinstance(self.next_cursor, AnomalyReclassificationCursor):
                raise TypeError("next cursor is invalid")
            if keys and self.next_cursor.key != keys[-1]:
                raise ValueError("next cursor must equal last page item")

    @property
    def alerts(self) -> tuple[AnomalyReclassificationAlertIdentity, ...]:
        return self.items


@dataclass(frozen=True, slots=True)
class AnomalyReclassificationBlockedItem:
    definition_code: str
    source_identity: str
    reason: str
    alert_fingerprint: PreviewFingerprint | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.definition_code, "blocked definition code", 191)
        require_canonical_text(self.source_identity, "blocked source identity", 191)
        require_canonical_text(
            self.reason,
            "blocked reason",
            _RECLASSIFICATION_EVIDENCE_MAXIMUM_LENGTH,
        )
        if self.alert_fingerprint is not None and not isinstance(
            self.alert_fingerprint, PreviewFingerprint
        ):
            raise TypeError("blocked alert fingerprint must be PreviewFingerprint")

    @property
    def cursor(self) -> AnomalyReclassificationCursor:
        return AnomalyReclassificationCursor(self.definition_code, self.source_identity)


@dataclass(frozen=True, slots=True)
class AnomalyReclassificationResult:
    scanned_count: int
    applied_count: int
    blocked_items: tuple[AnomalyReclassificationBlockedItem, ...]
    next_cursor: AnomalyReclassificationCursor | None
    batch_receipt_identity: str | None = None

    def __post_init__(self) -> None:
        require_nonnegative_integer(self.scanned_count, "scanned count")
        require_nonnegative_integer(self.applied_count, "applied count")
        if not isinstance(self.blocked_items, tuple):
            raise TypeError("blocked items must be a tuple")
        if len(self.blocked_items) > _MAXIMUM_SCAN_SIZE:
            raise ValueError("blocked items exceed maximum")
        if any(
            not isinstance(item, AnomalyReclassificationBlockedItem)
            for item in self.blocked_items
        ):
            raise TypeError("blocked item is invalid")
        blocked_keys = tuple(item.cursor.key for item in self.blocked_items)
        if blocked_keys != tuple(sorted(set(blocked_keys))):
            raise ValueError("blocked items must be strictly ordered")
        if self.applied_count + len(self.blocked_items) != self.scanned_count:
            raise ValueError("reclassification result counts are inconsistent")
        if self.next_cursor is not None and not isinstance(
            self.next_cursor, AnomalyReclassificationCursor
        ):
            raise TypeError("next cursor is invalid")
        if self.batch_receipt_identity is not None:
            require_canonical_text(
                self.batch_receipt_identity, "batch receipt identity", 191
            )

    @property
    def blocked_count(self) -> int:
        return len(self.blocked_items)

    @property
    def completed(self) -> bool:
        return self.next_cursor is None and not self.blocked_items


AnomalyReclassificationCursorPage = AnomalyReclassificationPage
AnomalyReclassificationBatchResult = AnomalyReclassificationResult


def preview_anomaly_reclassification(
    *,
    disposition: AnomalyReclassificationDisposition,
    alert: AnomalyReclassificationAlertIdentity,
    target: AnomalyReclassificationTargetBinding | None,
    actor: ActorContext,
    reason: str,
    evidence_reference: str,
    rulebook_reference: str | None = None,
    release_evidence_reference: str | None = None,
) -> AnomalyReclassificationCandidate:
    _validate_reclassification_payload(
        disposition,
        alert,
        target,
        actor,
        reason,
        evidence_reference,
        rulebook_reference,
        release_evidence_reference,
    )
    fingerprint = fingerprint_payload(
        {
            "disposition": disposition.value,
            "alert_fingerprint": alert.alert_fingerprint.value,
            "definition_code": alert.definition_code,
            "source_identity": alert.source_identity,
            "source_version": alert.source_version,
            "workflow_version": alert.workflow_version,
            "actor_id": actor.actor_id,
            "actor_permission_scope": actor.permission_scope,
            "target_domain": target.target_domain if target else None,
            "target_reference": target.target_reference if target else None,
            "target_version": target.target_version if target else None,
            "reason": reason,
            "evidence_reference": evidence_reference,
            "rulebook_reference": rulebook_reference,
            "release_evidence_reference": release_evidence_reference,
        }
    )
    return AnomalyReclassificationCandidate(
        disposition,
        alert,
        target,
        actor,
        reason,
        evidence_reference,
        rulebook_reference,
        release_evidence_reference,
        fingerprint,
    )


build_anomaly_reclassification_candidate = preview_anomaly_reclassification
preview_anomaly_reclassification_candidate = preview_anomaly_reclassification


def _disposition_identity(
    alert: AnomalyReclassificationAlertIdentity,
    disposition: AnomalyReclassificationDisposition,
) -> str:
    del disposition
    return f"anomaly-reclassification:{alert.alert_fingerprint.value}"


def _validate_reclassification_payload(
    disposition,
    alert,
    target,
    actor,
    reason,
    evidence_reference,
    rulebook_reference,
    release_evidence_reference,
) -> None:
    if not isinstance(disposition, AnomalyReclassificationDisposition):
        raise TypeError("reclassification disposition is invalid")
    if not isinstance(alert, AnomalyReclassificationAlertIdentity):
        raise TypeError("reclassification alert is invalid")
    if target is not None and not isinstance(
        target, AnomalyReclassificationTargetBinding
    ):
        raise TypeError("reclassification target is invalid")
    if disposition is AnomalyReclassificationDisposition.RETIRED_FALSE_POSITIVE:
        if target is not None and any(
            value is not None
            for value in (
                target.target_domain,
                target.target_reference,
                target.target_version,
            )
        ):
            raise ValueError("retired false positive cannot have a target")
        if rulebook_reference is None or release_evidence_reference is None:
            raise ValueError("retired false positive requires rulebook and release evidence")
    else:
        if target is None or any(
            value is None
            for value in (
                target.target_domain,
                target.target_reference,
                target.target_version,
            )
        ):
            raise ValueError("reclassification target is required")
        if (rulebook_reference is None) != (release_evidence_reference is None):
            raise ValueError("rulebook and release evidence must be supplied together")
    if not isinstance(actor, ActorContext):
        raise TypeError("actor must be ActorContext")
    require_canonical_text(reason, "reclassification reason", _RECLASSIFICATION_EVIDENCE_MAXIMUM_LENGTH)
    require_canonical_text(
        evidence_reference,
        "reclassification evidence reference",
        _RECLASSIFICATION_EVIDENCE_MAXIMUM_LENGTH,
    )
    if rulebook_reference is not None:
        require_canonical_text(
            rulebook_reference, "rulebook reference", _RECLASSIFICATION_EVIDENCE_MAXIMUM_LENGTH
        )
    if release_evidence_reference is not None:
        require_canonical_text(
            release_evidence_reference,
            "release evidence reference",
            _RECLASSIFICATION_EVIDENCE_MAXIMUM_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class ScanAnomalyDefinitionRequest:
    definition_code: str
    maximum_items: int = 50
    after_source_id: int = 0

    def __post_init__(self) -> None:
        require_canonical_text(
            self.definition_code,
            "anomaly definition code",
            191,
        )
        _require_bounded_size(self.maximum_items)
        require_nonnegative_integer(
            self.after_source_id,
            "scan source cursor",
        )


@dataclass(frozen=True, slots=True)
class AnomalyDefinitionScanPage:
    root_facts: tuple[FinanceManualReviewRootFact, ...]
    next_after_source_id: int | None


@dataclass(frozen=True, slots=True)
class ScanAnomalyDefinitionResult:
    definition_code: str
    scanned_count: int
    active_count: int
    inactive_count: int
    next_after_source_id: int | None

    @property
    def completed(self) -> bool:
        return self.next_after_source_id is None


@dataclass(frozen=True, slots=True)
class RetryAnomalyProjectorRequest:
    maximum_events: int = 50

    def __post_init__(self) -> None:
        _require_bounded_size(self.maximum_events)


@dataclass(frozen=True, slots=True)
class RetryAnomalyProjectorResult:
    projector_identity: str
    requeued_event_ids: tuple[int, ...]

    @property
    def requeued_count(self) -> int:
        return len(self.requeued_event_ids)


@dataclass(frozen=True, slots=True)
class ProjectorDeadLetterIdentity:
    projector_identity: str
    event_id: int

    def __post_init__(self) -> None:
        require_canonical_text(self.projector_identity, "projector identity", 100)
        require_positive_integer(self.event_id, "projector event id")


@dataclass(frozen=True, slots=True)
class ProjectorDeadLetter:
    identity: ProjectorDeadLetterIdentity
    intent_type: str
    attempt_count: int
    error_code: str
    failed_at: datetime
    successor: ProjectorDeadLetterSuccessor | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.intent_type, "projector intent type", 191)
        require_positive_integer(self.attempt_count, "projector attempt count")
        if self.attempt_count < _MINIMUM_DEAD_LETTER_ATTEMPTS:
            raise ValueError("projector attempt count is below dead-letter threshold")
        require_canonical_text(self.error_code, "projector error code", 191)
        if not isinstance(self.failed_at, datetime):
            raise ValueError("projector failed timestamp is invalid")


@dataclass(frozen=True, slots=True)
class ProjectorDeadLetterSuccessor:
    event_id: int
    source_version: int
    alert_fingerprint: PreviewFingerprint
    predicate_active: bool

    def __post_init__(self) -> None:
        require_positive_integer(self.event_id, "projector successor event id")
        require_positive_integer(self.source_version, "projector successor source version")


@dataclass(frozen=True, slots=True)
class RetryProjectorDeadLetterPreview:
    dead_letter: ProjectorDeadLetter
    reason: str
    evidence_reference: str
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class RetryProjectorDeadLetterRequest:
    identity: ProjectorDeadLetterIdentity
    expected_attempt_count: int
    reason: str
    evidence_reference: str
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_positive_integer(self.expected_attempt_count, "expected attempt count")
        if self.expected_attempt_count < _MINIMUM_DEAD_LETTER_ATTEMPTS:
            raise ValueError("expected attempt count is below dead-letter threshold")
        require_canonical_text(self.reason, "retry reason", 500)
        require_canonical_text(self.evidence_reference, "retry evidence reference", 500)


@dataclass(frozen=True, slots=True)
class RetryProjectorDeadLetterReceipt:
    identity: ProjectorDeadLetterIdentity
    prior_attempt_count: int
    resulting_status: str
    receipt_identity: str
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class SupersedeProjectorDeadLetterPreview:
    dead_letter: ProjectorDeadLetter
    successor: ProjectorDeadLetterSuccessor
    reason: str
    evidence_reference: str
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class SupersedeProjectorDeadLetterRequest:
    identity: ProjectorDeadLetterIdentity
    expected_attempt_count: int
    expected_successor_event_id: int
    expected_successor_source_version: int
    reason: str
    evidence_reference: str
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_positive_integer(self.expected_attempt_count, "expected attempt count")
        if self.expected_attempt_count < _MINIMUM_DEAD_LETTER_ATTEMPTS:
            raise ValueError("expected attempt count is below dead-letter threshold")
        require_positive_integer(
            self.expected_successor_event_id, "expected successor event id"
        )
        require_positive_integer(
            self.expected_successor_source_version,
            "expected successor source version",
        )
        require_canonical_text(self.reason, "supersede reason", 500)
        require_canonical_text(
            self.evidence_reference, "supersede evidence reference", 500
        )


@dataclass(frozen=True, slots=True)
class SupersedeProjectorDeadLetterReceipt:
    identity: ProjectorDeadLetterIdentity
    successor_event_id: int
    successor_source_version: int
    resulting_status: str
    receipt_identity: str
    replayed: bool = False


def preview_projector_dead_letter_retry(
    dead_letter: ProjectorDeadLetter,
    reason: str,
    evidence_reference: str,
) -> RetryProjectorDeadLetterPreview:
    require_canonical_text(reason, "retry reason", 500)
    require_canonical_text(evidence_reference, "retry evidence reference", 500)
    fingerprint = fingerprint_payload({
        "projector_identity": dead_letter.identity.projector_identity,
        "event_id": dead_letter.identity.event_id,
        "intent_type": dead_letter.intent_type,
        "attempt_count": dead_letter.attempt_count,
        "error_code": dead_letter.error_code,
        "reason": reason,
        "evidence_reference": evidence_reference,
    })
    return RetryProjectorDeadLetterPreview(
        dead_letter, reason, evidence_reference, fingerprint
    )


def preview_projector_dead_letter_supersede(
    dead_letter: ProjectorDeadLetter,
    reason: str,
    evidence_reference: str,
) -> SupersedeProjectorDeadLetterPreview:
    require_canonical_text(reason, "supersede reason", 500)
    require_canonical_text(
        evidence_reference, "supersede evidence reference", 500
    )
    successor = dead_letter.successor
    if successor is None:
        raise ValueError("projector_dead_letter_successor_not_verified")
    if successor.event_id <= dead_letter.identity.event_id:
        raise ValueError("projector_dead_letter_successor_not_verified")
    fingerprint = fingerprint_payload({
        "projector_identity": dead_letter.identity.projector_identity,
        "event_id": dead_letter.identity.event_id,
        "intent_type": dead_letter.intent_type,
        "attempt_count": dead_letter.attempt_count,
        "error_code": dead_letter.error_code,
        "successor_event_id": successor.event_id,
        "successor_source_version": successor.source_version,
        "successor_alert_fingerprint": successor.alert_fingerprint.value,
        "successor_predicate_active": successor.predicate_active,
        "reason": reason,
        "evidence_reference": evidence_reference,
    })
    return SupersedeProjectorDeadLetterPreview(
        dead_letter,
        successor,
        reason,
        evidence_reference,
        fingerprint,
    )


def _require_bounded_size(value: int) -> None:
    require_positive_integer(value, "bounded operation size")
    if value > _MAXIMUM_SCAN_SIZE:
        raise ValueError("bounded operation size exceeds maximum")


__all__ = [
    "AnomalyReclassificationAlert",
    "AnomalyReclassificationAlertIdentity",
    "AnomalyReclassificationApplyRequest",
    "AnomalyReclassificationBatchResult",
    "AnomalyReclassificationBlockedItem",
    "AnomalyReclassificationCandidate",
    "AnomalyReclassificationCursor",
    "AnomalyReclassificationCursorPage",
    "AnomalyReclassificationCursorPageRequest",
    "AnomalyReclassificationDisposition",
    "AnomalyReclassificationPage",
    "AnomalyReclassificationPreview",
    "AnomalyReclassificationPreviewCandidate",
    "AnomalyReclassificationReceipt",
    "AnomalyReclassificationRequest",
    "AnomalyReclassificationResult",
    "AnomalyReclassificationTargetBinding",
    "AnomalyDefinitionScanPage",
    "RetryAnomalyProjectorRequest",
    "RetryAnomalyProjectorResult",
    "ProjectorDeadLetter",
    "ProjectorDeadLetterIdentity",
    "ProjectorDeadLetterSuccessor",
    "RetryProjectorDeadLetterPreview",
    "RetryProjectorDeadLetterReceipt",
    "RetryProjectorDeadLetterRequest",
    "SupersedeProjectorDeadLetterPreview",
    "SupersedeProjectorDeadLetterReceipt",
    "SupersedeProjectorDeadLetterRequest",
    "ScanAnomalyDefinitionRequest",
    "ScanAnomalyDefinitionResult",
    "preview_projector_dead_letter_retry",
    "preview_projector_dead_letter_supersede",
    "build_anomaly_reclassification_candidate",
    "preview_anomaly_reclassification",
    "preview_anomaly_reclassification_candidate",
]
