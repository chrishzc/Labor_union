"""
File: maintenance_workflow.py
Description: 編排異常重分類 Query、Preview、Apply 與有界移轉 runner。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Protocol

from domains.anomalies.maintenance import (
    AnomalyReclassificationAlertIdentity,
    AnomalyReclassificationApplyRequest,
    AnomalyReclassificationBlockedItem,
    AnomalyReclassificationCandidate,
    AnomalyReclassificationCursor,
    AnomalyReclassificationCursorPageRequest,
    AnomalyReclassificationPage,
    AnomalyReclassificationReceipt,
    AnomalyReclassificationResult,
    AnomalyReclassificationTargetBinding,
    AnomalyReclassificationDisposition,
    ProjectorDeadLetterIdentity,
    RetryAnomalyProjectorResult,
    RetryProjectorDeadLetterReceipt,
    SupersedeProjectorDeadLetterReceipt,
    ScanAnomalyDefinitionResult,
    preview_anomaly_reclassification,
    preview_projector_dead_letter_retry,
    preview_projector_dead_letter_supersede,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_canonical_text


class AnomalyMaintenanceError(Exception):
    """Unexpected adapter failure; typed domain conflicts remain ValueError."""


class AnomalyReclassificationRepository(Protocol):
    """Port for the reclassification workflow; implementations own persistence."""

    def query_reclassification_page(
        self,
        request: AnomalyReclassificationCursorPageRequest,
        *,
        eligible_definitions: tuple[str, ...] | None = None,
    ) -> AnomalyReclassificationPage: ...

    def load_reclassification_alert(
        self, alert: AnomalyReclassificationAlertIdentity, *, for_update: bool
    ) -> AnomalyReclassificationAlertIdentity | None: ...

    def find_reclassification_batch_receipt(
        self,
        key: IdempotencyKey,
        *,
        for_update: bool,
    ) -> tuple[PreviewFingerprint, AnomalyReclassificationResult] | None: ...

    def save_reclassification_batch_receipt(
        self,
        request: "AnomalyReclassificationBatchRequest",
        result: AnomalyReclassificationResult,
        before_fingerprints: tuple[PreviewFingerprint, ...] = (),
        after_fingerprints: tuple[PreviewFingerprint, ...] = (),
        *,
        operation_identity: str | None = None,
        request_fingerprint: PreviewFingerprint | None = None,
        actor: ActorContext | None = None,
        correlation_id: CorrelationId | None = None,
    ) -> str: ...

    def find_reclassification_receipt(
        self, key: IdempotencyKey, *, for_update: bool
    ) -> tuple[PreviewFingerprint, AnomalyReclassificationReceipt] | None: ...

    def persist_reclassification(
        self,
        request: AnomalyReclassificationApplyRequest,
        candidate: AnomalyReclassificationCandidate,
    ) -> AnomalyReclassificationReceipt: ...


class AnomalyReclassificationTargetVerifier(Protocol):
    """Owner-specific port for fresh target existence/version verification."""

    def load_reclassification_target(
        self, target: AnomalyReclassificationTargetBinding, *, for_update: bool
    ) -> AnomalyReclassificationTargetBinding | None: ...


class AnomalyReclassificationSavepointUnitOfWork(UnitOfWork, Protocol):
    """UoW primitive required before a batch may isolate per-item blockers."""

    def savepoint(self): ...

    def rollback_to_savepoint(self, token) -> None: ...

    def release_savepoint(self, token) -> None: ...


class AnomalyReclassificationCandidateResolver(Protocol):
    """Deterministic migration policy supplied by the approved runner."""

    def __call__(
        self, alert: AnomalyReclassificationAlertIdentity
    ) -> AnomalyReclassificationCandidate: ...


@dataclass(frozen=True, slots=True)
class AnomalyReclassificationBatchRequest:
    """Application request persisted by the batch receipt adapter."""

    operation_identity: str
    idempotency_key: IdempotencyKey
    request_fingerprint: PreviewFingerprint
    actor: ActorContext
    correlation_id: CorrelationId
    eligible_codes: tuple[str, ...]
    maximum_items: int
    cursor: AnomalyReclassificationCursor | None

    def __post_init__(self) -> None:
        require_canonical_text(self.operation_identity, "reclassification operation identity", 191)
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise TypeError("reclassification batch idempotency key is invalid")
        if not isinstance(self.actor, ActorContext):
            raise TypeError("reclassification batch actor is invalid")
        if not isinstance(self.correlation_id, CorrelationId):
            raise TypeError("reclassification batch correlation id is invalid")
        if self.cursor is not None and not isinstance(
            self.cursor, AnomalyReclassificationCursor
        ):
            raise TypeError("reclassification batch cursor is invalid")
        if self.eligible_codes != tuple(sorted(set(self.eligible_codes))):
            raise ValueError("reclassification eligible codes must be sorted and unique")
        if not self.eligible_codes or any(
            not isinstance(code, str) for code in self.eligible_codes
        ):
            raise ValueError("reclassification eligible codes are invalid")
        for code in self.eligible_codes:
            require_canonical_text(code, "reclassification eligible code", 191)
        require_canonical_text(self.idempotency_key.value, "reclassification batch idempotency key", 191)
        require_canonical_text(self.correlation_id.value, "reclassification batch correlation id", 191)
        if not isinstance(self.request_fingerprint, PreviewFingerprint):
            raise TypeError("reclassification batch request fingerprint is invalid")
        if not 1 <= self.maximum_items <= 100:
            raise ValueError("reclassification batch size is invalid")

    @property
    def eligible_codes_fingerprint(self) -> PreviewFingerprint:
        return fingerprint_payload({"eligible_codes": self.eligible_codes})


class AnomalyMaintenanceApplication:
    def __init__(
        self,
        registry,
        scan_port,
        retry_port,
        projector,
        unit_of_work_factory: Callable[[], UnitOfWork],
        reclassification_port: AnomalyReclassificationRepository | None = None,
        target_verifier: AnomalyReclassificationTargetVerifier | None = None,
    ):
        self._registry = registry
        self._scan_port = scan_port
        self._retry_port = retry_port
        self._projector = projector
        self._unit_of_work_factory = unit_of_work_factory
        self._reclassification_port = reclassification_port
        self._target_verifier = target_verifier

    def scan_definition(self, request, correlation_id):
        try:
            self._registry.require(request.definition_code)
            page = self._scan_port.scan_definition(request)
            receipts = tuple(
                self._projector.project(item, correlation_id)
                for item in page.root_facts
            )
            return ScanAnomalyDefinitionResult(
                request.definition_code,
                len(receipts),
                sum(item.predicate_active for item in receipts),
                sum(not item.predicate_active for item in receipts),
                page.next_after_source_id,
            )
        except Exception as error:
            if error.__class__.__name__.endswith("Error"):
                raise
            raise AnomalyMaintenanceError(str(error)) from error

    def query_reclassification(
        self,
        request: AnomalyReclassificationCursorPageRequest,
        *,
        eligible_codes: tuple[str, ...],
    ) -> AnomalyReclassificationPage:
        port = self._require_reclassification_port()
        try:
            if not isinstance(request, AnomalyReclassificationCursorPageRequest):
                raise TypeError("reclassification_query_request_invalid")
            eligible_codes = self._validate_eligible_codes(eligible_codes)
            _validate_eligible_cursor(request.after, eligible_codes)
            page = port.query_reclassification_page(
                request, eligible_definitions=eligible_codes
            )
            if not isinstance(page, AnomalyReclassificationPage):
                raise ValueError("reclassification_query_result_invalid")
            if any(item.definition_code not in set(eligible_codes) for item in page.items):
                raise ValueError("anomaly_reclassification_definition_not_eligible")
            _validate_page_after(page, request.after)
            return page
        except ValueError:
            raise
        except Exception as error:
            raise AnomalyMaintenanceError(str(error)) from error

    query_reclassifications = query_reclassification
    query_reclassification_page = query_reclassification

    def preview_reclassification(
        self,
        alert: AnomalyReclassificationAlertIdentity,
        disposition: AnomalyReclassificationDisposition,
        target: AnomalyReclassificationTargetBinding | None,
        actor: ActorContext,
        reason: str,
        evidence_reference: str,
        rulebook_reference: str | None = None,
        release_evidence_reference: str | None = None,
    ) -> AnomalyReclassificationCandidate:
        """Read current alert/target and build a zero-write candidate."""
        port = self._require_reclassification_port()
        verifier = self._require_target_verifier()
        try:
            current = port.load_reclassification_alert(alert, for_update=False)
            if current is None:
                raise ValueError("anomaly_reclassification_alert_not_found")
            if current != alert:
                raise ValueError("anomaly_reclassification_stale_alert")
            _read_target(verifier, target, for_update=False)
            return preview_anomaly_reclassification(
                disposition=disposition,
                alert=current,
                target=target,
                actor=actor,
                reason=reason,
                evidence_reference=evidence_reference,
                rulebook_reference=rulebook_reference,
                release_evidence_reference=release_evidence_reference,
            )
        except ValueError:
            raise
        except Exception as error:
            raise AnomalyMaintenanceError(str(error)) from error

    preview = preview_reclassification
    preview_anomaly_reclassification = preview_reclassification

    def apply_reclassification(
        self, request: AnomalyReclassificationApplyRequest
    ) -> AnomalyReclassificationReceipt:
        """Apply once after fresh locked reads; receipt replay never writes."""
        port = self._require_reclassification_port()
        verifier = self._require_target_verifier()
        if not isinstance(request, AnomalyReclassificationApplyRequest):
            raise TypeError("anomaly_reclassification_apply_request_invalid")
        try:
            with self._unit_of_work_factory() as unit_of_work:
                receipt = self._apply_reclassification_in_uow(port, verifier, request)
                unit_of_work.commit()
                return receipt
        except ValueError:
            raise
        except Exception as error:
            raise AnomalyMaintenanceError(str(error)) from error

    apply = apply_reclassification
    apply_anomaly_reclassification = apply_reclassification

    def run_reclassification_batch(
        self,
        request: AnomalyReclassificationCursorPageRequest,
        *,
        eligible_codes: tuple[str, ...],
        operation_identity: str,
        policy_identity: str,
        policy_fingerprint: PreviewFingerprint,
        actor: ActorContext,
        resolve_candidate: AnomalyReclassificationCandidateResolver,
        correlation_id: CorrelationId | None = None,
    ) -> AnomalyReclassificationResult:
        """Replay a request-only batch receipt before querying mutable alerts."""
        port = self._require_reclassification_port()
        if not isinstance(request, AnomalyReclassificationCursorPageRequest):
            raise TypeError("reclassification_batch_request_invalid")
        eligible_codes = self._validate_eligible_codes(eligible_codes)
        require_canonical_text(operation_identity, "reclassification operation identity", 191)
        require_canonical_text(policy_identity, "reclassification policy identity", 191)
        if not isinstance(policy_fingerprint, PreviewFingerprint):
            raise TypeError("reclassification policy fingerprint is invalid")
        if not isinstance(actor, ActorContext):
            raise TypeError("reclassification runner actor is invalid")
        request_fingerprint = fingerprint_payload(
            {
                "operation_identity": operation_identity,
                "eligible_codes": eligible_codes,
                "maximum_items": request.maximum_items,
                "cursor": _cursor_payload(request.after),
                "policy_identity": policy_identity,
                "policy_fingerprint": policy_fingerprint.value,
                "actor_id": actor.actor_id,
                "actor_scope": actor.permission_scope,
            }
        )
        batch_key = IdempotencyKey(
            _bounded_identity(
                "anomaly-reclassification-batch-key",
                {
                    "operation_identity": operation_identity,
                    "cursor": _cursor_payload(request.after),
                },
            )
        )
        if correlation_id is None:
            correlation_id = CorrelationId(
                _bounded_identity(
                    "anomaly-reclassification-correlation",
                    {
                        "operation_identity": operation_identity,
                        "cursor": _cursor_payload(request.after),
                    },
                )
            )
        batch_request = AnomalyReclassificationBatchRequest(
            operation_identity,
            batch_key,
            request_fingerprint,
            actor,
            correlation_id,
            eligible_codes,
            request.maximum_items,
            request.after,
        )
        with self._unit_of_work_factory() as unit_of_work:
            stored = port.find_reclassification_batch_receipt(
                batch_key, for_update=True
            )
            if stored is not None:
                stored_fingerprint, stored_result = stored
                if stored_fingerprint != request_fingerprint:
                    raise ValueError("anomaly_reclassification_batch_conflict")
                unit_of_work.commit()
                return stored_result
            page = self.query_reclassification(
                request, eligible_codes=eligible_codes
            )
            if not page.items and page.next_cursor is not None:
                raise ValueError("reclassification_cursor_no_progress")
            candidates: list[AnomalyReclassificationCandidate | None] = []
            blocked: list[AnomalyReclassificationBlockedItem] = []
            for alert in page.items:
                try:
                    candidate = resolve_candidate(alert)
                    if not isinstance(candidate, AnomalyReclassificationCandidate):
                        raise ValueError("reclassification_candidate_invalid")
                    if candidate.alert != alert:
                        raise ValueError("reclassification_candidate_alert_mismatch")
                    if candidate.actor != actor:
                        raise ValueError("anomaly_reclassification_actor_mismatch")
                    candidates.append(candidate)
                except ValueError as error:
                    candidates.append(None)
                    blocked.append(_blocked(alert, error))
            savepoint, rollback_to_savepoint, release_savepoint = _require_savepoints(
                unit_of_work
            )
            applied = 0
            before_fingerprints: list[PreviewFingerprint] = []
            after_fingerprints: list[PreviewFingerprint] = []
            verifier = self._require_target_verifier()
            for alert, candidate in zip(page.items, candidates):
                if candidate is None:
                    continue
                token = savepoint()
                try:
                    command = AnomalyReclassificationApplyRequest.from_preview(
                        candidate,
                        idempotency_key=IdempotencyKey(
                            _bounded_identity(
                                "anomaly-reclassification-item-key",
                                {
                                    "operation_identity": operation_identity,
                                    "alert": _item_key_payload(alert),
                                },
                            )
                        ),
                        correlation_id=correlation_id,
                    )
                    receipt = self._apply_reclassification_in_uow(
                        port, verifier, command
                    )
                    applied += 1
                    before_fingerprints.append(receipt.before_state_fingerprint)
                    after_fingerprints.append(receipt.after_state_fingerprint)
                    release_savepoint(token)
                except ValueError as error:
                    rollback_to_savepoint(token)
                    release_savepoint(token)
                    blocked.append(_blocked(alert, error))
            blocked.sort(key=lambda item: (item.definition_code, item.source_identity))
            result = AnomalyReclassificationResult(
                len(page.items), applied, tuple(blocked), page.next_cursor, None
            )
            batch_identity = port.save_reclassification_batch_receipt(
                batch_request, result, tuple(before_fingerprints), tuple(after_fingerprints)
            )
            if not isinstance(batch_identity, str):
                raise ValueError("anomaly_reclassification_batch_receipt_invalid")
            require_canonical_text(batch_identity, "batch receipt identity", 191)
            unit_of_work.commit()
            return replace(result, batch_receipt_identity=batch_identity)

    run_batch = run_reclassification_batch
    run_reclassification = run_reclassification_batch

    def _apply_reclassification_in_uow(
        self,
        port: AnomalyReclassificationRepository,
        verifier: AnomalyReclassificationTargetVerifier,
        request: AnomalyReclassificationApplyRequest,
    ) -> AnomalyReclassificationReceipt:
        stored = port.find_reclassification_receipt(
            request.idempotency_key, for_update=True
        )
        if stored is not None:
            stored_fingerprint, stored_receipt = stored
            if stored_fingerprint != request.preview_fingerprint:
                raise ValueError("anomaly_reclassification_idempotency_conflict")
            return replace(stored_receipt, replayed=True)

        current = port.load_reclassification_alert(request.alert, for_update=True)
        if current is None:
            raise ValueError("anomaly_reclassification_stale_alert")
        if current != request.alert:
            raise ValueError("anomaly_reclassification_stale_alert")
        _read_target(verifier, request.target, for_update=True)
        candidate = preview_anomaly_reclassification(
            disposition=request.disposition,
            alert=current,
            target=request.target,
            actor=request.actor,
            reason=request.reason,
            evidence_reference=request.evidence_reference,
            rulebook_reference=request.rulebook_reference,
            release_evidence_reference=request.release_evidence_reference,
        )
        if candidate.fingerprint != request.preview_fingerprint:
            raise ValueError("anomaly_reclassification_preview_stale")
        receipt = port.persist_reclassification(request, candidate)
        if not isinstance(receipt, AnomalyReclassificationReceipt):
            raise ValueError("anomaly_reclassification_receipt_invalid")
        if receipt.alert != current or receipt.resulting_predicate_active:
            raise ValueError("anomaly_reclassification_readback_invalid")
        return receipt

    def _require_reclassification_port(self) -> AnomalyReclassificationRepository:
        if self._reclassification_port is None:
            raise ValueError("anomaly_reclassification_port_unavailable")
        return self._reclassification_port

    def _validate_eligible_codes(self, eligible_codes):
        try:
            allowed = tuple(self._registry.reclassification_codes())
        except AttributeError as error:
            raise ValueError("anomaly_reclassification_registry_contract_missing") from error
        if allowed != tuple(sorted(set(allowed))) or not allowed:
            raise ValueError("anomaly_reclassification_registry_contract_invalid")
        if not isinstance(eligible_codes, tuple):
            raise ValueError("anomaly_reclassification_eligible_codes_invalid")
        if eligible_codes != tuple(sorted(set(eligible_codes))) or not eligible_codes:
            raise ValueError("anomaly_reclassification_eligible_codes_invalid")
        if any(code not in allowed for code in eligible_codes):
            raise ValueError("anomaly_reclassification_eligible_codes_not_allowed")
        return eligible_codes

    def _require_target_verifier(self) -> AnomalyReclassificationTargetVerifier:
        if self._target_verifier is None:
            raise ValueError("anomaly_reclassification_target_verifier_unavailable")
        return self._target_verifier

    def retry_projector(self, request, correlation_id):
        del correlation_id
        try:
            with self._unit_of_work_factory() as unit_of_work:
                event_ids = tuple(
                    self._retry_port.requeue_failed_projector_events(
                        request.maximum_events
                    )
                )
                unit_of_work.commit()
            return RetryAnomalyProjectorResult("anomaly-root-fact-projector-v1", event_ids)
        except Exception as error:
            raise AnomalyMaintenanceError(str(error)) from error

    def query_dead_letters(self, maximum_items):
        try:
            return tuple(self._retry_port.query_dead_letters(maximum_items))
        except Exception as error:
            raise AnomalyMaintenanceError(str(error)) from error

    def preview_dead_letter_retry(self, identity, reason, evidence_reference):
        try:
            dead_letter = self._retry_port.load_dead_letter(identity, for_update=False)
            if dead_letter is None:
                raise ValueError("projector_dead_letter_not_found")
            return preview_projector_dead_letter_retry(
                dead_letter, reason, evidence_reference
            )
        except Exception as error:
            if isinstance(error, ValueError):
                raise
            raise AnomalyMaintenanceError(str(error)) from error

    def preview_dead_letter_supersede(self, identity, reason, evidence_reference):
        try:
            dead_letter = self._retry_port.load_dead_letter_with_successor(
                identity, for_update=False
            )
            if dead_letter is None:
                raise ValueError("projector_dead_letter_not_found")
            return preview_projector_dead_letter_supersede(
                dead_letter, reason, evidence_reference
            )
        except Exception as error:
            if isinstance(error, ValueError):
                raise
            raise AnomalyMaintenanceError(str(error)) from error

    def apply_dead_letter_retry(self, request):
        try:
            with self._unit_of_work_factory() as unit_of_work:
                stored = self._retry_port.load_dead_letter_retry_receipt(
                    request.idempotency_key.value, for_update=True
                )
                if stored is not None:
                    stored_fingerprint, stored_receipt = stored
                    if stored_fingerprint != request.preview_fingerprint:
                        raise ValueError("idempotency_conflict")
                    unit_of_work.commit()
                    return replace(stored_receipt, replayed=True)
                dead_letter = self._retry_port.load_dead_letter(
                    request.identity, for_update=True
                )
                if dead_letter is None:
                    raise ValueError("projector_dead_letter_not_found")
                if dead_letter.attempt_count != request.expected_attempt_count:
                    raise ValueError("projector_dead_letter_stale")
                preview = preview_projector_dead_letter_retry(
                    dead_letter, request.reason, request.evidence_reference
                )
                if preview.fingerprint != request.preview_fingerprint:
                    raise ValueError("projector_dead_letter_preview_stale")
                receipt = RetryProjectorDeadLetterReceipt(
                    ProjectorDeadLetterIdentity(
                        dead_letter.identity.projector_identity,
                        dead_letter.identity.event_id,
                    ),
                    dead_letter.attempt_count,
                    "pending",
                    f"anomaly-projector-retry:{request.idempotency_key.value}",
                )
                self._retry_port.requeue_dead_letter(dead_letter)
                self._retry_port.save_dead_letter_retry_receipt(
                    request, preview.fingerprint, receipt
                )
                unit_of_work.commit()
            return receipt
        except Exception as error:
            if isinstance(error, ValueError):
                raise
            raise AnomalyMaintenanceError(str(error)) from error

    def apply_dead_letter_supersede(self, request):
        try:
            with self._unit_of_work_factory() as unit_of_work:
                stored = self._retry_port.load_dead_letter_supersede_receipt(
                    request.idempotency_key.value, for_update=True
                )
                if stored is not None:
                    stored_fingerprint, stored_receipt = stored
                    if stored_fingerprint != request.preview_fingerprint:
                        raise ValueError("idempotency_conflict")
                    unit_of_work.commit()
                    return replace(stored_receipt, replayed=True)
                dead_letter = self._retry_port.load_dead_letter_with_successor(
                    request.identity, for_update=True
                )
                if dead_letter is None:
                    raise ValueError("projector_dead_letter_not_found")
                if dead_letter.attempt_count != request.expected_attempt_count:
                    raise ValueError("projector_dead_letter_stale")
                successor = dead_letter.successor
                if successor is None:
                    raise ValueError("projector_dead_letter_successor_not_verified")
                if (
                    successor.event_id != request.expected_successor_event_id
                    or successor.source_version
                    != request.expected_successor_source_version
                ):
                    raise ValueError("projector_dead_letter_successor_stale")
                preview = preview_projector_dead_letter_supersede(
                    dead_letter, request.reason, request.evidence_reference
                )
                if preview.fingerprint != request.preview_fingerprint:
                    raise ValueError("projector_dead_letter_preview_stale")
                receipt = SupersedeProjectorDeadLetterReceipt(
                    ProjectorDeadLetterIdentity(
                        dead_letter.identity.projector_identity,
                        dead_letter.identity.event_id,
                    ),
                    successor.event_id,
                    successor.source_version,
                    "superseded_by_verified_successor",
                    f"anomaly-projector-supersede:{request.idempotency_key.value}",
                )
                self._retry_port.save_dead_letter_supersede_receipt(
                    request, preview.fingerprint, receipt
                )
                unit_of_work.commit()
            return receipt
        except Exception as error:
            if isinstance(error, ValueError):
                raise
            raise AnomalyMaintenanceError(str(error)) from error


def _read_target(port, target, *, for_update):
    if target is None:
        return None
    current = port.load_reclassification_target(target, for_update=for_update)
    if current is None:
        raise ValueError("anomaly_reclassification_target_not_found")
    if current != target:
        raise ValueError("anomaly_reclassification_stale_target")
    return current


def _require_savepoints(unit_of_work):
    savepoint = getattr(unit_of_work, "savepoint", None)
    rollback_to_savepoint = getattr(unit_of_work, "rollback_to_savepoint", None)
    release_savepoint = getattr(unit_of_work, "release_savepoint", None)
    if not all(
        callable(item)
        for item in (savepoint, rollback_to_savepoint, release_savepoint)
    ):
        raise ValueError("anomaly_reclassification_savepoint_unavailable")
    return savepoint, rollback_to_savepoint, release_savepoint


def _validate_page_after(page, after):
    if after is None or not page.items:
        return
    if _item_key(page.items[0]) <= after.key:
        raise ValueError("reclassification_cursor_not_advanced")


def _validate_eligible_cursor(cursor, eligible_codes):
    if cursor is not None and cursor.definition_code not in set(eligible_codes):
        raise ValueError("anomaly_reclassification_definition_not_eligible")


def _item_key(alert):
    return alert.definition_code, alert.source_identity


def _item_key_payload(alert):
    return {
        "definition_code": alert.definition_code,
        "source_identity": alert.source_identity,
        "source_version": alert.source_version,
        "workflow_version": alert.workflow_version,
        "alert_fingerprint": alert.alert_fingerprint.value,
    }


def _cursor_payload(cursor: AnomalyReclassificationCursor | None):
    return (
        None
        if cursor is None
        else {
            "definition_code": cursor.definition_code,
            "source_identity": cursor.source_identity,
        }
    )


def _item_operation_key(operation_identity, alert):
    return _bounded_identity(
        "anomaly-reclassification-item-key",
        {
            "operation_identity": operation_identity,
            "alert": _item_key_payload(alert),
        },
    )


def _bounded_identity(prefix, payload):
    canonical = fingerprint_payload(payload).value
    return f"{prefix}:{canonical}"


def _blocked(alert, error):
    reason = str(error) or "reclassification_blocked"
    return AnomalyReclassificationBlockedItem(
        alert.definition_code,
        alert.source_identity,
        reason[:500],
        alert.alert_fingerprint,
    )


def _batch_receipt_identity(request):
    return f"anomaly-reclassification-batch:{request.idempotency_key.value}"


__all__ = [
    "AnomalyMaintenanceApplication",
    "AnomalyMaintenanceError",
    "AnomalyReclassificationBatchRequest",
    "AnomalyReclassificationCandidateResolver",
    "AnomalyReclassificationRepository",
    "AnomalyReclassificationSavepointUnitOfWork",
    "AnomalyReclassificationTargetVerifier",
]
