"""Preview/apply workflow for client refunds, subsidy returns, and reversals."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Protocol
from domains.client_finance.client_refund_reversal import (ClientFinanceCorrectionType,ClientRefundBankFact,ClientRefundObligation,ClientRefundPurpose,ClientRefundReturnBankFact,ClientRefundReversalCandidate,ClientReversalTarget,build_client_refund_candidate,build_client_refund_return_candidate,build_client_reversal_candidate)
from shared_kernel.errors import ErrorCategory,TypedError
from shared_kernel.fingerprints import PreviewFingerprint,fingerprint_payload
from shared_kernel.identities import ActorContext,CorrelationId,ExpectedVersion,IdempotencyKey
from shared_kernel.validation import require_canonical_text,require_nonnegative_integer
CLIENT_FINANCE_CANDIDATE_STALE="client_finance_candidate_stale"; CLIENT_FINANCE_IDEMPOTENCY_CONFLICT="client_finance_idempotency_conflict"
@dataclass(frozen=True,slots=True)
class ClientRefundReversalSelection:
 case_no:str; correction_type:ClientFinanceCorrectionType; refund_purpose:ClientRefundPurpose=ClientRefundPurpose.CUSTOMER_REFUND; bank_fact_identities:tuple[str,...]=(); obligation_identities:tuple[str,...]=(); reversal_target_identities:tuple[str,...]=(); reversal_occurred_on:str|None=None
 def __post_init__(self): require_canonical_text(self.case_no,"case number",191); _selection_shape(self)
@dataclass(frozen=True,slots=True)
class ClientRefundReversalFacts:
 account_version:int; bank_facts:tuple[ClientRefundBankFact,...]=(); obligations:tuple[ClientRefundObligation,...]=(); reversal_targets:tuple[ClientReversalTarget,...]=(); refund_return_bank_facts:tuple[ClientRefundReturnBankFact,...]=()
 def __post_init__(self): require_nonnegative_integer(self.account_version,"client account version")
@dataclass(frozen=True,slots=True)
class ClientRefundReversalPreview: candidate:ClientRefundReversalCandidate; account_version:int; fingerprint:PreviewFingerprint
@dataclass(frozen=True,slots=True)
class ClientRefundReversalApplyRequest:
 selection:ClientRefundReversalSelection; expected_account_version:ExpectedVersion; preview_fingerprint:PreviewFingerprint; idempotency_key:IdempotencyKey; actor:ActorContext; reason:str; correlation_id:CorrelationId
@dataclass(frozen=True,slots=True)
class ClientRefundReversalReceipt:
 case_no:str; correction_type:ClientFinanceCorrectionType; account_version:int; correction_identity:PreviewFingerprint; ledger_entry_count:int; allocation_count:int; affected_obligations:tuple[str,...]
@dataclass(frozen=True,slots=True)
class StoredClientRefundReversalReceipt: command_fingerprint:PreviewFingerprint; receipt:ClientRefundReversalReceipt
class ClientRefundReversalError(Exception):
 def __init__(self,error): self.error=error; super().__init__(error.code)
class ClientRefundReversalStorageError(RuntimeError):
 def __init__(self,message,*,retryable): self.retryable=retryable; super().__init__(message)
class ClientRefundReversalRepository(Protocol):
 def load(self,selection,*,for_update): ...
 def find_receipt(self,key): ...
 def append_ledger_entries(self,candidate): ...
 def append_allocations(self,candidate): ...
 def update_projection(self,candidate,resulting_version): ...
 def append_outbox(self,candidate,resulting_version): ...
 def save_receipt(self,key,stored_receipt): ...
class ClientRefundReversalWorkflow:
 def __init__(self,repository,unit_of_work_factory:Callable[[],object]): self._repository=repository;self._unit_of_work_factory=unit_of_work_factory
 def preview(self,selection,correlation_id):
  try:return _preview(selection,self._repository.load(selection,for_update=False))
  except ValueError as e: raise _error(correlation_id,ErrorCategory.DOMAIN_BLOCKED,str(e)) from e
 def apply(self,request):
  try:
   command=_command(request)
   with self._unit_of_work_factory() as unit:
    replay=self._repository.find_receipt(request.idempotency_key)
    if replay:
     if replay.command_fingerprint!=command: raise _error(request.correlation_id,ErrorCategory.IDEMPOTENCY_MISMATCH,CLIENT_FINANCE_IDEMPOTENCY_CONFLICT)
     return replay.receipt
    preview=_preview(request.selection,self._repository.load(request.selection,for_update=True))
    if preview.account_version!=request.expected_account_version.value or preview.fingerprint!=request.preview_fingerprint: raise _error(request.correlation_id,ErrorCategory.CONFLICT,CLIENT_FINANCE_CANDIDATE_STALE,current=preview.account_version)
    receipt=ClientRefundReversalReceipt(request.selection.case_no,preview.candidate.correction_type,preview.account_version+1,preview.candidate.fingerprint,len(preview.candidate.entries),len(preview.candidate.allocations),preview.candidate.affected_obligations)
    self._repository.append_ledger_entries(preview.candidate);self._repository.append_allocations(preview.candidate);self._repository.update_projection(preview.candidate,receipt.account_version);self._repository.append_outbox(preview.candidate,receipt.account_version);self._repository.save_receipt(request.idempotency_key,StoredClientRefundReversalReceipt(command,receipt));unit.commit();return receipt
  except ClientRefundReversalError:raise
  except ClientRefundReversalStorageError as e:raise _error(request.correlation_id,ErrorCategory.UNAVAILABLE if e.retryable else ErrorCategory.INTERNAL,"transaction_failed",retryable=e.retryable) from e
  except Exception as e:raise _error(request.correlation_id,ErrorCategory.INTERNAL,"transaction_failed") from e
def _preview(s,f):
 _facts(s,f)
 if s.correction_type is ClientFinanceCorrectionType.REFUND:c=build_client_refund_candidate(s.case_no,f.bank_facts,f.obligations,s.refund_purpose)
 elif s.correction_type is ClientFinanceCorrectionType.REFUND_RETURN:c=build_client_refund_return_candidate(s.case_no,f.refund_return_bank_facts[0],f.reversal_targets[0])
 else:c=build_client_reversal_candidate(s.case_no,f.reversal_targets)
 return ClientRefundReversalPreview(c,f.account_version,fingerprint_payload({"selection":_payload(s),"version":f.account_version,"candidate":c.fingerprint.value}))
def _selection_shape(s):
 refund=s.correction_type is ClientFinanceCorrectionType.REFUND
 refund_return=s.correction_type is ClientFinanceCorrectionType.REFUND_RETURN
 active=(s.bank_fact_identities,s.obligation_identities) if refund else ((s.bank_fact_identities,s.reversal_target_identities) if refund_return else (s.reversal_target_identities,))
 if not all(active) or any(not isinstance(xs,tuple) or xs!=tuple(sorted(set(xs))) for xs in active):raise ValueError("invalid_client_finance_intent")
 if refund and (s.reversal_target_identities or s.reversal_occurred_on is not None):raise ValueError("invalid_client_finance_intent")
 if refund_return and (s.obligation_identities or s.reversal_occurred_on is not None or len(s.bank_fact_identities)!=1 or len(s.reversal_target_identities)!=1):raise ValueError("invalid_client_finance_intent")
 if not refund and not refund_return and (s.bank_fact_identities or s.obligation_identities or s.reversal_occurred_on is None):raise ValueError("invalid_client_finance_intent")
def _facts(s,f):
 if s.correction_type is ClientFinanceCorrectionType.REFUND and (any(x.case_no!=s.case_no for x in (*f.bank_facts,*f.obligations)) or not f.bank_facts or not f.obligations):raise ValueError("invalid_client_finance_intent")
 if s.correction_type is ClientFinanceCorrectionType.REFUND_RETURN and (len(f.refund_return_bank_facts)!=1 or len(f.reversal_targets)!=1 or f.refund_return_bank_facts[0].case_no!=s.case_no or f.reversal_targets[0].case_no!=s.case_no):raise ValueError("invalid_client_finance_intent")
 if s.correction_type is ClientFinanceCorrectionType.REVERSAL and (not f.reversal_targets or any(x.case_no!=s.case_no for x in f.reversal_targets)):raise ValueError("invalid_client_finance_intent")
def _payload(s):return {"case_no":s.case_no,"type":s.correction_type.value,"purpose":s.refund_purpose.value,"bank":s.bank_fact_identities,"obligation":s.obligation_identities,"target":s.reversal_target_identities,"occurred_on":s.reversal_occurred_on}
def _command(r):return fingerprint_payload({"selection":_payload(r.selection),"expected":r.expected_account_version.value,"preview":r.preview_fingerprint.value,"actor":r.actor.actor_id,"reason":r.reason})
def _error(c,category,code,retryable=False,current=None):return ClientRefundReversalError(TypedError(category,code or "transaction_failed","Client refund/reversal failed.",c,retryable=retryable,current_version=None if current is None else ExpectedVersion(current)))
__all__=[name for name in globals() if name.startswith("Client") or name.startswith("Stored")]
