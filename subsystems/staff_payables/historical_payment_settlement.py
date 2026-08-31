"""Staff Payables Query/Preview/Apply for historical payout evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from domains.staff_payables.historical_payout import (
    HistoricalStaffPayoutCandidate,
    HistoricalStaffPayoutFacts,
    HistoricalStaffPayoutIntent,
    HistoricalStaffPayoutProjection,
    build_historical_staff_payout_candidate,
    historical_staff_owner_is_terminal,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.validation import require_canonical_text


@dataclass(frozen=True, slots=True)
class HistoricalStaffPayoutPreview:
    candidate: HistoricalStaffPayoutCandidate


@dataclass(frozen=True, slots=True)
class HistoricalStaffPayoutReadback:
    facts: HistoricalStaffPayoutFacts
    projections: tuple[HistoricalStaffPayoutProjection, ...]
    owner_terminal: bool


@dataclass(frozen=True, slots=True)
class ApplyHistoricalStaffPayout:
    intent: HistoricalStaffPayoutIntent
    expected_staff_payables_version: ExpectedVersion
    expected_adoption_receipt_id: int
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.reason, "reason", 500)
        if self.expected_adoption_receipt_id <= 0:
            raise ValueError("historical_staff_adoption_receipt_invalid")


@dataclass(frozen=True, slots=True)
class HistoricalStaffPayoutReceipt:
    event_identity: str
    case_no: str
    staff_id: int
    obligation_identities: tuple[str, ...]
    amount_snapshot_ntd: int
    resulting_staff_payables_version: int
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StoredHistoricalStaffPayoutReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: HistoricalStaffPayoutReceipt


class HistoricalStaffPayoutError(Exception):
    def __init__(self, error: TypedError) -> None:
        self.error = error
        super().__init__(error.code)


class HistoricalStaffPayoutRepository(Protocol):
    def load(self, case_no: str, staff_id: int, *, for_update: bool) -> HistoricalStaffPayoutFacts: ...
    def load_projections(self, case_no: str, staff_id: int) -> tuple[HistoricalStaffPayoutProjection, ...]: ...
    def find_receipt(self, key: IdempotencyKey) -> StoredHistoricalStaffPayoutReceipt | None: ...
    def append_event(self, request: ApplyHistoricalStaffPayout, candidate: HistoricalStaffPayoutCandidate, event_identity: str) -> int: ...
    def append_obligation_links(self, event_id: int, candidate: HistoricalStaffPayoutCandidate) -> None: ...
    def upsert_projections(self, event_id: int, candidate: HistoricalStaffPayoutCandidate, resulting_version: int) -> None: ...
    def append_source_outbox(self, event_id: int, candidate: HistoricalStaffPayoutCandidate, event_identity: str) -> None: ...
    def save_receipt(self, key: IdempotencyKey, stored: StoredHistoricalStaffPayoutReceipt) -> None: ...


class HistoricalStaffPayoutWorkflow:
    def __init__(self, repository: HistoricalStaffPayoutRepository, unit_of_work_factory: Callable[[], object]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query(self, case_no: str, staff_id: int) -> HistoricalStaffPayoutFacts:
        require_canonical_text(case_no, "case number", 50)
        return self._repository.load(case_no, staff_id, for_update=False)

    def preview(self, intent: HistoricalStaffPayoutIntent) -> HistoricalStaffPayoutPreview:
        facts = self._repository.load(intent.case_no, intent.staff_id, for_update=False)
        return HistoricalStaffPayoutPreview(build_historical_staff_payout_candidate(facts, intent))

    def readback(self, case_no: str, staff_id: int) -> HistoricalStaffPayoutReadback:
        facts = self.query(case_no, staff_id)
        projections = self._repository.load_projections(case_no, staff_id)
        return HistoricalStaffPayoutReadback(
            facts,
            projections,
            historical_staff_owner_is_terminal(facts.obligations, projections),
        )

    def apply(self, request: ApplyHistoricalStaffPayout) -> HistoricalStaffPayoutReceipt:
        command_fingerprint = _command_fingerprint(request)
        with self._unit_of_work_factory() as unit:
            replay = self._repository.find_receipt(request.idempotency_key)
            if replay is not None:
                if replay.command_fingerprint != command_fingerprint:
                    raise _error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "historical_staff_payout_idempotency_conflict")
                return replay.receipt

            facts = self._repository.load(request.intent.case_no, request.intent.staff_id, for_update=True)
            candidate = build_historical_staff_payout_candidate(facts, request.intent)
            if (
                facts.staff_payables_version != request.expected_staff_payables_version.value
                or facts.adoption_receipt_id != request.expected_adoption_receipt_id
                or candidate.fingerprint != request.preview_fingerprint
            ):
                raise _error(request, ErrorCategory.CONFLICT, "historical_staff_payout_candidate_stale", facts.staff_payables_version)
            if not candidate.can_apply:
                raise _error(request, ErrorCategory.DOMAIN_BLOCKED, candidate.blockers[0])

            resulting_version = facts.staff_payables_version + 1
            event_identity = _event_identity(request.idempotency_key)
            receipt = HistoricalStaffPayoutReceipt(
                event_identity,
                request.intent.case_no,
                request.intent.staff_id,
                request.intent.obligation_identities,
                candidate.amount_snapshot_ntd,
                resulting_version,
                candidate.fingerprint,
            )
            event_id = self._repository.append_event(request, candidate, event_identity)
            self._repository.append_obligation_links(event_id, candidate)
            self._repository.upsert_projections(event_id, candidate, resulting_version)
            self._repository.append_source_outbox(event_id, candidate, event_identity)
            self._repository.save_receipt(request.idempotency_key, StoredHistoricalStaffPayoutReceipt(command_fingerprint, receipt))
            unit.commit()
            return receipt


def _command_fingerprint(request: ApplyHistoricalStaffPayout) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "preview_fingerprint": request.preview_fingerprint.value,
            "expected_staff_payables_version": request.expected_staff_payables_version.value,
            "expected_adoption_receipt_id": request.expected_adoption_receipt_id,
            "idempotency_key": request.idempotency_key.value,
            "actor_id": request.actor.actor_id,
            "reason": request.reason,
        }
    )


def _event_identity(key: IdempotencyKey) -> str:
    digest = fingerprint_payload({"historical_staff_payout": key.value}).value
    return f"historical-staff-payout:{digest}"


def _error(request, category, code, current_version=None):
    return HistoricalStaffPayoutError(
        TypedError(
            category,
            code,
            "Historical Staff Payables payout could not be applied.",
            request.correlation_id,
            domain_blockers=(code,) if category is ErrorCategory.DOMAIN_BLOCKED else (),
            current_version=None if current_version is None else ExpectedVersion(current_version),
        )
    )


__all__ = [name for name in globals() if name.startswith("Historical") or name.startswith("Apply") or name.startswith("Stored")]
