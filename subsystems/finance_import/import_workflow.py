"""Preview and apply the canonical Finance Import dispatch plan."""

from __future__ import annotations

from dataclasses import dataclass, replace
from collections import Counter
from enum import StrEnum
import re
from typing import Callable, Protocol

from domains.finance_import.planning import (
    CanonicalFinanceImportRow, ClientReceiptReviewDiagnostic, FinanceClassificationType, FinanceImportBatchFacts, FinanceImportDisposition, FinanceImportPlan,
    build_finance_import_plan, defer_overlapping_client_receipts, defer_overlapping_outgoing_payments,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_canonical_text

_IDENTITY_MAXIMUM_LENGTH = 191
_REASON_MAXIMUM_LENGTH = 500


class FinanceDispatchOutcome(StrEnum):
    RECONCILED = "reconciled"
    EXISTING = "existing"
    PENDING = "pending"
    REJECTED = "rejected"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class FinanceImportApplyRequest:
    batch_identity: str; expected_batch_version: ExpectedVersion; preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey; actor: ActorContext; reason: str; correlation_id: CorrelationId
    staff_subsidy_selections: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        require_canonical_text(self.batch_identity, "finance import batch identity", _IDENTITY_MAXIMUM_LENGTH)
        require_canonical_text(self.reason, "finance import apply reason", _REASON_MAXIMUM_LENGTH, allow_empty=True)


@dataclass(frozen=True, slots=True)
class FinanceImportDispatchResult:
    row_identity: str; outcome: FinanceDispatchOutcome; result_reference: str | None = None
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class FinanceImportApplyReceipt:
    batch_identity: str; resulting_batch_version: int; preview_fingerprint: PreviewFingerprint
    reconciled_count: int; existing_count: int; pending_count: int


@dataclass(frozen=True, slots=True)
class PendingReconciliationRequest:
    idempotency_key: IdempotencyKey
    actor: ActorContext
    correlation_id: CorrelationId
    reason: str = "重新配對並核銷待核對明細"


@dataclass(frozen=True, slots=True)
class PendingReconciliationReceipt:
    checked_count: int
    reconciled_count: int
    existing_count: int
    pending_count: int


@dataclass(frozen=True, slots=True)
class StoredFinanceImportReceipt:
    command_fingerprint: PreviewFingerprint; receipt: FinanceImportApplyReceipt
    client_receipt_reviews: tuple[tuple[str, ClientReceiptReviewDiagnostic], ...] = ()
    pending_reasons: tuple[tuple[str, str], ...] = ()


class FinanceImportRepository(Protocol):
    def load(self, batch_identity: str, *, for_update: bool) -> FinanceImportBatchFacts: ...
    def load_pending_batches(self): ...
    def find_receipt(self, key: IdempotencyKey, *, for_update: bool = False) -> StoredFinanceImportReceipt | None: ...
    def append_dispatch_audit(self, plan: FinanceImportPlan, results: tuple[FinanceImportDispatchResult, ...]) -> None: ...
    def append_outbox(self, plan: FinanceImportPlan, results: tuple[FinanceImportDispatchResult, ...]) -> None: ...
    def advance_batch_version(self, batch_identity: str, expected_version: int, resulting_version: int) -> None: ...
    def save_receipt(self, key: IdempotencyKey, stored: StoredFinanceImportReceipt) -> None: ...


class FinanceImportFormalPostingPort(Protocol):
    def resolve(self, row: CanonicalFinanceImportRow) -> CanonicalFinanceImportRow: ...
    def resolve_pending_government(self, row: CanonicalFinanceImportRow) -> CanonicalFinanceImportRow: ...
    def post(self, row: CanonicalFinanceImportRow) -> FinanceImportDispatchResult: ...


class FinanceImportRepositoryUnavailable(RuntimeError): pass


class FinanceImportWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.message); self.error = error


