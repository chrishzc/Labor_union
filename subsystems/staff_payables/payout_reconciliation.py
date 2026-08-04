"""Typed Preview and atomic Apply for Staff Payout Reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, TypeAlias

from domains.staff_payables.reconciliation import (
    OutgoingBankFact,
    StaffPayableFacts,
    StaffPayableStatus,
    StaffPayoutCandidate,
    StaffPayoutEventType,
    StaffPayoutReopenCandidate,
    StaffPayoutReopenFact,
    StaffPrimaryBankAccount,
    build_staff_payout_candidate,
    build_staff_payout_reopen_candidate,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer

_IDENTITY_MAXIMUM_LENGTH = 191
_REASON_MAXIMUM_LENGTH = 500
StaffPayoutFormalCandidate: TypeAlias = StaffPayoutCandidate | StaffPayoutReopenCandidate


@dataclass(frozen=True, slots=True)
class StaffPayoutSelection:
    event_type: StaffPayoutEventType
    bank_fact_identities: tuple[str, ...]
    obligation_identities: tuple[str, ...]
    reopen_fact_identity: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, StaffPayoutEventType):
            raise TypeError("staff payout event type is invalid")
        _validate_identity_tuple(self.obligation_identities, "staff obligations", required=True)
        _validate_selection_intent(self)


@dataclass(frozen=True, slots=True)
class StaffPayoutReconciliationFacts:
    staff_payables_version: int
    bank_facts_version: int
    bank_facts: tuple[OutgoingBankFact, ...]
    bank_accounts: tuple[StaffPrimaryBankAccount, ...]
    obligations: tuple[StaffPayableFacts, ...]
    reopen_fact: StaffPayoutReopenFact | None = None
    blocking_anomalies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_nonnegative_integer(self.staff_payables_version, "staff payables version")
        require_nonnegative_integer(self.bank_facts_version, "bank facts version")
        _require_tuple(self.bank_facts, "bank facts")
        _require_tuple(self.bank_accounts, "bank accounts")
        _require_tuple(self.obligations, "staff obligations")
        _validate_identity_tuple(self.blocking_anomalies, "blocking anomalies", required=False)


@dataclass(frozen=True, slots=True)
class StaffPayoutReconciliationPreview:
    candidate: StaffPayoutFormalCandidate
    staff_payables_version: int
    bank_facts_version: int
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StaffPayoutApplyRequest:
    selection: StaffPayoutSelection
    expected_staff_payables_version: ExpectedVersion
    expected_bank_facts_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.reason, "reason", _REASON_MAXIMUM_LENGTH)


@dataclass(frozen=True, slots=True)
class StaffPayoutReceipt:
    event_type: StaffPayoutEventType
    staff_id: int
    staff_payables_version: int
    bank_facts_version: int
    resulting_status: StaffPayableStatus
    event_count: int
    obligation_link_count: int
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StoredStaffPayoutReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: StaffPayoutReceipt


class StaffPayoutReconciliationRepository(Protocol):
    def load(self, selection: StaffPayoutSelection, *, for_update: bool) -> StaffPayoutReconciliationFacts: ...
    def find_receipt(self, key: IdempotencyKey) -> StoredStaffPayoutReceipt | None: ...
    def append_events(self, candidate: StaffPayoutFormalCandidate) -> None: ...
    def append_obligation_links(self, candidate: StaffPayoutFormalCandidate) -> None: ...
    def update_payable_projection(self, selection: StaffPayoutSelection, resulting_version: int, resulting_status: StaffPayableStatus) -> None: ...
    def append_outbox(self, candidate: StaffPayoutFormalCandidate) -> None: ...
    def save_receipt(self, key: IdempotencyKey, stored_receipt: StoredStaffPayoutReceipt) -> None: ...


class StaffPayoutRepositoryUnavailable(RuntimeError):
    """Signals a transient storage failure that permits exact command retry."""


class StaffPayoutReconciliationError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.code)
        self.error = error


class StaffPayoutReconciliationWorkflow:
    def __init__(self, repository: StaffPayoutReconciliationRepository, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def preview(self, selection: StaffPayoutSelection, correlation_id: CorrelationId) -> StaffPayoutReconciliationPreview:
        facts = self._repository.load(selection, for_update=False)
        return _build_typed_preview(selection, facts, correlation_id)

    def apply(self, request: StaffPayoutApplyRequest) -> StaffPayoutReceipt:
        try:
            return self._apply_in_unit_of_work(request)
        except StaffPayoutReconciliationError:
            raise
        except StaffPayoutRepositoryUnavailable as error:
            raise _transaction_error(request, error, retryable=True) from error
        except Exception as error:
            raise _transaction_error(request, error, retryable=False) from error

    def _apply_in_unit_of_work(self, request: StaffPayoutApplyRequest) -> StaffPayoutReceipt:
        command_fingerprint = _command_fingerprint(request)
        with self._unit_of_work_factory() as unit_of_work:
            replay = self._find_replay(request, command_fingerprint)
            if replay is not None:
                return replay
            preview = self._fresh_preview(request)
            receipt = _build_receipt(request, preview)
            self._persist(request, preview, command_fingerprint, receipt)
            unit_of_work.commit()
            return receipt

    def _find_replay(self, request: StaffPayoutApplyRequest, command_fingerprint: PreviewFingerprint) -> StaffPayoutReceipt | None:
        stored = self._repository.find_receipt(request.idempotency_key)
        if stored is None:
            return None
        if stored.command_fingerprint == command_fingerprint:
            return stored.receipt
        raise _workflow_error(request.correlation_id, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_conflict", "Idempotency key was used by another Staff Payables command.")

    def _fresh_preview(self, request: StaffPayoutApplyRequest) -> StaffPayoutReconciliationPreview:
        facts = self._repository.load(request.selection, for_update=True)
        _validate_expected_versions(request, facts)
        preview = _build_typed_preview(request.selection, facts, request.correlation_id)
        if preview.fingerprint != request.preview_fingerprint:
            raise _stale_error(request, "Staff payout facts changed after Preview.")
        return preview

    def _persist(self, request, preview, command_fingerprint, receipt) -> None:
        candidate = preview.candidate
        self._repository.append_events(candidate)
        self._repository.append_obligation_links(candidate)
        self._repository.update_payable_projection(request.selection, receipt.staff_payables_version, receipt.resulting_status)
        self._repository.append_outbox(candidate)
        self._repository.save_receipt(request.idempotency_key, StoredStaffPayoutReceipt(command_fingerprint, receipt))


def _build_typed_preview(selection, facts, correlation_id):
    try:
        return _build_preview(selection, facts)
    except ValueError as error:
        raise _domain_error(correlation_id, str(error)) from error


def _build_preview(selection, facts):
    _validate_loaded_facts(selection, facts)
    candidate = _build_candidate(selection, facts)
    fingerprint = fingerprint_payload({
        "selection": _selection_payload(selection),
        "staff_payables_version": facts.staff_payables_version,
        "bank_facts_version": facts.bank_facts_version,
        "root_facts": _root_facts_payload(facts),
        "candidate_fingerprint": candidate.fingerprint.value,
    })
    return StaffPayoutReconciliationPreview(candidate, facts.staff_payables_version, facts.bank_facts_version, fingerprint)


def _build_candidate(selection, facts):
    if selection.event_type is StaffPayoutEventType.PAYOUT:
        return build_staff_payout_candidate(facts.bank_facts, facts.obligations, bank_accounts=facts.bank_accounts, blocking_anomalies=facts.blocking_anomalies, require_primary_account_owner=True)
    if facts.reopen_fact is None:
        raise ValueError("staff_payout_reversal_invalid")
    return build_staff_payout_reopen_candidate(facts.reopen_fact, facts.obligations)


def _validate_loaded_facts(selection, facts) -> None:
    bank_identities = tuple(sorted(item.identity for item in facts.bank_facts))
    obligation_identities = tuple(sorted(item.obligation_identity for item in facts.obligations))
    if bank_identities != selection.bank_fact_identities:
        raise ValueError("outgoing_bank_fact_not_eligible")
    if obligation_identities != selection.obligation_identities:
        raise ValueError("staff_payable_not_found")
    _validate_loaded_reopen_fact(selection, facts.reopen_fact)


def _validate_loaded_reopen_fact(selection, reopen_fact) -> None:
    if selection.event_type is StaffPayoutEventType.PAYOUT:
        if reopen_fact is not None:
            raise ValueError("invalid_staff_payout_intent")
        return
    if reopen_fact is None or reopen_fact.identity != selection.reopen_fact_identity or reopen_fact.event_type is not selection.event_type:
        raise ValueError("staff_payout_reversal_invalid")


def _validate_expected_versions(request, facts) -> None:
    expected = (request.expected_staff_payables_version.value, request.expected_bank_facts_version.value)
    current = (facts.staff_payables_version, facts.bank_facts_version)
    if expected != current:
        raise _stale_error(request, "Staff payout aggregate version changed.")


def _build_receipt(request, preview) -> StaffPayoutReceipt:
    candidate = preview.candidate
    return StaffPayoutReceipt(request.selection.event_type, candidate.staff_id, preview.staff_payables_version + 1, preview.bank_facts_version, candidate.resulting_status, len(_candidate_events(candidate)), len(candidate.obligation_links), preview.fingerprint)


def _candidate_events(candidate):
    return candidate.events if isinstance(candidate, StaffPayoutCandidate) else (candidate.event,)


def _command_fingerprint(request) -> PreviewFingerprint:
    return fingerprint_payload({
        "selection": _selection_payload(request.selection),
        "staff_payables_version": request.expected_staff_payables_version.value,
        "bank_facts_version": request.expected_bank_facts_version.value,
        "preview_fingerprint": request.preview_fingerprint.value,
        "actor_id": request.actor.actor_id,
        "reason": request.reason,
    })


def _selection_payload(selection):
    return {"event_type": selection.event_type.value, "bank_fact_identities": selection.bank_fact_identities, "obligation_identities": selection.obligation_identities, "reopen_fact_identity": selection.reopen_fact_identity}


def _root_facts_payload(facts):
    return {"bank_facts": _sorted_bank_fact_payloads(facts.bank_facts), "bank_accounts": _sorted_bank_account_payloads(facts.bank_accounts), "obligations": _sorted_obligation_payloads(facts.obligations), "reopen_fact": _reopen_fact_payload(facts.reopen_fact), "blocking_anomalies": facts.blocking_anomalies}


def _sorted_bank_fact_payloads(bank_facts):
    return tuple(_bank_fact_payload(item) for item in sorted(bank_facts, key=lambda item: item.identity))


def _sorted_bank_account_payloads(bank_accounts):
    return tuple(_bank_account_payload(item) for item in sorted(bank_accounts, key=lambda item: item.identity))


def _sorted_obligation_payloads(obligations):
    return tuple(_obligation_payload(item) for item in sorted(obligations, key=lambda item: item.obligation_identity))


def _bank_fact_payload(bank_fact):
    return {"identity": bank_fact.identity, "staff_id": bank_fact.staff_id, "amount_ntd": bank_fact.amount.amount, "bank_account_identity": bank_fact.bank_account_identity, "direction": bank_fact.direction.value, "raw_fact_identity": bank_fact.canonical_raw_fact_identity, "eligible": bank_fact.eligible, "blocking_anomalies": bank_fact.blocking_anomalies}


def _bank_account_payload(bank_account):
    return {"identity": bank_account.identity, "owner_staff_id": bank_account.owner_staff_id, "active": bank_account.active, "primary": bank_account.primary}


def _obligation_payload(obligation):
    return {"identity": obligation.obligation_identity, "staff_id": obligation.staff_id, "amount_due_ntd": obligation.amount_due.amount, "events": tuple(_existing_event_payload(item) for item in sorted(obligation.events, key=lambda item: item.identity))}


def _existing_event_payload(event):
    return {"identity": event.identity, "event_type": event.event_type.value, "amount_ntd": event.amount.amount, "reversal_of_event_identity": event.reversal_of_event_identity, "status": event.status.value}


def _reopen_fact_payload(reopen_fact):
    if reopen_fact is None:
        return None
    return {"identity": reopen_fact.identity, "event_type": reopen_fact.event_type.value, "staff_id": reopen_fact.staff_id, "amount_ntd": reopen_fact.amount.amount, "source_payout_event_identity": reopen_fact.source_payout_event_identity, "succeeded": reopen_fact.succeeded, "blocking_anomalies": reopen_fact.blocking_anomalies}


def _domain_error(correlation_id, code):
    category = _domain_error_category(code)
    blockers = (code,) if category is ErrorCategory.DOMAIN_BLOCKED else ()
    return StaffPayoutReconciliationError(TypedError(category, code, "Staff payout facts do not permit a formal ledger event.", correlation_id, domain_blockers=blockers))


def _domain_error_category(code):
    if code == "staff_payable_not_found":
        return ErrorCategory.NOT_FOUND
    if code == "invalid_staff_payout_intent":
        return ErrorCategory.VALIDATION
    return ErrorCategory.DOMAIN_BLOCKED


def _stale_error(request, message):
    return StaffPayoutReconciliationError(TypedError(ErrorCategory.CONFLICT, "staff_payable_candidate_stale", message, request.correlation_id, current_version=request.expected_staff_payables_version))


def _transaction_error(request, error, *, retryable):
    del error
    category = ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL
    message = "Staff payout storage is temporarily unavailable." if retryable else "Staff payout transaction failed and was rolled back."
    return StaffPayoutReconciliationError(TypedError(category, "transaction_failed", message, request.correlation_id, retryable=retryable))


def _workflow_error(correlation_id, category, code, message):
    return StaffPayoutReconciliationError(TypedError(category, code, message, correlation_id))


def _validate_selection_intent(selection) -> None:
    if selection.event_type is StaffPayoutEventType.PAYOUT:
        _validate_payout_selection(selection)
        return
    _validate_reopen_selection(selection)


def _validate_payout_selection(selection) -> None:
    _validate_identity_tuple(selection.bank_fact_identities, "outgoing bank facts", required=True)
    if selection.reopen_fact_identity is not None:
        raise ValueError("invalid_staff_payout_intent")


def _validate_reopen_selection(selection) -> None:
    _validate_identity_tuple(selection.bank_fact_identities, "outgoing bank facts", required=False)
    if selection.bank_fact_identities:
        raise ValueError("invalid_staff_payout_intent")
    if selection.reopen_fact_identity is None:
        raise ValueError("staff_payout_reversal_invalid")
    require_canonical_text(selection.reopen_fact_identity, "payout reopen fact", _IDENTITY_MAXIMUM_LENGTH)


def _validate_identity_tuple(values, field_name, *, required) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    if required and not values:
        raise ValueError(f"{field_name} must be nonempty")
    for value in values:
        require_canonical_text(value, field_name, _IDENTITY_MAXIMUM_LENGTH)
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{field_name} must be sorted and unique")


def _require_tuple(value, field_name) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple")


__all__ = [
    "StaffPayoutApplyRequest", "StaffPayoutReceipt", "StaffPayoutReconciliationError",
    "StaffPayoutReconciliationFacts", "StaffPayoutReconciliationPreview",
    "StaffPayoutReconciliationRepository", "StaffPayoutReconciliationWorkflow",
    "StaffPayoutRepositoryUnavailable", "StaffPayoutSelection", "StoredStaffPayoutReceipt",
]
