"""Preview/apply orchestration for a canonical deposit receipt reversal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Protocol

from domains.client_finance.deposit_lifecycle import (
    DepositLifecycleEvent,
    DepositLifecycleFacts,
    DepositLifecycleImpact,
    decide_deposit_lifecycle_impact,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer


DEPOSIT_REVERSAL_STALE = "deposit_reversal_candidate_stale"
DEPOSIT_REVERSAL_IDEMPOTENCY_CONFLICT = "deposit_reversal_idempotency_conflict"


@dataclass(frozen=True, slots=True)
class DepositReversalSelection:
    case_no: str
    original_ledger_entry_id: int
    reversal_occurred_on: date

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        if self.original_ledger_entry_id < 1:
            raise ValueError("deposit reversal ledger entry is invalid")
        if not isinstance(self.reversal_occurred_on, date):
            raise TypeError("deposit reversal date is invalid")


@dataclass(frozen=True, slots=True)
class DepositReversalFacts:
    case_no: str
    account_version: int
    deposit_obligation_identity: str
    contracted_amount_ntd: int
    deposit_due_date: date | None
    settlement_identity: PreviewFingerprint
    original_ledger_entry_id: int
    original_ledger_amount_ntd: int
    actual_start_exists: bool
    service_started: bool
    service_completed: bool
    confirmed_settlement_identity: PreviewFingerprint | None

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        require_nonnegative_integer(self.account_version, "client account version")
        require_canonical_text(
            self.deposit_obligation_identity,
            "deposit obligation identity",
            191,
        )
        if self.contracted_amount_ntd < 1 or self.original_ledger_amount_ntd < 1:
            raise ValueError("deposit amount is invalid")
        if self.contracted_amount_ntd != self.original_ledger_amount_ntd:
            raise ValueError("deposit reversal must reverse the exact receipt")
        if self.original_ledger_entry_id < 1:
            raise ValueError("original deposit ledger entry is invalid")


@dataclass(frozen=True, slots=True)
class DepositReversalCandidate:
    case_no: str
    deposit_obligation_identity: str
    original_ledger_entry_id: int
    reversal_amount_ntd: int
    reversed_settlement_identity: PreviewFingerprint
    reversal_occurred_on: date
    resulting_account_version: int
    lifecycle_impact: DepositLifecycleImpact
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class DepositReversalPreview:
    candidate: DepositReversalCandidate
    account_version: int
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class DepositReversalApplyRequest:
    selection: DepositReversalSelection
    expected_account_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class DepositReversalReceipt:
    case_no: str
    account_version: int
    original_ledger_entry_id: int
    reversal_amount_ntd: int
    lifecycle_intent: DepositLifecycleEvent
    anomaly_code: str | None


@dataclass(frozen=True, slots=True)
class StoredDepositReversalReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: DepositReversalReceipt


class DepositReversalError(Exception):
    def __init__(self, error: TypedError) -> None:
        self.error = error
        super().__init__(error.code)


class DepositReversalRepository(Protocol):
    def load(self, selection: DepositReversalSelection, *, for_update: bool) -> DepositReversalFacts: ...
    def find_receipt(self, key: IdempotencyKey) -> StoredDepositReversalReceipt | None: ...
    def append_reversal_ledger_entry(self, candidate: DepositReversalCandidate) -> None: ...
    def reopen_deposit_obligation(self, candidate: DepositReversalCandidate) -> None: ...
    def replace_deposit_settlement(self, candidate: DepositReversalCandidate) -> None: ...
    def append_orders_lifecycle_intent(self, candidate: DepositReversalCandidate) -> None: ...
    def append_anomaly_intent(self, candidate: DepositReversalCandidate) -> None: ...
    def save_receipt(self, key: IdempotencyKey, receipt: StoredDepositReversalReceipt) -> None: ...


class DepositReversalWorkflow:
    def __init__(self, repository: DepositReversalRepository, unit_of_work_factory: Callable[[], object]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def preview(self, selection: DepositReversalSelection) -> DepositReversalPreview:
        return _preview(selection, self._repository.load(selection, for_update=False))

    def apply(self, request: DepositReversalApplyRequest) -> DepositReversalReceipt:
        command = _command_fingerprint(request)
        with self._unit_of_work_factory() as unit:
            replay = self._repository.find_receipt(request.idempotency_key)
            if replay is not None:
                if replay.command_fingerprint != command:
                    raise _error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, DEPOSIT_REVERSAL_IDEMPOTENCY_CONFLICT)
                return replay.receipt
            preview = _preview(request.selection, self._repository.load(request.selection, for_update=True))
            if preview.account_version != request.expected_account_version.value or preview.fingerprint != request.preview_fingerprint:
                raise _error(request, ErrorCategory.CONFLICT, DEPOSIT_REVERSAL_STALE, preview.account_version)
            receipt = _receipt(preview.candidate)
            self._persist(request, preview.candidate, command)
            unit.commit()
            return receipt

    def _persist(self, request, candidate, command) -> None:
        self._repository.append_reversal_ledger_entry(candidate)
        self._repository.reopen_deposit_obligation(candidate)
        self._repository.replace_deposit_settlement(candidate)
        self._repository.append_orders_lifecycle_intent(candidate)
        if candidate.lifecycle_impact.anomaly_code is not None:
            self._repository.append_anomaly_intent(candidate)
        self._repository.save_receipt(
            request.idempotency_key,
            StoredDepositReversalReceipt(command, _receipt(candidate)),
        )


def _preview(selection, facts):
    _validate_selection(selection, facts)
    impact = decide_deposit_lifecycle_impact(
        DepositLifecycleFacts(
            selection.case_no,
            DepositLifecycleEvent.REVERSAL,
            False,
            None,
            facts.actual_start_exists,
            facts.service_started,
            facts.service_completed,
            facts.confirmed_settlement_identity,
        )
    )
    candidate = DepositReversalCandidate(
        selection.case_no,
        facts.deposit_obligation_identity,
        facts.original_ledger_entry_id,
        facts.original_ledger_amount_ntd,
        facts.settlement_identity,
        selection.reversal_occurred_on,
        facts.account_version + 1,
        impact,
        fingerprint_payload(_candidate_payload(selection, facts, impact)),
    )
    return DepositReversalPreview(
        candidate,
        facts.account_version,
        fingerprint_payload({"candidate": candidate.fingerprint.value, "account_version": facts.account_version}),
    )


def _validate_selection(selection, facts) -> None:
    if selection.case_no != facts.case_no:
        raise ValueError("deposit reversal obligation case differs")
    if selection.original_ledger_entry_id != facts.original_ledger_entry_id:
        raise ValueError("deposit reversal target is not current settlement receipt")


def _candidate_payload(selection, facts, impact):
    return {
        "case_no": selection.case_no,
        "original_ledger_entry_id": facts.original_ledger_entry_id,
        "reversal_occurred_on": selection.reversal_occurred_on.isoformat(),
        "settlement_identity": facts.settlement_identity.value,
        "account_version": facts.account_version,
        "lifecycle_impact": impact.fingerprint.value,
    }


def _receipt(candidate):
    return DepositReversalReceipt(
        candidate.case_no,
        candidate.resulting_account_version,
        candidate.original_ledger_entry_id,
        candidate.reversal_amount_ntd,
        candidate.lifecycle_impact.lifecycle_intent,
        candidate.lifecycle_impact.anomaly_code,
    )


def _command_fingerprint(request):
    return fingerprint_payload(
        {
            "selection": {
                "case_no": request.selection.case_no,
                "original_ledger_entry_id": request.selection.original_ledger_entry_id,
                "reversal_occurred_on": request.selection.reversal_occurred_on.isoformat(),
            },
            "expected_account_version": request.expected_account_version.value,
            "preview_fingerprint": request.preview_fingerprint.value,
            "actor": request.actor.actor_id,
            "reason": request.reason,
        }
    )


def _error(request, category, code, current=None):
    return DepositReversalError(
        TypedError(
            category,
            code,
            "Deposit reversal failed.",
            request.correlation_id,
            current_version=None if current is None else ExpectedVersion(current),
        )
    )
