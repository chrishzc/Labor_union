"""
File: historical_review_remediation_workflow.py
Description: 協調歷史 review 更正的 Query、零寫入 Preview、Apply 與 replay。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from domains.orders.historical_review_remediation import (
    HistoricalReviewContext,
    HistoricalReviewCorrectionCandidate,
    HistoricalReviewCorrectionSource,
    build_correction_candidate,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_canonical_text
from subsystems.orders.historical_order_workbook import load_historical_order_workbook


@dataclass(frozen=True, slots=True)
class HistoricalReviewRemediationQuery:
    context: HistoricalReviewContext


@dataclass(frozen=True, slots=True)
class HistoricalReviewRemediationPreview:
    context: HistoricalReviewContext
    candidate: HistoricalReviewCorrectionCandidate
    expected_review_version: ExpectedVersion
    expected_remediation_version: ExpectedVersion
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ApplyHistoricalReviewRemediation:
    prior_review_identity: str
    source_path: str
    expected_review_version: ExpectedVersion
    expected_remediation_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    evidence: tuple[str, ...]
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.prior_review_identity, "prior review identity", 191)
        require_canonical_text(self.reason, "remediation reason", 500)
        if not self.evidence:
            raise ValueError("historical_order_remediation_evidence_required")
        normalized = tuple(require_canonical_text(item, "remediation evidence", 500) for item in self.evidence)
        if normalized != tuple(sorted(set(normalized))):
            raise ValueError("historical_order_remediation_evidence_not_canonical")


@dataclass(frozen=True, slots=True)
class HistoricalReviewRemediationReceipt:
    prior_review_identity: str
    remediation_receipt_identity: str
    disposition: str
    successor_review_identity: str | None
    source_content_digest: str
    resulting_remediation_version: int
    preview_fingerprint: PreviewFingerprint
    replayed: bool


class HistoricalReviewRemediationWorkflowError(Exception):
    def __init__(self, error: TypedError):
        super().__init__(error.code)
        self.error = error


class HistoricalReviewRemediationRepository(Protocol):
    def load_context(self, review_identity: str, *, for_update: bool) -> HistoricalReviewContext | None: ...
    def evaluate_source(
        self,
        context: HistoricalReviewContext,
        source: HistoricalReviewCorrectionSource,
        *,
        for_update: bool,
    ) -> HistoricalReviewCorrectionSource: ...
    def find_receipt(self, key: IdempotencyKey) -> tuple[PreviewFingerprint, HistoricalReviewRemediationReceipt] | None: ...
    def persist(
        self,
        command: ApplyHistoricalReviewRemediation,
        context: HistoricalReviewContext,
        candidate: HistoricalReviewCorrectionCandidate,
    ) -> HistoricalReviewRemediationReceipt: ...


class HistoricalReviewRemediationWorkflow:
    def __init__(self, repository: HistoricalReviewRemediationRepository, unit_of_work_factory: Callable[[], UnitOfWork]):
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query(self, review_identity: str, correlation_id: CorrelationId) -> HistoricalReviewRemediationQuery:
        context = self._repository.load_context(review_identity, for_update=False)
        if context is None:
            raise _error(ErrorCategory.NOT_FOUND, "historical_order_review_not_found", "找不到歷史訂單 review。", correlation_id)
        return HistoricalReviewRemediationQuery(context)

    def preview(
        self,
        review_identity: str,
        source_path: str | Path,
        expected_review_version: ExpectedVersion,
        expected_remediation_version: ExpectedVersion,
        actor: ActorContext,
        reason: str,
        evidence: tuple[str, ...],
        correlation_id: CorrelationId,
    ) -> HistoricalReviewRemediationPreview:
        with self._unit_of_work_factory() as unit_of_work:
            context = self._repository.load_context(review_identity, for_update=True)
            if context is None:
                raise _error(ErrorCategory.NOT_FOUND, "historical_order_review_not_found", "找不到歷史訂單 review。", correlation_id)
            _check_preview_inputs(
                context,
                expected_review_version,
                expected_remediation_version,
                reason,
                evidence,
                correlation_id,
            )
            source = self._repository.evaluate_source(
                context, _source(source_path), for_update=True
            )
            candidate = build_correction_candidate(context, source)
            preview = _preview(context, candidate, actor, reason, evidence)
            unit_of_work.rollback()
            return preview

    def apply(self, command: ApplyHistoricalReviewRemediation) -> HistoricalReviewRemediationReceipt:
        raw_source = _source(command.source_path)
        command_fingerprint = historical_review_remediation_command_fingerprint(
            command, raw_source
        )
        with self._unit_of_work_factory() as unit_of_work:
            stored = self._repository.find_receipt(command.idempotency_key)
            if stored is not None:
                if stored[0] != command_fingerprint:
                    raise _error(ErrorCategory.IDEMPOTENCY_MISMATCH, "historical_order_remediation_idempotency_conflict", "同一 idempotency key 對應不同更正內容。", command.correlation_id)
                unit_of_work.commit()
                return _replayed(stored[1])
            context = self._repository.load_context(command.prior_review_identity, for_update=True)
            if context is None:
                raise _error(ErrorCategory.NOT_FOUND, "historical_order_review_not_found", "找不到歷史訂單 review。", command.correlation_id)
            _check_versions(command, context)
            source = self._repository.evaluate_source(
                context, raw_source, for_update=True
            )
            candidate = build_correction_candidate(context, source)
            preview = _preview(
                context, candidate, command.actor, command.reason, command.evidence
            )
            if preview.fingerprint != command.preview_fingerprint:
                raise _error(ErrorCategory.CONFLICT, "historical_order_remediation_preview_stale", "來源或 review 已在 Preview 後變更，請重新查詢。", command.correlation_id)
            receipt = self._repository.persist(command, context, candidate)
            unit_of_work.commit()
            return receipt


def _source(path: str | Path) -> HistoricalReviewCorrectionSource:
    workbook = load_historical_order_workbook(path)
    if len(workbook.rows) != 1:
        raise ValueError("historical_order_correction_workbook_must_have_one_row")
    row = workbook.rows[0]
    return HistoricalReviewCorrectionSource(
        workbook.content_digest,
        row.source_identity,
        row.source_fingerprint,
        row.case_no,
        row.client_name,
        row.issue_codes,
        row,
    )


def _preview(context, candidate, actor, reason, evidence):
    return HistoricalReviewRemediationPreview(
        context,
        candidate,
        ExpectedVersion(context.review_version),
        ExpectedVersion(context.remediation_version),
        fingerprint_payload({
            "candidate": candidate.fingerprint.value,
            "review_version": context.review_version,
            "remediation_version": context.remediation_version,
            "actor": actor.actor_id,
            "actor_capabilities": actor.permission_scope,
            "reason": reason,
            "evidence": evidence,
        }),
    )


def historical_review_remediation_command_fingerprint(command, source):
    return fingerprint_payload({
        "prior_review_identity": command.prior_review_identity,
        "source_content_digest": source.workbook_digest,
        "source_identity": source.source_identity,
        "source_fingerprint": source.source_fingerprint,
        "expected_review_version": command.expected_review_version.value,
        "expected_remediation_version": command.expected_remediation_version.value,
        "preview_fingerprint": command.preview_fingerprint.value,
        "actor": command.actor.actor_id,
        "actor_capabilities": command.actor.permission_scope,
        "reason": command.reason,
        "evidence": command.evidence,
    })


def _check_preview_inputs(
    context,
    expected_review_version,
    expected_remediation_version,
    reason,
    evidence,
    correlation_id,
):
    if (
        expected_review_version.value != context.review_version
        or expected_remediation_version.value != context.remediation_version
    ):
        raise _error(
            ErrorCategory.CONFLICT,
            "historical_order_remediation_stale",
            "歷史 review 已變更，請重新查詢與 Preview。",
            correlation_id,
            current_version=ExpectedVersion(context.remediation_version),
        )
    if not reason.strip() or not evidence:
        raise _error(
            ErrorCategory.VALIDATION,
            "historical_order_remediation_evidence_required",
            "人工更正 Preview 必須提供理由與佐證。",
            correlation_id,
        )


def _check_versions(command, context):
    if command.expected_review_version.value != context.review_version or command.expected_remediation_version.value != context.remediation_version:
        raise _error(ErrorCategory.CONFLICT, "historical_order_remediation_stale", "歷史 review 已變更，請重新查詢與 Preview。", command.correlation_id, current_version=ExpectedVersion(context.remediation_version))
    if not command.reason.strip() or not command.evidence:
        raise _error(ErrorCategory.VALIDATION, "historical_order_remediation_evidence_required", "人工更正必須提供理由與佐證。", command.correlation_id)


def _replayed(receipt):
    return HistoricalReviewRemediationReceipt(
        receipt.prior_review_identity,
        receipt.remediation_receipt_identity,
        receipt.disposition,
        receipt.successor_review_identity,
        receipt.source_content_digest,
        receipt.resulting_remediation_version,
        receipt.preview_fingerprint,
        True,
    )


def _error(category, code, message, correlation_id, *, current_version=None):
    return HistoricalReviewRemediationWorkflowError(TypedError(category, code, message, correlation_id, current_version=current_version))


__all__ = [
    "ApplyHistoricalReviewRemediation",
    "HistoricalReviewRemediationPreview",
    "HistoricalReviewRemediationQuery",
    "HistoricalReviewRemediationReceipt",
    "HistoricalReviewRemediationRepository",
    "HistoricalReviewRemediationWorkflow",
    "HistoricalReviewRemediationWorkflowError",
    "historical_review_remediation_command_fingerprint",
]
