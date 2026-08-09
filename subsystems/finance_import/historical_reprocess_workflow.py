"""Typed, all-or-nothing Historical Finance Import reprocess workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from domains.finance_import.planning import (
    CanonicalFinanceImportRow,
    FinanceClassificationType,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer
from subsystems.finance_import.import_workflow import (
    FinanceDispatchOutcome,
    FinanceImportDispatchResult,
)


@dataclass(frozen=True, slots=True)
class HistoricalReprocessRow:
    row_identity: str
    before_classification: FinanceClassificationType
    after: CanonicalFinanceImportRow
    owner_selection: "HistoricalOwnerSelection | None" = None

    def __post_init__(self) -> None:
        require_canonical_text(self.row_identity, "reprocess row identity", 191)
        if self.after.row_identity != self.row_identity:
            raise ValueError("reprocess_row_identity_mismatch")
        if self.before_classification is not FinanceClassificationType.NON_BUSINESS_REVIEW:
            raise ValueError("reprocess_row_is_not_eligible")
        if self.after.classification_type is FinanceClassificationType.NON_BUSINESS_REVIEW:
            raise ValueError("reprocess_owner_not_resolved")
        if self.owner_selection is not None and self.owner_selection.row_identity != self.row_identity:
            raise ValueError("historical_owner_selection_row_mismatch")


@dataclass(frozen=True, slots=True)
class HistoricalOwnerSelection:
    """Append-only human case evidence; it never changes a bank root fact."""

    row_identity: str
    case_no: str
    obligation_identity: str
    reason: str
    evidence_references: tuple[str, ...]

    def __post_init__(self) -> None:
        require_canonical_text(self.row_identity, "bank row identity", 191)
        require_canonical_text(self.case_no, "owner case number", 50)
        require_canonical_text(self.obligation_identity, "owner obligation identity", 191)
        require_canonical_text(self.reason, "owner selection reason", 500)
        if not self.evidence_references:
            raise ValueError("historical_owner_evidence_required")
        for reference in self.evidence_references:
            require_canonical_text(reference, "owner evidence reference", 500)
        if self.evidence_references != tuple(sorted(set(self.evidence_references))):
            raise ValueError("owner evidence references must be sorted and unique")


@dataclass(frozen=True, slots=True)
class HistoricalReprocessFacts:
    batch_identity: str
    batch_version: int
    batch_completed: bool
    classifier_version: str
    rows: tuple[HistoricalReprocessRow, ...]

    def __post_init__(self) -> None:
        require_canonical_text(self.batch_identity, "reprocess batch identity", 191)
        require_nonnegative_integer(self.batch_version, "reprocess batch version")
        require_canonical_text(self.classifier_version, "reprocess classifier version", 191)
        if not self.batch_completed:
            raise ValueError("batch_not_completed")
        identities = tuple(row.row_identity for row in self.rows)
        if not identities or identities != tuple(sorted(set(identities))):
            raise ValueError("reprocess rows must be sorted and unique")


@dataclass(frozen=True, slots=True)
class HistoricalReprocessPlan:
    batch_identity: str
    batch_version: int
    rows: tuple[HistoricalReprocessRow, ...]
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class HistoricalReprocessApplyRequest:
    batch_identity: str
    expected_batch_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId
    owner_selections: tuple[HistoricalOwnerSelection, ...] = ()

    def __post_init__(self) -> None:
        require_canonical_text(self.batch_identity, "reprocess batch identity", 191)
        require_canonical_text(self.reason, "reprocess reason", 500)
        identities = tuple(item.row_identity for item in self.owner_selections)
        if identities != tuple(sorted(set(identities))):
            raise ValueError("historical owner selections must be sorted and unique")


@dataclass(frozen=True, slots=True)
class HistoricalReprocessReceipt:
    batch_identity: str
    resulting_batch_version: int
    reprocess_run_id: int
    reclassified_count: int
    dispatched_count: int
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StoredHistoricalReprocessReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: HistoricalReprocessReceipt


class HistoricalReprocessRepository(Protocol):
    def load_historical_reprocess(self, batch_identity: str, *, for_update: bool, owner_selections: tuple[HistoricalOwnerSelection, ...] = ()) -> HistoricalReprocessFacts: ...
    def find_historical_reprocess_receipt(self, key: IdempotencyKey) -> StoredHistoricalReprocessReceipt | None: ...
    def append_reprocess_classification_events(self, plan: HistoricalReprocessPlan, actor: ActorContext) -> None: ...
    def append_owner_selection_events(self, plan: HistoricalReprocessPlan, request: HistoricalReprocessApplyRequest) -> None: ...
    def append_reprocess_run(self, plan: HistoricalReprocessPlan, dispatched_count: int) -> int: ...
    def append_reprocess_outbox(self, plan: HistoricalReprocessPlan) -> None: ...
    def advance_batch_version(self, batch_identity: str, expected_version: int, resulting_version: int) -> None: ...
    def save_historical_reprocess_receipt(self, key: IdempotencyKey, stored: StoredHistoricalReprocessReceipt) -> None: ...


class HistoricalReprocessPostingPort(Protocol):
    def resolve(self, row: CanonicalFinanceImportRow) -> CanonicalFinanceImportRow: ...
    def post(self, row: CanonicalFinanceImportRow) -> FinanceImportDispatchResult: ...


class HistoricalReprocessWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.code)
        self.error = error


class HistoricalReprocessWorkflow:
    def __init__(self, repository: HistoricalReprocessRepository, posting_port: HistoricalReprocessPostingPort, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository = repository
        self._posting_port = posting_port
        self._unit_of_work_factory = unit_of_work_factory

    def preview(self, batch_identity: str, correlation_id: CorrelationId, owner_selections: tuple[HistoricalOwnerSelection, ...] = ()) -> HistoricalReprocessPlan:
        try:
            return build_historical_reprocess_plan(
                self._load(batch_identity, False, owner_selections)
            )
        except ValueError as error:
            raise _workflow_error(correlation_id, ErrorCategory.DOMAIN_BLOCKED, str(error)) from error

    def apply(self, request: HistoricalReprocessApplyRequest) -> HistoricalReprocessReceipt:
        try:
            return self._apply(request)
        except HistoricalReprocessWorkflowError:
            raise
        except ValueError as error:
            raise _workflow_error(request.correlation_id, ErrorCategory.DOMAIN_BLOCKED, str(error)) from error
        except Exception as error:
            raise _workflow_error(request.correlation_id, ErrorCategory.INTERNAL, "transaction_failed") from error

    def _apply(self, request: HistoricalReprocessApplyRequest) -> HistoricalReprocessReceipt:
        command = _command_fingerprint(request)
        with self._unit_of_work_factory() as unit_of_work:
            replay = self._replay(request, command)
            if replay is not None:
                return replay
            plan = self._fresh_plan(request)
            self._append_owner_selection_events(plan, request)
            self._repository.append_reprocess_classification_events(
                plan,
                request.actor,
            )
            self._dispatch(plan)
            receipt = self._persist(request, plan, command)
            unit_of_work.commit()
            return receipt

    def _replay(self, request, command):
        stored = self._repository.find_historical_reprocess_receipt(request.idempotency_key)
        if stored is None:
            return None
        if stored.command_fingerprint == command:
            return stored.receipt
        raise _workflow_error(request.correlation_id, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_conflict")

    def _fresh_plan(self, request):
        facts = self._load(
            request.batch_identity,
            True,
            request.owner_selections,
        )
        if facts.batch_version != request.expected_batch_version.value:
            raise _workflow_error(request.correlation_id, ErrorCategory.CONFLICT, "stale_preview")
        plan = build_historical_reprocess_plan(facts)
        if plan.fingerprint != request.preview_fingerprint:
            raise _workflow_error(request.correlation_id, ErrorCategory.CONFLICT, "stale_preview")
        return plan

    def _load(self, batch_identity, for_update, owner_selections):
        if owner_selections:
            return self._repository.load_historical_reprocess(
                batch_identity,
                for_update=for_update,
                owner_selections=owner_selections,
            )
        return self._repository.load_historical_reprocess(
            batch_identity,
            for_update=for_update,
        )

    def _append_owner_selection_events(self, plan, request):
        if any(row.owner_selection is not None for row in plan.rows):
            self._repository.append_owner_selection_events(plan, request)

    def _dispatch(self, plan):
        for row in plan.rows:
            result = self._posting_port.post(self._posting_port.resolve(row.after))
            _require_final_dispatch(row, result)

    def _persist(self, request, plan, command):
        run_id = self._repository.append_reprocess_run(plan, len(plan.rows))
        receipt = HistoricalReprocessReceipt(plan.batch_identity, plan.batch_version + 1, run_id, len(plan.rows), len(plan.rows), plan.fingerprint)
        self._repository.append_reprocess_outbox(plan)
        self._repository.advance_batch_version(plan.batch_identity, plan.batch_version, receipt.resulting_batch_version)
        self._repository.save_historical_reprocess_receipt(request.idempotency_key, StoredHistoricalReprocessReceipt(command, receipt))
        return receipt


def build_historical_reprocess_plan(facts: HistoricalReprocessFacts) -> HistoricalReprocessPlan:
    payload = {
        "batch_identity": facts.batch_identity,
        "batch_version": facts.batch_version,
        "classifier_version": facts.classifier_version,
        "rows": tuple(_row_payload(row) for row in facts.rows),
    }
    return HistoricalReprocessPlan(facts.batch_identity, facts.batch_version, facts.rows, fingerprint_payload(payload))


def _row_payload(row: HistoricalReprocessRow) -> dict[str, object]:
    return {
        "row_identity": row.row_identity,
        "before": row.before_classification.value,
        "after": row.after.decision_facts_fingerprint.value,
        "owner": row.after.classification_type.value,
        "owner_selection": _owner_selection_payload(row.owner_selection),
    }


def _command_fingerprint(request: HistoricalReprocessApplyRequest) -> PreviewFingerprint:
    return fingerprint_payload({"batch": request.batch_identity, "version": request.expected_batch_version.value, "preview": request.preview_fingerprint.value, "actor": request.actor.actor_id, "reason": request.reason, "owner_selections": tuple(_owner_selection_payload(item) for item in request.owner_selections)})


def _owner_selection_payload(selection):
    if selection is None:
        return None
    return {
        "row_identity": selection.row_identity,
        "case_no": selection.case_no,
        "obligation_identity": selection.obligation_identity,
        "reason": selection.reason,
        "evidence_references": selection.evidence_references,
    }


def _workflow_error(correlation_id, category, code):
    return HistoricalReprocessWorkflowError(TypedError(category, code or "transaction_failed", "Historical Finance Import reprocess failed.", correlation_id))


def _require_final_dispatch(row, result) -> None:
    if not isinstance(result, FinanceImportDispatchResult):
        raise ValueError("historical_reprocess_dispatch_result_invalid")
    if result.row_identity != row.row_identity:
        raise ValueError("historical_reprocess_dispatch_identity_mismatch")
    if result.outcome not in {
        FinanceDispatchOutcome.RECONCILED,
        FinanceDispatchOutcome.EXISTING,
    }:
        raise ValueError("historical_reprocess_dispatch_not_final")
    if result.result_reference is None:
        raise ValueError("historical_reprocess_dispatch_reference_missing")
