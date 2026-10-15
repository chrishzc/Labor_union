"""Dedicated Preview/Apply workflow for Government Subsidy overpayments."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from domains.government_subsidy.overpayment import GovernmentSubsidyOffsetIntent, GovernmentSubsidyOverpayment, GovernmentSubsidyOverpaymentCandidate, build_overpayment_offset_candidate
from domains.government_subsidy.overpayment import build_receipt_with_overage_candidate
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey


@dataclass(frozen=True, slots=True)
class OffsetApplyRequest:
    identity: str; intents: tuple[GovernmentSubsidyOffsetIntent, ...]; expected_version: ExpectedVersion; preview_fingerprint: PreviewFingerprint; idempotency_key: IdempotencyKey; actor: ActorContext; reason: str; evidence_reference: str; correlation_id: CorrelationId








class Repository(Protocol):
    def load_overage_receipt_context(self, row_id: int, batch_id: int, *, lock: bool): ...
    def persist_receipt_with_overage(self, request, candidate, bank, batch) -> dict: ...
    def load_overpayment(self, identity: str, *, lock: bool) -> GovernmentSubsidyOverpayment: ...
    def load_offset_targets(self, intents: tuple[GovernmentSubsidyOffsetIntent, ...], *, lock: bool): ...
    def persist_offset(self, request: OffsetApplyRequest, candidate: GovernmentSubsidyOverpaymentCandidate) -> dict: ...


class GovernmentSubsidyOverpaymentWorkflow:
    def __init__(self, repository: Repository, unit_of_work_factory: Callable): self._repository, self._uow = repository, unit_of_work_factory

    def preview_offset(self, identity, intents):
        return build_overpayment_offset_candidate(self._repository.load_overpayment(identity, lock=False), self._repository.load_offset_targets(intents, lock=False), intents)


    def preview_receipt_with_overage(self, row_id, batch_id, intents):
        bank, batch = self._repository.load_overage_receipt_context(row_id, batch_id, lock=False)
        return build_receipt_with_overage_candidate(bank, batch, intents)

    def apply_receipt_with_overage(self, request):
        with self._uow() as unit_of_work:
            bank, batch = self._repository.load_overage_receipt_context(request.finance_import_row_id, request.batch_id, lock=True)
            candidate = build_receipt_with_overage_candidate(bank, batch, request.allocations)
            if request.expected_version.value != batch.aggregate_version: raise ValueError("government_subsidy_overpayment_version_conflict")
            if request.preview_fingerprint != candidate.fingerprint: raise ValueError("government_subsidy_overpayment_preview_stale")
            receipt = self._repository.persist_receipt_with_overage(request, candidate, bank, batch)
            unit_of_work.commit()
            return receipt

    def apply_offset(self, request):
        with self._uow() as unit_of_work:
            root = self._repository.load_overpayment(request.identity, lock=True)
            replay = _replay(self._repository, request, "offset")
            if replay is not None: return replay
            candidate = build_overpayment_offset_candidate(root, self._repository.load_offset_targets(request.intents, lock=True), request.intents)
            _verify(request, root, candidate)
            receipt = self._repository.persist_offset(request, candidate)
            _save_receipt(self._repository, request, candidate, receipt, "offset")
            unit_of_work.commit()
            return receipt






def _verify(request, root, candidate):
    if request.expected_version.value != root.version: raise ValueError("government_subsidy_overpayment_version_conflict")
    if request.preview_fingerprint != candidate.fingerprint: raise ValueError("government_subsidy_overpayment_preview_stale")


def _replay(repository, request, command_kind):
    finder = getattr(repository, "find_overpayment_apply_receipt", None)
    if finder is None:
        return None
    return finder(request.idempotency_key, _command_fingerprint(request, command_kind))


def _save_receipt(repository, request, candidate, receipt, command_kind):
    saver = getattr(repository, "save_overpayment_apply_receipt", None)
    if saver is not None:
        saver(request, candidate, receipt, command_kind, _command_fingerprint(request, command_kind))


def _command_fingerprint(request, command_kind):
    payload = {
        "kind": command_kind,
        "identity": request.identity,
        "expected_version": request.expected_version.value,
        "preview_fingerprint": request.preview_fingerprint.value,
        "actor": request.actor.actor_id,
        "reason": request.reason,
    }
    if isinstance(request, OffsetApplyRequest):
        payload["intents"] = tuple((item.claim_item_id, item.amount_ntd.amount) for item in request.intents)
        payload["evidence_reference"] = request.evidence_reference
    else:
        payload["finance_import_row_id"] = request.finance_import_row_id
        payload["evidence_reference"] = request.evidence_reference
    return fingerprint_payload(payload)
@dataclass(frozen=True, slots=True)
class ReceiptWithOverageApplyRequest:
    finance_import_row_id: int; batch_id: int; allocations: tuple[GovernmentSubsidyOffsetIntent, ...]; evidence_reference: str; expected_version: ExpectedVersion; preview_fingerprint: PreviewFingerprint; idempotency_key: IdempotencyKey; actor: ActorContext; reason: str; correlation_id: CorrelationId
