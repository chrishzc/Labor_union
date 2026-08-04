"""Atomic orchestration for conserved financial adjustments."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Protocol
from domains.client_finance.financial_adjustment import FinancialAdjustmentCandidate, FinancialAdjustmentFacts, FinancialAdjustmentIntent, FinancialAdjustmentScope, build_financial_adjustment_candidate
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
CLIENT_FINANCE_CANDIDATE_STALE="client_finance_candidate_stale"; CLIENT_FINANCE_IDEMPOTENCY_CONFLICT="client_finance_idempotency_conflict"
@dataclass(frozen=True,slots=True)
class FinancialAdjustmentPreview: client_account_version:int; payroll_version:int|None; candidate:FinancialAdjustmentCandidate; fingerprint:PreviewFingerprint
@dataclass(frozen=True,slots=True)
class FinancialAdjustmentApplyRequest: intent:FinancialAdjustmentIntent; expected_client_account_version:ExpectedVersion; expected_payroll_version:ExpectedVersion|None; preview_fingerprint:PreviewFingerprint; idempotency_key:IdempotencyKey; actor:ActorContext; correlation_id:CorrelationId
@dataclass(frozen=True,slots=True)
class FinancialAdjustmentReceipt: case_no:str; adjustment_identity:str; amount_delta_ntd:int; client_account_version:int; payroll_version:int|None; assignment_allocation_count:int; preview_fingerprint:PreviewFingerprint
@dataclass(frozen=True,slots=True)
class StoredFinancialAdjustmentReceipt: command_fingerprint:PreviewFingerprint; receipt:FinancialAdjustmentReceipt
class FinancialAdjustmentError(Exception):
 def __init__(self,error): self.error=error; super().__init__(error.code)
class FinancialAdjustmentStorageError(RuntimeError):
 def __init__(self,message,*,retryable): self.retryable=retryable; super().__init__(message)
class FinancialAdjustmentRepository(Protocol):
 def load(self,intent,*,for_update): ...
 def find_receipt(self,key): ...
 def persist(self,request,preview,command_fingerprint,receipt): ...
class FinancialAdjustmentWorkflow:
 def __init__(self,repository,unit_of_work_factory:Callable[[],object]): self._repository=repository; self._unit_of_work_factory=unit_of_work_factory
 def preview(self,intent,correlation_id):
  try:return _preview(self._repository.load(intent,for_update=False),intent)
  except (TypeError,ValueError) as e: raise _domain(correlation_id,str(e)) from e
 def apply(self,request):
  try:
   command=_command(request)
   with self._unit_of_work_factory() as unit:
    replay=self._repository.find_receipt(request.idempotency_key)
    if replay:
     if replay.command_fingerprint != command: raise _workflow(request.correlation_id,ErrorCategory.IDEMPOTENCY_MISMATCH,CLIENT_FINANCE_IDEMPOTENCY_CONFLICT)
     return replay.receipt
    preview=_preview(self._repository.load(request.intent,for_update=True),request.intent); _versions(request,preview)
    receipt=_receipt(preview); self._repository.persist(request,preview,command,receipt); unit.commit(); return receipt
  except FinancialAdjustmentError: raise
  except FinancialAdjustmentStorageError as e: raise _workflow(request.correlation_id,ErrorCategory.UNAVAILABLE if e.retryable else ErrorCategory.INTERNAL,"transaction_failed",retryable=e.retryable) from e
  except Exception as e: raise _workflow(request.correlation_id,ErrorCategory.INTERNAL,"transaction_failed") from e
def _preview(facts,intent):
 c=build_financial_adjustment_candidate(facts,intent); payroll=None if intent.scope is FinancialAdjustmentScope.CLIENT_ONLY else facts.payroll_version
 return FinancialAdjustmentPreview(facts.client_account_version,payroll,c,fingerprint_payload({"candidate":c.fingerprint.value,"client_account_version":facts.client_account_version,"payroll_version":payroll}))
def _versions(req,p):
 if req.expected_client_account_version.value!=p.client_account_version or req.preview_fingerprint!=p.fingerprint or (p.payroll_version is None and req.expected_payroll_version is not None) or (p.payroll_version is not None and (req.expected_payroll_version is None or req.expected_payroll_version.value!=p.payroll_version)): raise _workflow(req.correlation_id,ErrorCategory.CONFLICT,CLIENT_FINANCE_CANDIDATE_STALE,current=p.client_account_version)
def _receipt(p):
 c=p.candidate; return FinancialAdjustmentReceipt(c.case_no,c.adjustment_identity,c.amount_delta.amount,p.client_account_version+1,None if p.payroll_version is None else p.payroll_version+1,len(c.assignment_allocations),p.fingerprint)
def _command(r): return fingerprint_payload({"intent":r.intent.source_event_identity,"case_no":r.intent.case_no,"expected_client":r.expected_client_account_version.value,"expected_payroll":None if r.expected_payroll_version is None else r.expected_payroll_version.value,"preview":r.preview_fingerprint.value,"actor":r.actor.actor_id})
def _domain(c,e): return _workflow(c,ErrorCategory.VALIDATION,e or "invalid_financial_adjustment_facts")
def _workflow(c,category,code,retryable=False,current=None): return FinancialAdjustmentError(TypedError(category,code,"Financial adjustment failed.",c,retryable=retryable,current_version=None if current is None else ExpectedVersion(current)))
__all__=[name for name in globals() if name.startswith("FinancialAdjustment") or name.startswith("Stored")]
