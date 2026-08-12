"""Preview/apply orchestration for exact client receipt reconciliation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from domains.client_finance.reconciliation import (ClientObligation, ClientReconciliationCandidate, IncomingBankFact, PaymentStage, ReconciliationStatus, build_reconciliation_candidate)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer

CLIENT_FINANCE_CANDIDATE_STALE = "client_finance_candidate_stale"
CLIENT_FINANCE_IDEMPOTENCY_CONFLICT = "client_finance_idempotency_conflict"

@dataclass(frozen=True, slots=True)
class ReconciliationSelection:
    case_no: str; payment_stage: PaymentStage; bank_fact_identities: tuple[str, ...]; obligation_identities: tuple[str, ...]; allow_overage_disposition: bool = False
    def __post_init__(self):
        require_canonical_text(self.case_no, "case number", 191); _ids(self.bank_fact_identities); _ids(self.obligation_identities)
        if not isinstance(self.allow_overage_disposition, bool): raise ValueError("invalid_client_receipt_intent")

@dataclass(frozen=True, slots=True)
class ClientReconciliationFacts:
    account_version: int; bank_facts: tuple[IncomingBankFact, ...]; obligations: tuple[ClientObligation, ...]
    def __post_init__(self): require_nonnegative_integer(self.account_version, "client account version")

@dataclass(frozen=True, slots=True)
class ClientReconciliationPreview:
    candidate: ClientReconciliationCandidate; account_version: int; fingerprint: PreviewFingerprint

@dataclass(frozen=True, slots=True)
class ClientReconciliationApplyRequest:
    selection: ReconciliationSelection; expected_account_version: ExpectedVersion; preview_fingerprint: PreviewFingerprint; idempotency_key: IdempotencyKey; actor: ActorContext; reason: str; correlation_id: CorrelationId

@dataclass(frozen=True, slots=True)
class ClientReconciliationReceipt:
    case_no: str; account_version: int; status: ReconciliationStatus; settlement_identity: PreviewFingerprint; ledger_entry_count: int; allocation_count: int; blockers: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class StoredClientReconciliationReceipt:
    command_fingerprint: PreviewFingerprint; receipt: ClientReconciliationReceipt

class ClientReconciliationError(Exception):
    def __init__(self, error: TypedError): self.error = error; super().__init__(error.code)

class ClientReconciliationRepository(Protocol):
    def load(self, selection: ReconciliationSelection, *, for_update: bool) -> ClientReconciliationFacts: ...
    def find_receipt(self, key: IdempotencyKey) -> StoredClientReconciliationReceipt | None: ...
    def append_ledger_entries(self, candidate: ClientReconciliationCandidate) -> None: ...
    def append_allocations(self, candidate: ClientReconciliationCandidate) -> None: ...
    def establish_overage_refund(self, candidate: ClientReconciliationCandidate, resulting_version: int) -> None: ...
    def update_projection(self, selection: ReconciliationSelection, resulting_version: int) -> None: ...
    def append_orders_deposit_intent(self, candidate: ClientReconciliationCandidate) -> None: ...
    def append_anomaly_intent(self, candidate: ClientReconciliationCandidate) -> None: ...
    def save_receipt(self, key: IdempotencyKey, receipt: StoredClientReconciliationReceipt) -> None: ...

class ClientReconciliationWorkflow:
    def __init__(self, repository: ClientReconciliationRepository, unit_of_work_factory: Callable[[], object]): self._repository=repository; self._unit_of_work_factory=unit_of_work_factory
    def preview(self, selection: ReconciliationSelection) -> ClientReconciliationPreview: return _preview(selection, self._repository.load(selection, for_update=False))
    def apply(self, request: ClientReconciliationApplyRequest) -> ClientReconciliationReceipt:
        command = _command(request)
        with self._unit_of_work_factory() as unit:
            replay=self._repository.find_receipt(request.idempotency_key)
            if replay is not None:
                if replay.command_fingerprint != command: raise _error(request.correlation_id, ErrorCategory.IDEMPOTENCY_MISMATCH, CLIENT_FINANCE_IDEMPOTENCY_CONFLICT)
                return replay.receipt
            preview=_preview(request.selection, self._repository.load(request.selection, for_update=True))
            if preview.account_version != request.expected_account_version.value or preview.fingerprint != request.preview_fingerprint: raise _error(request.correlation_id, ErrorCategory.CONFLICT, CLIENT_FINANCE_CANDIDATE_STALE, current=preview.account_version)
            receipt=_receipt(request, preview)
            self._repository.append_ledger_entries(preview.candidate); self._repository.append_allocations(preview.candidate)
            self._repository.update_projection(request.selection, receipt.account_version)
            if preview.candidate.status is ReconciliationStatus.OVERAGE:
                self._repository.establish_overage_refund(preview.candidate, receipt.account_version)
            (self._repository.append_orders_deposit_intent if preview.candidate.status in {ReconciliationStatus.EXACT, ReconciliationStatus.OVERAGE} and preview.candidate.payment_stage is PaymentStage.DEPOSIT else self._repository.append_anomaly_intent)(preview.candidate)
            self._repository.save_receipt(request.idempotency_key, StoredClientReconciliationReceipt(command, receipt)); unit.commit(); return receipt

def _preview(selection, facts):
    _facts(selection, facts); candidate=build_reconciliation_candidate(facts.bank_facts, facts.obligations,allow_overage_disposition=selection.allow_overage_disposition)
    return ClientReconciliationPreview(candidate, facts.account_version, fingerprint_payload({"selection":_selection(selection), "account_version":facts.account_version, "candidate":candidate.settlement_identity.value}))
def _receipt(request, preview):
    c=preview.candidate; return ClientReconciliationReceipt(request.selection.case_no, preview.account_version+1, c.status, c.settlement_identity, len(c.allocations and {x.bank_fact_identity for x in c.allocations}), len(c.allocations), c.blockers)
def _facts(selection, facts):
    if any(x.payment_stage is not selection.payment_stage for x in (*facts.bank_facts,*facts.obligations)) or any(x.case_no != selection.case_no for x in facts.obligations): raise ValueError("invalid_client_receipt_facts")
def _ids(values):
    if not isinstance(values,tuple) or not values or values != tuple(sorted(set(values))): raise ValueError("invalid_client_receipt_intent")
    for value in values: require_canonical_text(value,"identity",191)
def _selection(s): return {"case_no":s.case_no,"payment_stage":s.payment_stage.value,"bank_fact_identities":s.bank_fact_identities,"obligation_identities":s.obligation_identities,"allow_overage_disposition":s.allow_overage_disposition}
def _command(r): return fingerprint_payload({"selection":_selection(r.selection),"expected_account_version":r.expected_account_version.value,"preview_fingerprint":r.preview_fingerprint.value,"actor":r.actor.actor_id,"reason":r.reason})
def _error(correlation, category, code, current=None): return ClientReconciliationError(TypedError(category,code,"Client receipt reconciliation failed.",correlation,current_version=None if current is None else ExpectedVersion(current)))
__all__=[name for name in globals() if name.startswith("Client") or name=="ReconciliationSelection"]
