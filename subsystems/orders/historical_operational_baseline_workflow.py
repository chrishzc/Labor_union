"""
File: historical_operational_baseline_workflow.py
Description: 協調歷史作業基準的 Query、Preview、Apply、重播與 outbox。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Callable, Protocol

from domains.orders.historical_operational_baseline import (
    HistoricalBaselineEvidenceMode,
    HistoricalOperationalBaselineCandidate,
    HistoricalOperationalBaselineError,
    HistoricalOperationalBaselineFacts,
    HistoricalOperationalBaselineRequest,
    HistoricalOrderIdentity,
    build_historical_operational_baseline_candidate,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.ports import OutboxIntent, UnitOfWork
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer


@dataclass(frozen=True, slots=True)
class HistoricalOperationalBaselineQuery:
    """Read-only projection of facts used by the baseline command."""

    facts: HistoricalOperationalBaselineFacts


@dataclass(frozen=True, slots=True)
class HistoricalOperationalBaselinePreview:
    candidate: HistoricalOperationalBaselineCandidate
    expected_orders_version: ExpectedVersion
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ApplyHistoricalOperationalBaseline:
    identity: HistoricalOrderIdentity
    selected_step: int
    expected_orders_version: ExpectedVersion
    expected_owner_binding_fingerprint: PreviewFingerprint
    evidence_mode: HistoricalBaselineEvidenceMode
    reason: str
    evidence_reference: str
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    correlation_id: CorrelationId
    document_kind: str | None = None
    affected_steps: tuple[int, ...] | None = None


# A descriptive alias for callers that use request terminology.
HistoricalOperationalBaselineApplyRequest = ApplyHistoricalOperationalBaseline
HistoricalOperationalBaselineCommand = ApplyHistoricalOperationalBaseline


@dataclass(frozen=True, slots=True)
class HistoricalOperationalBaselinePersisted:
    baseline_event_identity: str
    receipt_identity: str
    resulting_orders_version: int

    def __post_init__(self) -> None:
        require_canonical_text(
            self.baseline_event_identity,
            "baseline event identity",
            191,
        )
        require_canonical_text(self.receipt_identity, "baseline receipt identity", 191)
        require_nonnegative_integer(
            self.resulting_orders_version, "baseline resulting Orders version"
        )


@dataclass(frozen=True, slots=True)
class HistoricalOperationalBaselineReceipt:
    identity: HistoricalOrderIdentity
    baseline_event_identity: str
    receipt_identity: str
    selected_step: int
    resulting_orders_version: int
    preview_fingerprint: PreviewFingerprint
    command_fingerprint: PreviewFingerprint
    replayed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.identity, HistoricalOrderIdentity):
            raise TypeError("baseline identity is invalid")
        require_canonical_text(self.baseline_event_identity, "baseline event identity", 191)
        require_canonical_text(self.receipt_identity, "baseline receipt identity", 191)
        if isinstance(self.selected_step, bool) or not 1 <= self.selected_step <= 11:
            raise ValueError("baseline selected step is invalid")
        require_nonnegative_integer(
            self.resulting_orders_version, "baseline resulting Orders version"
        )
        if not isinstance(self.preview_fingerprint, PreviewFingerprint):
            raise TypeError("baseline preview fingerprint is invalid")
        if not isinstance(self.command_fingerprint, PreviewFingerprint):
            raise TypeError("baseline command fingerprint is invalid")


@dataclass(frozen=True, slots=True)
class StoredHistoricalOperationalBaselineReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: HistoricalOperationalBaselineReceipt


class HistoricalOperationalBaselineRepository(Protocol):
    """Typed ports; all methods run inside the workflow-owned transaction when applying."""

    def load_facts(
        self, identity: HistoricalOrderIdentity, *, for_update: bool
    ) -> HistoricalOperationalBaselineFacts | None: ...

    def find_receipt(
        self, key: IdempotencyKey, *, for_update: bool
    ) -> StoredHistoricalOperationalBaselineReceipt | None: ...

    def append_baseline(
        self,
        command: ApplyHistoricalOperationalBaseline,
        candidate: HistoricalOperationalBaselineCandidate,
        command_fingerprint: PreviewFingerprint,
    ) -> HistoricalOperationalBaselinePersisted: ...

    def save_receipt(
        self,
        key: IdempotencyKey,
        stored: StoredHistoricalOperationalBaselineReceipt,
    ) -> None: ...


class HistoricalOperationalBaselineOutbox(Protocol):
    """Appends a durable intent without opening, committing, or rolling back a transaction."""

    def append(self, intent: OutboxIntent) -> int: ...


class HistoricalOperationalBaselineWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.code)
        self.error = error


class HistoricalOperationalBaselineWorkflow:
    def __init__(
        self,
        repository: HistoricalOperationalBaselineRepository,
        outbox: HistoricalOperationalBaselineOutbox,
        unit_of_work_factory: Callable[[], UnitOfWork],
    ) -> None:
        self._repository = repository
        self._outbox = outbox
        self._unit_of_work_factory = unit_of_work_factory

    def query(
        self,
        identity: HistoricalOrderIdentity,
        correlation_id: CorrelationId,
    ) -> HistoricalOperationalBaselineQuery:
        facts = self._repository.load_facts(identity, for_update=False)
        if facts is None:
            raise _workflow_error(
                ErrorCategory.NOT_FOUND,
                "historical_operational_baseline_not_found",
                "找不到歷史訂單作業基準 facts。",
                correlation_id,
            )
        return HistoricalOperationalBaselineQuery(facts)

    def preview(
        self,
        request: HistoricalOperationalBaselineRequest,
        actor: ActorContext,
        correlation_id: CorrelationId,
    ) -> HistoricalOperationalBaselinePreview:
        """Build a candidate from an unlocked read; this method performs no writes."""

        facts = self._repository.load_facts(request.identity, for_update=False)
        if facts is None:
            raise _workflow_error(
                ErrorCategory.NOT_FOUND,
                "historical_operational_baseline_not_found",
                "找不到歷史訂單作業基準 facts。",
                correlation_id,
            )
        try:
            candidate = build_historical_operational_baseline_candidate(facts, request)
        except (HistoricalOperationalBaselineError, TypeError, ValueError) as error:
            raise _map_domain_error(correlation_id, error) from error
        return _preview(candidate, request, actor)

    def apply(
        self, command: ApplyHistoricalOperationalBaseline
    ) -> HistoricalOperationalBaselineReceipt:
        command_fingerprint = historical_operational_baseline_command_fingerprint(command)
        try:
            with self._unit_of_work_factory() as unit_of_work:
                try:
                    stored = self._repository.find_receipt(
                        command.idempotency_key, for_update=True
                    )
                    if stored is not None:
                        if stored.command_fingerprint != command_fingerprint:
                            raise _workflow_error(
                                ErrorCategory.IDEMPOTENCY_MISMATCH,
                                "historical_operational_baseline_idempotency_mismatch",
                                "同一 idempotency key 對應不同歷史作業基準命令。",
                                command.correlation_id,
                            )
                        replayed = replace(stored.receipt, replayed=True)
                        unit_of_work.commit()
                        return replayed

                    facts = self._repository.load_facts(command.identity, for_update=True)
                    if facts is None:
                        raise _workflow_error(
                            ErrorCategory.NOT_FOUND,
                            "historical_operational_baseline_not_found",
                            "找不到歷史訂單作業基準 facts。",
                            command.correlation_id,
                        )
                    request = _request(command)
                    try:
                        candidate = build_historical_operational_baseline_candidate(
                            facts, request
                        )
                    except (HistoricalOperationalBaselineError, TypeError, ValueError) as error:
                        raise _map_domain_error(command.correlation_id, error) from error
                    preview = _preview(candidate, request, command.actor)
                    if preview.fingerprint != command.preview_fingerprint:
                        raise _workflow_error(
                            ErrorCategory.CONFLICT,
                            "historical_operational_baseline_preview_stale",
                            "歷史訂單作業基準在 Preview 後已變更，請重新查詢與 Preview。",
                            command.correlation_id,
                            current_version=ExpectedVersion(facts.current_orders_version),
                        )
                    persisted = self._repository.append_baseline(
                        command, candidate, command_fingerprint
                    )
                    receipt = _receipt(command, candidate, persisted, command_fingerprint, preview)
                    _validate_persisted_receipt(receipt, candidate, persisted, preview)
                    self._repository.save_receipt(
                        command.idempotency_key,
                        StoredHistoricalOperationalBaselineReceipt(
                            command_fingerprint, receipt
                        ),
                    )
                    self._outbox.append(_outbox_intent(command, candidate, receipt))
                    unit_of_work.commit()
                    return receipt
                except HistoricalOperationalBaselineWorkflowError:
                    unit_of_work.rollback()
                    raise
                except Exception as error:
                    unit_of_work.rollback()
                    raise _workflow_error(
                        ErrorCategory.INTERNAL,
                        "historical_operational_baseline_transaction_failed",
                        "歷史訂單作業基準交易失敗。",
                        command.correlation_id,
                    ) from error
        except HistoricalOperationalBaselineWorkflowError:
            raise


def _request(command: ApplyHistoricalOperationalBaseline) -> HistoricalOperationalBaselineRequest:
    return HistoricalOperationalBaselineRequest(
        command.identity,
        command.selected_step,
        command.expected_orders_version.value,
        command.expected_owner_binding_fingerprint,
        command.evidence_mode,
        command.reason,
        command.evidence_reference,
        command.document_kind,
        command.affected_steps,
    )


def _preview(
    candidate: HistoricalOperationalBaselineCandidate,
    request: HistoricalOperationalBaselineRequest,
    actor: ActorContext,
) -> HistoricalOperationalBaselinePreview:
    fingerprint = fingerprint_payload(
        {
            "candidate": candidate.fingerprint.value,
            "actor": actor.actor_id,
            "permission_scope": actor.permission_scope,
            "evidence_mode": request.evidence_mode.value,
            "reason": request.reason,
            "evidence_reference": request.evidence_reference,
        }
    )
    return HistoricalOperationalBaselinePreview(
        candidate,
        ExpectedVersion(candidate.current_orders_version),
        fingerprint,
    )


def _receipt(
    command: ApplyHistoricalOperationalBaseline,
    candidate: HistoricalOperationalBaselineCandidate,
    persisted: HistoricalOperationalBaselinePersisted,
    command_fingerprint: PreviewFingerprint,
    preview: HistoricalOperationalBaselinePreview,
) -> HistoricalOperationalBaselineReceipt:
    return HistoricalOperationalBaselineReceipt(
        command.identity,
        persisted.baseline_event_identity,
        persisted.receipt_identity,
        candidate.selected_step,
        persisted.resulting_orders_version,
        preview.fingerprint,
        command_fingerprint,
    )


def _validate_persisted_receipt(
    receipt: HistoricalOperationalBaselineReceipt,
    candidate: HistoricalOperationalBaselineCandidate,
    persisted: HistoricalOperationalBaselinePersisted,
    preview: HistoricalOperationalBaselinePreview,
) -> None:
    if receipt.identity != candidate.identity:
        raise ValueError("historical_operational_baseline_persisted_identity_mismatch")
    if receipt.baseline_event_identity != persisted.baseline_event_identity:
        raise ValueError("historical_operational_baseline_event_identity_mismatch")
    if receipt.selected_step != candidate.selected_step:
        raise ValueError("historical_operational_baseline_persisted_step_mismatch")
    if receipt.resulting_orders_version != candidate.current_orders_version:
        raise ValueError("historical_operational_baseline_persisted_version_mismatch")
    if receipt.preview_fingerprint != preview.fingerprint:
        raise ValueError("historical_operational_baseline_persisted_preview_mismatch")
    if receipt.replayed:
        raise ValueError("historical_operational_baseline_unexpected_replay")


def _outbox_intent(
    command: ApplyHistoricalOperationalBaseline,
    candidate: HistoricalOperationalBaselineCandidate,
    receipt: HistoricalOperationalBaselineReceipt,
) -> OutboxIntent:
    payload = json.dumps(
        {
            "baseline_event_identity": receipt.baseline_event_identity,
            "receipt_identity": receipt.receipt_identity,
            "candidate": candidate.canonical_payload,
            "selected_step": candidate.selected_step,
            "resulting_orders_version": receipt.resulting_orders_version,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return OutboxIntent(
        "orders.historical_operational_baseline",
        command.identity.order_identity,
        "historical_operational_baseline_confirmed",
        payload,
        command.idempotency_key.value,
    )


def historical_operational_baseline_command_fingerprint(
    command: ApplyHistoricalOperationalBaseline,
) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "command_type": "historical_operational_baseline.apply",
            "command_version": 1,
            "order_identity": command.identity.order_identity,
            "case_no": command.identity.case_no,
            "selected_step": command.selected_step,
            "expected_orders_version": command.expected_orders_version.value,
            "expected_owner_binding_fingerprint": command.expected_owner_binding_fingerprint.value,
            "evidence_mode": command.evidence_mode.value,
            "reason": command.reason,
            "evidence_reference": command.evidence_reference,
            "document_kind": command.document_kind,
            "affected_steps": command.affected_steps,
            "preview_fingerprint": command.preview_fingerprint.value,
            "submitted_by": command.actor.actor_id,
            "permission_scope": command.actor.permission_scope,
        }
    )


def _map_domain_error(
    correlation_id: CorrelationId, error: Exception
) -> HistoricalOperationalBaselineWorkflowError:
    code = str(getattr(error, "code", error))
    if code in {
        "historical_baseline_stale",
        "historical_baseline_version_rollback",
        "historical_baseline_binding_drift",
        "historical_baseline_identity_mismatch",
        "historical_baseline_prior_identity_mismatch",
        "historical_baseline_prior_binding_conflict",
        "historical_baseline_step_regression",
        "historical_baseline_version_mismatch",
    }:
        category = ErrorCategory.CONFLICT
    elif code.startswith("historical_baseline_"):
        category = ErrorCategory.VALIDATION
    else:
        category = ErrorCategory.INTERNAL
    return _workflow_error(
        category,
        code,
        "歷史訂單作業基準候選不符合目前根事實。",
        correlation_id,
    )


def _workflow_error(
    category: ErrorCategory,
    code: str,
    message: str,
    correlation_id: CorrelationId,
    *,
    current_version: ExpectedVersion | None = None,
) -> HistoricalOperationalBaselineWorkflowError:
    return HistoricalOperationalBaselineWorkflowError(
        TypedError(
            category,
            code,
            message,
            correlation_id,
            domain_blockers=(code,) if category is ErrorCategory.DOMAIN_BLOCKED else (),
            current_version=current_version,
        )
    )


__all__ = [
    "ApplyHistoricalOperationalBaseline",
    "HistoricalOperationalBaselineApplyRequest",
    "HistoricalOperationalBaselineCommand",
    "HistoricalOperationalBaselineOutbox",
    "HistoricalOperationalBaselinePersisted",
    "HistoricalOperationalBaselinePreview",
    "HistoricalOperationalBaselineQuery",
    "HistoricalOperationalBaselineReceipt",
    "HistoricalOperationalBaselineRepository",
    "HistoricalOperationalBaselineWorkflow",
    "HistoricalOperationalBaselineWorkflowError",
    "StoredHistoricalOperationalBaselineReceipt",
    "historical_operational_baseline_command_fingerprint",
]