class FinanceImportWorkflow:
    def __init__(self, repository: FinanceImportRepository, posting_port: FinanceImportFormalPostingPort, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository = repository; self._posting_port = posting_port; self._unit_of_work_factory = unit_of_work_factory
    def preview(self, batch_identity: str, correlation_id: CorrelationId, staff_subsidy_selections=()) -> FinanceImportPlan:
        try: return self._build_resolved_plan(self._repository.load(batch_identity, for_update=False), staff_subsidy_selections)
        except FinanceImportWorkflowError: raise
        except FinanceImportRepositoryUnavailable as error: raise _preview_transaction_error(correlation_id, error) from error
        except ValueError as error: raise _validation_error(correlation_id, str(error)) from error
    def apply(self, request: FinanceImportApplyRequest) -> FinanceImportApplyReceipt:
        try: return self._apply_in_unit_of_work(request)
        except FinanceImportWorkflowError: raise
        except FinanceImportRepositoryUnavailable as error: raise _transaction_error(request, error, retryable=True) from error
        except Exception as error: raise _transaction_error(request, error, retryable=False) from error

    def reconcile_pending(self, request: PendingReconciliationRequest) -> PendingReconciliationReceipt:
        with self._unit_of_work_factory() as unit_of_work:
            batches = tuple(self._repository.load_pending_batches())
            checked = sum(len(ids) for _, ids in batches)
            plans = tuple(self._pending_plan(facts, ids) for facts, ids in batches)
            targets = Counter(
                target
                for plan in plans if plan.apply_allowed
                for row in plan.dispatchable_rows
                for target in row.target_identities
            )
            reconciled = 0
            existing = 0
            for plan, (_, pending_ids) in zip(plans, batches, strict=True):
                existing += sum(row.disposition is FinanceImportDisposition.EXISTING
                                and row.row_identity in pending_ids for row in plan.rows)
                if not plan.apply_allowed:
                    continue
                # No owner confirmation or contested balance is implicitly authorized.
                rows = tuple(
                    row for row in plan.dispatchable_rows
                    if (row.subsidy_preflight is None or row.subsidy_preflight.existing_confirmed_payable)
                    and row.target_identities
                    and all(targets[target] == 1 for target in row.target_identities)
                )
                if not rows:
                    continue
                plan = replace(plan, rows=rows, fingerprint=fingerprint_payload({
                    "pending_reconciliation": request.idempotency_key.value,
                    "source_plan": plan.fingerprint.value,
                    "rows": tuple(row.row_identity for row in rows),
                }))
                results = self._dispatch(plan, request)
                self._repository.append_dispatch_audit(plan, results)
                self._repository.append_outbox(plan, results)
                self._repository.advance_batch_version(plan.batch_identity, plan.batch_version, plan.batch_version + 1)
                reconciled += sum(result.outcome is FinanceDispatchOutcome.RECONCILED for result in results)
                existing += sum(result.outcome is FinanceDispatchOutcome.EXISTING for result in results)
            unit_of_work.commit()
            return PendingReconciliationReceipt(checked, reconciled, existing, checked - reconciled - existing)

    def _pending_plan(self, facts, pending_ids):
        rows = []
        for row in facts.rows:
            if row.row_identity not in pending_ids:
                if row.disposition in {FinanceImportDisposition.CREATE, FinanceImportDisposition.BUSINESS_PENDING}:
                    row = replace(row, disposition=FinanceImportDisposition.EXISTING)
            elif not (row.integrity_violations or row.fingerprint_collision or row.formal_reference_conflict):
                if row.classification_type is FinanceClassificationType.GOVERNMENT_SUBSIDY:
                    row = self._posting_port.resolve_pending_government(row)
                else:
                    row = self._posting_port.resolve(row)
            rows.append(row)
        return build_finance_import_plan(replace(facts, rows=tuple(rows)))
    def _apply_in_unit_of_work(self, request):
        command_fingerprint = _command_fingerprint(request)
        with self._unit_of_work_factory() as unit_of_work:
            replay = self._find_replay(request, command_fingerprint)
            if replay is not None: return replay
            facts = self._repository.load(request.batch_identity, for_update=True)
            # The initial non-locking receipt read can miss a concurrent winner.  Once
            # this transaction owns the batch lock, use a locking read so its latest
            # immutable same-command receipt wins over a stale preview comparison.
            replay = self._find_replay(request, command_fingerprint, for_update=True)
            if replay is not None: return replay
            plan = self._fresh_plan(request, facts); results = self._dispatch(plan, request); receipt = _build_receipt(plan, results)
            self._persist(request, plan, results, command_fingerprint, receipt); unit_of_work.commit(); return receipt
    def _find_replay(self, request, command_fingerprint, *, for_update=False):
        stored = self._repository.find_receipt(request.idempotency_key, for_update=for_update)
        if stored is None: return None
        if stored.command_fingerprint == command_fingerprint: return stored.receipt
        raise _workflow_error(request.correlation_id, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_conflict", "Idempotency key was used by another Finance Import command.")
    def _fresh_plan(self, request, facts):
        _validate_batch_version(request, facts)
        try:
            plan = self._build_resolved_plan(facts, request.staff_subsidy_selections)
        except ValueError as error:
            if str(error) != "staff_subsidy_case_selection_invalid":
                raise
            raise _stale_error(request, facts.batch_version) from error
        _validate_plan_is_applicable(request, plan)
        if plan.fingerprint != request.preview_fingerprint: raise _stale_error(request, facts.batch_version)
        return plan
    def _build_resolved_plan(self, facts, staff_subsidy_selections=()):
        selections = dict(staff_subsidy_selections)
        eligible_selection_rows = {
            row.row_identity for row in facts.rows
            if row.classification_type is FinanceClassificationType.STAFF_PAYOUT
            and row.disposition is FinanceImportDisposition.BUSINESS_PENDING
        }
        if not selections.keys() <= eligible_selection_rows:
            raise ValueError("staff_subsidy_case_selection_invalid")
        resolved_rows = tuple(
            self._posting_port.resolve(replace(row, selected_staff_subsidy_case=selections[row.row_identity]))
            if row.row_identity in selections else self._posting_port.resolve(row)
            for row in facts.rows
        )
        return build_finance_import_plan(
            replace(
                facts,
                rows=defer_overlapping_outgoing_payments(defer_overlapping_client_receipts(resolved_rows)),
            )
        )
    def _dispatch(self, plan, request):
        results = tuple(self._posting_port.post(row) for row in plan.dispatchable_rows); _validate_dispatch_results(plan, results, request); return results
    def _persist(self, request, plan, results, command_fingerprint, receipt):
        self._repository.append_dispatch_audit(plan, results); self._repository.append_outbox(plan, results)
        self._repository.advance_batch_version(plan.batch_identity, plan.batch_version, receipt.resulting_batch_version)
        reviews = tuple(
            (row.row_identity, row.client_receipt_review)
            for row in plan.rows
            if row.disposition is FinanceImportDisposition.BUSINESS_PENDING and row.client_receipt_review is not None
        )
        pending_reasons = tuple((row.row_identity, row.pending_reason) for row in plan.rows
                               if row.disposition is FinanceImportDisposition.BUSINESS_PENDING and row.pending_reason is not None)
        self._repository.save_receipt(request.idempotency_key, StoredFinanceImportReceipt(command_fingerprint, receipt, reviews, pending_reasons))


def _validate_batch_version(request, facts):
    if facts.batch_version != request.expected_batch_version.value:
        raise _workflow_error(request.correlation_id, ErrorCategory.CONFLICT, "stale_preview", "Finance Import batch version changed before Apply.", current_version=facts.batch_version)
def _validate_result_reference(result):
    formal = {FinanceDispatchOutcome.RECONCILED, FinanceDispatchOutcome.EXISTING}
    if result.outcome in formal and result.result_reference is None: raise ValueError("formal dispatch result requires a reference")
    if result.outcome not in formal and result.result_reference is not None: raise ValueError("non-formal dispatch result cannot have a reference")
def _validate_plan_is_applicable(request, plan):
    if not plan.apply_allowed: raise _workflow_error(request.correlation_id, ErrorCategory.DOMAIN_BLOCKED, "finance_import_batch_blocked", "Finance Import batch has blocking integrity or reference conflicts.", blockers=plan.blocking_codes)
def _validate_dispatch_results(plan, results, request):
    if tuple(item.row_identity for item in results) != tuple(item.row_identity for item in plan.dispatchable_rows): raise RuntimeError("formal posting results do not match dispatch plan")
    for result in results:
        _validate_result_reference(result)
        if result.outcome in {FinanceDispatchOutcome.REJECTED, FinanceDispatchOutcome.CONFLICT}:
            code = "dispatch_rejected" if result.outcome is FinanceDispatchOutcome.REJECTED else "classification_conflict"
            row_blockers = tuple(
                f"{item.row_identity}:{item.reason_code}"
                for item in results
                if item.outcome in {FinanceDispatchOutcome.REJECTED, FinanceDispatchOutcome.CONFLICT}
                and item.reason_code
                and re.fullmatch(r"finance-import-row:[0-9]{1,20}", item.row_identity)
                and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", item.reason_code)
            )
            raise _dispatch_error(request, code, row_blockers)
def _build_receipt(plan, results):
    outcomes = tuple(item.outcome for item in results)
    return FinanceImportApplyReceipt(plan.batch_identity, plan.batch_version + 1, plan.fingerprint, outcomes.count(FinanceDispatchOutcome.RECONCILED), outcomes.count(FinanceDispatchOutcome.EXISTING), outcomes.count(FinanceDispatchOutcome.PENDING))
def _command_fingerprint(request):
    payload = {
        "batch_identity": request.batch_identity,
        "expected_batch_version": request.expected_batch_version.value,
        "preview_fingerprint": request.preview_fingerprint.value,
        "actor_id": request.actor.actor_id,
        "reason": request.reason,
    }
    if request.staff_subsidy_selections:
        payload["staff_subsidy_selections"] = dict(request.staff_subsidy_selections)
    return fingerprint_payload(payload)
def _stale_error(request, current_version): return _workflow_error(request.correlation_id, ErrorCategory.CONFLICT, "stale_preview", "Finance Import facts changed after Preview.", current_version=current_version)
def _dispatch_error(request, code, row_blockers): return _workflow_error(request.correlation_id, ErrorCategory.DOMAIN_BLOCKED, code, "Owning Finance Domain rejected the proposed dispatch.", blockers=(code, *row_blockers))
def _validation_error(correlation_id, code): return _workflow_error(correlation_id, ErrorCategory.VALIDATION, "invalid_finance_import_facts", code)
def _transaction_error(request, error, *, retryable): return _workflow_error(request.correlation_id, ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL, "downstream_unavailable" if retryable else "transaction_failed", str(error) or "Finance Import transaction failed.", retryable=retryable)
def _preview_transaction_error(correlation_id, error): return _workflow_error(correlation_id, ErrorCategory.UNAVAILABLE, "downstream_unavailable", str(error) or "Finance Import Preview is unavailable.", retryable=True)
def _workflow_error(correlation_id, category, code, message, *, blockers=(), retryable=False, current_version=None): return FinanceImportWorkflowError(TypedError(category, code, message, correlation_id, domain_blockers=tuple(sorted(set(blockers))), retryable=retryable, current_version=_expected_version(current_version)))
def _expected_version(current_version): return None if current_version is None else ExpectedVersion(current_version)

__all__ = ["FinanceDispatchOutcome","FinanceImportApplyReceipt","FinanceImportApplyRequest","FinanceImportDispatchResult","FinanceImportFormalPostingPort","FinanceImportRepository","FinanceImportRepositoryUnavailable","FinanceImportWorkflow","FinanceImportWorkflowError","StoredFinanceImportReceipt"]
