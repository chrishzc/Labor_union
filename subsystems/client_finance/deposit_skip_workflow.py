"""Preview/apply workflow for an unpaid-deposit progression override."""
from dataclasses import dataclass
from typing import Protocol, Callable
from domains.client_finance.deposit_skip import DepositSkipFacts, DepositSkipCandidate, build_deposit_skip_candidate
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.validation import require_canonical_text

@dataclass(frozen=True, slots=True)
class DepositSkipSelection:
    case_no: str
@dataclass(frozen=True, slots=True)
class DepositSkipApplyRequest:
    selection: DepositSkipSelection
    expected_account_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId
    def __post_init__(self): require_canonical_text(self.reason, "deposit override reason", 500)
@dataclass(frozen=True, slots=True)
class DepositSkipReceipt:
    case_no: str; account_version: int; unpaid_progression_allowed: bool; replayed: bool=False
@dataclass(frozen=True, slots=True)
class StoredDepositSkipReceipt:
    command_fingerprint: PreviewFingerprint; receipt: DepositSkipReceipt
class DepositSkipError(Exception):
    def __init__(self, error): self.error=error; super().__init__(error.code)
class Repository(Protocol):
    def load(self, selection, *, for_update: bool) -> DepositSkipFacts: ...
    def find_receipt(self, key): ...
    def apply(self, candidate, request): ...
    def save_receipt(self, key, stored, preview): ...

class DepositSkipWorkflow:
    def __init__(self, repository: Repository, unit_of_work_factory: Callable[[], object]): self.repo=repository; self.uow=unit_of_work_factory
    def preview(self, selection): return build_deposit_skip_candidate(self.repo.load(selection, for_update=False))
    def apply(self, request):
        command=fingerprint_payload({"case_no":request.selection.case_no,"version":request.expected_account_version.value,"preview":request.preview_fingerprint.value,"actor":request.actor.actor_id,"reason":request.reason})
        with self.uow() as unit:
            stored=self.repo.find_receipt(request.idempotency_key)
            if stored:
                if stored.command_fingerprint != command: raise self._error(request,"deposit_skip.idempotency_conflict",ErrorCategory.IDEMPOTENCY_MISMATCH)
                unit.commit(); return DepositSkipReceipt(stored.receipt.case_no,stored.receipt.account_version,True,True)
            candidate=build_deposit_skip_candidate(self.repo.load(request.selection,for_update=True))
            if candidate.expected_account_version != request.expected_account_version.value or candidate.fingerprint != request.preview_fingerprint:
                raise self._error(request,"deposit_skip.candidate_stale",ErrorCategory.CONFLICT)
            if candidate.blockers:
                raise DepositSkipError(TypedError(ErrorCategory.DOMAIN_BLOCKED,candidate.blockers[0],"目前不能允許訂金未付仍推進。",request.correlation_id,domain_blockers=candidate.blockers))
            if candidate.mutates: self.repo.apply(candidate,request)
            receipt=DepositSkipReceipt(candidate.case_no,candidate.resulting_account_version,True)
            self.repo.save_receipt(request.idempotency_key,StoredDepositSkipReceipt(command,receipt),candidate.fingerprint)
            unit.commit(); return receipt
    @staticmethod
    def _error(request,code,category): return DepositSkipError(TypedError(category,code,"訂金未付人工放行失敗。",request.correlation_id))

__all__=[name for name in globals() if name.startswith("DepositSkip") or name.startswith("StoredDepositSkip")]
