"""Preview and post a manually confirmed Finance Import correction."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Protocol
from domains.finance_import.correction import FinanceImportCorrectionCandidate, FinanceImportCorrectionFacts, FinanceImportCorrectionSelection, build_finance_import_correction_candidate
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.ports import UnitOfWork

@dataclass(frozen=True, slots=True)
class FinanceImportCorrectionPreview:
    candidate: FinanceImportCorrectionCandidate; batch_version: int; canonical_fact_version: int; alert_version: int; fingerprint: PreviewFingerprint
@dataclass(frozen=True, slots=True)
class FinanceImportCorrectionApplyRequest:
    selection: FinanceImportCorrectionSelection; expected_batch_version: ExpectedVersion; expected_canonical_fact_version: ExpectedVersion; expected_alert_version: ExpectedVersion; preview_fingerprint: PreviewFingerprint; idempotency_key: IdempotencyKey; actor: ActorContext; correlation_id: CorrelationId
@dataclass(frozen=True, slots=True)
class FinanceImportCorrectionReceipt:
    row_identity: str; batch_identity: str; resulting_batch_version: int; classification_event_count: int; ledger_entry_count: int; allocation_count: int; reconciliation_receipt_count: int; alert_resolved_event_count: int; preview_fingerprint: PreviewFingerprint
@dataclass(frozen=True, slots=True)
class StoredFinanceImportCorrectionReceipt:
    command_fingerprint: PreviewFingerprint; receipt: FinanceImportCorrectionReceipt
class FinanceImportCorrectionRepository(Protocol):
    def load(self, selection: FinanceImportCorrectionSelection, *, for_update: bool) -> FinanceImportCorrectionFacts: ...
    def find_correction_receipt(self, key: IdempotencyKey) -> StoredFinanceImportCorrectionReceipt | None: ...
    def append_manual_classification(self, candidate, actor): ...
    def append_reconciliation_receipt(self, candidate): ...
    def append_alert_resolved_event(self, candidate, actor) -> int: ...
    def append_outbox(self, candidate): ...
    def advance_batch_version(self, candidate, expected_version, resulting_version): ...
    def save_correction_receipt(self, key, stored): ...
class FinanceImportCorrectionPostingPort(Protocol):
    def post(self, candidate: FinanceImportCorrectionCandidate) -> int: ...
class FinanceImportRepositoryUnavailable(RuntimeError): pass
class FinanceImportCorrectionWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None: super().__init__(error.message); self.error = error

class FinanceImportCorrectionWorkflow:
    def __init__(self, repository: FinanceImportCorrectionRepository, posting_port: FinanceImportCorrectionPostingPort, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository=repository; self._posting_port=posting_port; self._unit_of_work_factory=unit_of_work_factory
    def preview(self, selection, correlation_id):
        try: return _build_preview(selection, self._repository.load(selection, for_update=False))
        except FinanceImportRepositoryUnavailable as error: raise _preview_transaction_error(correlation_id,error) from error
        except ValueError as error: raise _domain_error(correlation_id,str(error)) from error
    def correct_and_post(self, request):
        try: return self._apply_in_unit_of_work(request)
        except FinanceImportCorrectionWorkflowError: raise
        except FinanceImportRepositoryUnavailable as error: raise _transaction_error(request,error,retryable=True) from error
        except ValueError as error: raise _domain_error(request.correlation_id,str(error)) from error
        except Exception as error: raise _transaction_error(request,error,retryable=False) from error
    def _apply_in_unit_of_work(self,request):
        fingerprint=_command_fingerprint(request)
        with self._unit_of_work_factory() as uow:
            replay=self._find_replay(request,fingerprint)
            if replay is not None: return replay
            preview=self._fresh_preview(request); count, alert_resolved_event_count=self._persist_formal_result(request,preview); receipt=_build_receipt(preview,count,alert_resolved_event_count)
            self._save_receipt(request,fingerprint,receipt); uow.commit(); return receipt
    def _find_replay(self,request,fingerprint):
        stored=self._repository.find_correction_receipt(request.idempotency_key)
        if stored is None:return None
        if stored.command_fingerprint==fingerprint:return stored.receipt
        raise _workflow_error(request.correlation_id,ErrorCategory.IDEMPOTENCY_MISMATCH,"idempotency_conflict","Idempotency key was used by another correction command.")
    def _fresh_preview(self,request):
        facts=self._repository.load(request.selection,for_update=True); _validate_expected_versions(request,facts)
        try: preview=_build_preview(request.selection,facts)
        except ValueError as error: raise _domain_error(request.correlation_id,str(error)) from error
        if preview.fingerprint != request.preview_fingerprint: raise _stale_error(request,facts)
        return preview
    def _persist_formal_result(self,request,preview):
        candidate=preview.candidate; self._repository.append_manual_classification(candidate,request.actor); count=self._posting_port.post(candidate)
        if count < 1: raise RuntimeError("correction posting created no formal ledger entry")
        self._repository.append_reconciliation_receipt(candidate); alert_resolved_event_count=self._repository.append_alert_resolved_event(candidate,request.actor) or 0; self._repository.append_outbox(candidate); self._repository.advance_batch_version(candidate,preview.batch_version,preview.batch_version+1); return count, alert_resolved_event_count
    def _save_receipt(self,request,fingerprint,receipt): self._repository.save_correction_receipt(request.idempotency_key,StoredFinanceImportCorrectionReceipt(fingerprint,receipt))

def _build_preview(selection,facts):
    candidate=build_finance_import_correction_candidate(selection,facts); fingerprint=fingerprint_payload({"candidate_fingerprint":candidate.fingerprint.value,"batch_version":facts.batch_version,"canonical_fact_version":facts.canonical_fact_version,"alert_version":facts.alert_version}); return FinanceImportCorrectionPreview(candidate,facts.batch_version,facts.canonical_fact_version,facts.alert_version,fingerprint)
def _validate_expected_versions(request,facts):
    if (request.expected_batch_version.value,request.expected_canonical_fact_version.value,request.expected_alert_version.value)!=(facts.batch_version,facts.canonical_fact_version,facts.alert_version): raise _workflow_error(request.correlation_id,ErrorCategory.CONFLICT,"stale_preview","Correction facts changed before Apply.")
def _build_receipt(preview,ledger_entry_count,alert_resolved_event_count):
    candidate=preview.candidate; return FinanceImportCorrectionReceipt(candidate.row_identity,candidate.batch_identity,preview.batch_version+1,1,ledger_entry_count,len(candidate.allocations),1,alert_resolved_event_count,preview.fingerprint)
def _command_fingerprint(request):
    selection=request.selection; return fingerprint_payload({"row_identity":selection.row_identity,"classification_type":selection.classification_type.value,"target_obligation_identities":selection.target_obligation_identities,"refund_ledger_entry_identity":selection.refund_ledger_entry_identity,"reason":selection.reason,"evidence":selection.evidence,"expected_batch_version":request.expected_batch_version.value,"expected_canonical_fact_version":request.expected_canonical_fact_version.value,"expected_alert_version":request.expected_alert_version.value,"preview_fingerprint":request.preview_fingerprint.value,"actor_id":request.actor.actor_id})
def _domain_error(correlation_id,raw_code):
    blockers=tuple(sorted(code for code in raw_code.split(",") if code)); code=blockers[0] if blockers else "classification_conflict"; category=ErrorCategory.VALIDATION if code=="manual_evidence_required" else ErrorCategory.DOMAIN_BLOCKED; return _workflow_error(correlation_id,category,code,"Finance Import correction cannot be posted.",blockers=blockers if category is ErrorCategory.DOMAIN_BLOCKED else ())
def _stale_error(request,facts): return _workflow_error(request.correlation_id,ErrorCategory.CONFLICT,"stale_preview","Correction candidate changed after Preview.",current_version=facts.alert_version)
def _transaction_error(request,error,*,retryable): return _workflow_error(request.correlation_id,ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL,"downstream_unavailable" if retryable else "transaction_failed",str(error) or "Finance Import transaction failed.",retryable=retryable)
def _preview_transaction_error(correlation_id,error): return _workflow_error(correlation_id,ErrorCategory.UNAVAILABLE,"downstream_unavailable",str(error) or "Finance Import Preview is unavailable.",retryable=True)
def _workflow_error(correlation_id,category,code,message,*,blockers=(),retryable=False,current_version=None): return FinanceImportCorrectionWorkflowError(TypedError(category,code,message,correlation_id,domain_blockers=tuple(sorted(set(blockers))),retryable=retryable,current_version=_expected_version(current_version)))
def _expected_version(current_version): return None if current_version is None else ExpectedVersion(current_version)
__all__=["FinanceImportCorrectionApplyRequest","FinanceImportCorrectionPostingPort","FinanceImportCorrectionPreview","FinanceImportCorrectionReceipt","FinanceImportCorrectionRepository","FinanceImportCorrectionWorkflow","FinanceImportCorrectionWorkflowError","StoredFinanceImportCorrectionReceipt"]
