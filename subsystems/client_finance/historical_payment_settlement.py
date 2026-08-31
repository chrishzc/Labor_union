"""Client Finance Query/Preview/Apply for historical payment evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from domains.client_finance.historical_payment import (
    HistoricalClientPaymentCandidate,
    HistoricalClientPaymentFacts,
    HistoricalClientPaymentIntent,
    HistoricalClientPaymentProjection,
    build_historical_client_payment_candidate,
    historical_client_owner_is_terminal,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.validation import require_canonical_text


@dataclass(frozen=True, slots=True)
class HistoricalClientPaymentPreview:
    candidate: HistoricalClientPaymentCandidate


@dataclass(frozen=True, slots=True)
class HistoricalClientPaymentReadback:
    facts: HistoricalClientPaymentFacts
    projections: tuple[HistoricalClientPaymentProjection, ...]
    owner_terminal: bool


@dataclass(frozen=True, slots=True)
class ApplyHistoricalClientPayment:
    intent: HistoricalClientPaymentIntent
    expected_account_version: ExpectedVersion
    expected_adoption_receipt_id: int
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.reason, "reason", 500)
        if self.expected_adoption_receipt_id <= 0:
            raise ValueError("historical_client_adoption_receipt_invalid")


@dataclass(frozen=True, slots=True)
class HistoricalClientPaymentReceipt:
    event_identity: str
    case_no: str
    obligation_identities: tuple[str, ...]
    amount_snapshot_ntd: int
    resulting_account_version: int
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StoredHistoricalClientPaymentReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: HistoricalClientPaymentReceipt


class HistoricalClientPaymentError(Exception):
    def __init__(self, error: TypedError) -> None:
        self.error = error
        super().__init__(error.code)


class HistoricalClientPaymentRepository(Protocol):
    def load(self, case_no: str, *, for_update: bool) -> HistoricalClientPaymentFacts: ...
    def load_projections(self, case_no: str) -> tuple[HistoricalClientPaymentProjection, ...]: ...
    def find_receipt(self, key: IdempotencyKey) -> StoredHistoricalClientPaymentReceipt | None: ...
    def append_event(self, request: ApplyHistoricalClientPayment, candidate: HistoricalClientPaymentCandidate, event_identity: str) -> int: ...
    def append_obligation_links(self, event_id: int, candidate: HistoricalClientPaymentCandidate) -> None: ...
    def upsert_projections(self, event_id: int, candidate: HistoricalClientPaymentCandidate, resulting_version: int) -> None: ...
    def append_source_outbox(self, event_id: int, candidate: HistoricalClientPaymentCandidate, event_identity: str) -> None: ...
    def save_receipt(self, key: IdempotencyKey, stored: StoredHistoricalClientPaymentReceipt) -> None: ...


class HistoricalClientPaymentWorkflow:
    def __init__(
        self,
        repository: HistoricalClientPaymentRepository,
        unit_of_work_factory: Callable[[], object],
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query(self, case_no: str) -> HistoricalClientPaymentFacts:
        require_canonical_text(case_no, "case number", 50)
        return self._repository.load(case_no, for_update=False)

    def preview(self, intent: HistoricalClientPaymentIntent) -> HistoricalClientPaymentPreview:
        facts = self._repository.load(intent.case_no, for_update=False)
        return HistoricalClientPaymentPreview(
            build_historical_client_payment_candidate(facts, intent)
        )

    def readback(self, case_no: str) -> HistoricalClientPaymentReadback:
        facts = self.query(case_no)
        projections = self._repository.load_projections(case_no)
        return HistoricalClientPaymentReadback(
            facts,
            projections,
            historical_client_owner_is_terminal(facts.obligations, projections),
        )

    def apply(self, request: ApplyHistoricalClientPayment) -> HistoricalClientPaymentReceipt:
        command_fingerprint = _command_fingerprint(request)
        with self._unit_of_work_factory() as unit:
            replay = self._repository.find_receipt(request.idempotency_key)
            if replay is not None:
                if replay.command_fingerprint != command_fingerprint:
                    raise _error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "historical_client_payment_idempotency_conflict")
                return replay.receipt

            facts = self._repository.load(request.intent.case_no, for_update=True)
            candidate = build_historical_client_payment_candidate(facts, request.intent)
            if (
                facts.account_version != request.expected_account_version.value
                or facts.adoption_receipt_id != request.expected_adoption_receipt_id
                or candidate.fingerprint != request.preview_fingerprint
            ):
                raise _error(
                    request,
                    ErrorCategory.CONFLICT,
                    "historical_client_payment_candidate_stale",
                    facts.account_version,
                )
            if not candidate.can_apply:
                raise _error(request, ErrorCategory.DOMAIN_BLOCKED, candidate.blockers[0])

            resulting_version = facts.account_version + 1
            event_identity = _event_identity(request.idempotency_key)
            receipt = HistoricalClientPaymentReceipt(
                event_identity,
                request.intent.case_no,
                request.intent.obligation_identities,
                candidate.amount_snapshot_ntd,
                resulting_version,
                candidate.fingerprint,
            )
            event_id = self._repository.append_event(request, candidate, event_identity)
            self._repository.append_obligation_links(event_id, candidate)
            self._repository.upsert_projections(event_id, candidate, resulting_version)
            self._repository.append_source_outbox(event_id, candidate, event_identity)
            self._repository.save_receipt(
                request.idempotency_key,
                StoredHistoricalClientPaymentReceipt(command_fingerprint, receipt),
            )
            unit.commit()
            return receipt


def _command_fingerprint(request: ApplyHistoricalClientPayment) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "preview_fingerprint": request.preview_fingerprint.value,
            "expected_account_version": request.expected_account_version.value,
            "expected_adoption_receipt_id": request.expected_adoption_receipt_id,
            "idempotency_key": request.idempotency_key.value,
            "actor_id": request.actor.actor_id,
            "reason": request.reason,
        }
    )


def _event_identity(key: IdempotencyKey) -> str:
    digest = fingerprint_payload({"historical_client_payment": key.value}).value
    return f"historical-client-payment:{digest}"


def _error(
    request: ApplyHistoricalClientPayment,
    category: ErrorCategory,
    code: str,
    current_version: int | None = None,
) -> HistoricalClientPaymentError:
    return HistoricalClientPaymentError(
        TypedError(
            category,
            code,
            "Historical Client Finance payment could not be applied.",
            request.correlation_id,
            domain_blockers=(code,) if category is ErrorCategory.DOMAIN_BLOCKED else (),
            current_version=(
                None if current_version is None else ExpectedVersion(current_version)
            ),
        )
    )


__all__ = [name for name in globals() if name.startswith("Historical") or name.startswith("Apply") or name.startswith("Stored")]
