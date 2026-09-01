"""Preview and apply the historical accounting-completed lifecycle transition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Callable, Protocol

from domains.orders.lifecycle import (
    LifecycleImpactCandidate,
    OrderLifecycleStatus,
    project_historical_accounting_completion_status,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer
from subsystems.orders.historical_completion_oracle import (
    HistoricalCompletionOracleResult,
    HistoricalCompletionState,
    HistoricalSettlementSourceVersion,
)


class HistoricalCompletionClaimState(StrEnum):
    CREATED = "created"
    MATCHED = "matched"
    MISMATCH = "mismatch"


@dataclass(frozen=True, slots=True)
class HistoricalCompletionApplyFacts:
    oracle: HistoricalCompletionOracleResult
    actual_end_date: date | None

    def __post_init__(self) -> None:
        if not isinstance(self.oracle, HistoricalCompletionOracleResult):
            raise TypeError("historical completion oracle result is invalid")
        if self.actual_end_date is not None and type(self.actual_end_date) is not date:
            raise TypeError("historical actual end date is invalid")


@dataclass(frozen=True, slots=True)
class HistoricalCompletionCandidate:
    case_no: str
    before_status: OrderLifecycleStatus
    after_status: OrderLifecycleStatus
    expected_order_version: int
    resulting_order_version: int
    expected_client_finance_version: int
    expected_source_versions: tuple[HistoricalSettlementSourceVersion, ...]
    actual_end_date: date | None
    business_date: date
    source_fingerprint: PreviewFingerprint
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ApplyHistoricalCompletion:
    case_no: str
    expected_order_version: int
    expected_client_finance_version: int
    expected_source_versions: tuple[HistoricalSettlementSourceVersion, ...]
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        require_nonnegative_integer(self.expected_order_version, "expected order version")
        require_nonnegative_integer(
            self.expected_client_finance_version, "expected client finance version"
        )
        require_canonical_text(self.reason, "historical completion reason", 500)
        if not isinstance(self.expected_source_versions, tuple):
            raise TypeError("expected source versions must be a tuple")
        if any(
            not isinstance(item, HistoricalSettlementSourceVersion)
            for item in self.expected_source_versions
        ):
            raise TypeError("expected source version is invalid")
        if self.expected_source_versions != tuple(sorted(set(self.expected_source_versions))):
            raise ValueError("expected source versions must be sorted and unique")


@dataclass(frozen=True, slots=True)
class HistoricalCompletionReceipt:
    case_no: str
    lifecycle_event_id: int
    resulting_order_version: int
    after_status: OrderLifecycleStatus
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class StoredHistoricalCompletionReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: HistoricalCompletionReceipt


class HistoricalCompletionApplyError(Exception):
    def __init__(self, error: TypedError) -> None:
        self.error = error
        super().__init__(error.code)


class HistoricalCompletionApplyRepository(Protocol):
    def load(self, case_no: str, *, for_update: bool) -> HistoricalCompletionApplyFacts: ...

    def claim(
        self, request: ApplyHistoricalCompletion, command_fingerprint: PreviewFingerprint
    ) -> HistoricalCompletionClaimState: ...

    def find_receipt(
        self, key: IdempotencyKey
    ) -> StoredHistoricalCompletionReceipt | None: ...

    def persist(
        self,
        request: ApplyHistoricalCompletion,
        candidate: HistoricalCompletionCandidate,
    ) -> HistoricalCompletionReceipt: ...


class HistoricalCompletionApplyWorkflow:
    def __init__(
        self,
        repository: HistoricalCompletionApplyRepository,
        unit_of_work_factory: Callable[[], object],
        clock: object,
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock

    def preview(self, case_no: str) -> HistoricalCompletionCandidate:
        require_canonical_text(case_no, "case number", 50)
        return _candidate(self._repository.load(case_no, for_update=False), self._clock.today())

    def apply(self, request: ApplyHistoricalCompletion) -> HistoricalCompletionReceipt:
        command_fingerprint = _command_fingerprint(request)
        with self._unit_of_work_factory() as unit:
            claim = self._repository.claim(request, command_fingerprint)
            if claim is HistoricalCompletionClaimState.MISMATCH:
                raise _error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_conflict")
            stored = self._repository.find_receipt(request.idempotency_key)
            if stored is not None:
                if stored.command_fingerprint != command_fingerprint:
                    raise _error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_conflict")
                return _replayed(stored.receipt)
            if claim is HistoricalCompletionClaimState.MATCHED:
                raise _error(
                    request,
                    ErrorCategory.INTERNAL,
                    "idempotency_evidence_incomplete",
                )

            facts = self._repository.load(request.case_no, for_update=True)
            candidate = _candidate(facts, self._clock.today(), request)
            if (
                candidate.expected_order_version != request.expected_order_version
                or candidate.expected_client_finance_version
                != request.expected_client_finance_version
                or candidate.expected_source_versions != request.expected_source_versions
                or candidate.fingerprint != request.preview_fingerprint
            ):
                raise _error(
                    request,
                    ErrorCategory.CONFLICT,
                    "historical_accounting_completion_candidate_stale",
                    candidate.expected_order_version,
                )
            receipt = self._repository.persist(request, candidate)
            unit.commit()
            return receipt


def _candidate(
    facts: HistoricalCompletionApplyFacts,
    business_date: date,
    request: ApplyHistoricalCompletion | None = None,
) -> HistoricalCompletionCandidate:
    result = facts.oracle
    if result.orders_readback.canonical_status is not OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED:
        raise _error_or_value(request, "historical_order_lifecycle_transition_invalid")
    if result.state is not HistoricalCompletionState.COMPLETED:
        blockers = tuple(item.code for item in result.missing_roots)
        raise _error_or_value(
            request,
            "historical_accounting_completion_blocked",
            blockers,
        )
    client_version = next(
        (version for owner, version in result.owner_versions if owner == "client_finance"),
        None,
    )
    if client_version is None:
        raise _error_or_value(
            request,
            "historical_accounting_completion_blocked",
            ("historical_client_settlement_incomplete",),
        )
    after_status = project_historical_accounting_completion_status(
        result.orders_readback.canonical_status,
        client_settled=True,
        all_staff_settled=True,
        service_day_counts_complete=True,
    )
    expected_order_version = result.orders_readback.lifecycle_version
    payload = {
        "case_no": result.case_no,
        "before_status": result.orders_readback.canonical_status.value,
        "after_status": after_status.value,
        "expected_order_version": expected_order_version,
        "resulting_order_version": expected_order_version + 1,
        "expected_client_finance_version": client_version,
        "expected_source_versions": tuple(
            {"kind": item.kind.value, "identity": item.identity, "version": item.version}
            for item in result.owner_source_versions
        ),
        "actual_end_date": facts.actual_end_date.isoformat() if facts.actual_end_date else None,
        "business_date": business_date.isoformat(),
        "source_fingerprint": result.fingerprint.value,
    }
    return HistoricalCompletionCandidate(
        result.case_no,
        result.orders_readback.canonical_status,
        after_status,
        expected_order_version,
        expected_order_version + 1,
        client_version,
        result.owner_source_versions,
        facts.actual_end_date,
        business_date,
        result.fingerprint,
        fingerprint_payload(payload),
    )


def _command_fingerprint(request: ApplyHistoricalCompletion) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "case_no": request.case_no,
            "expected_order_version": request.expected_order_version,
            "expected_client_finance_version": request.expected_client_finance_version,
            "expected_source_versions": tuple(
                {"kind": item.kind.value, "identity": item.identity, "version": item.version}
                for item in request.expected_source_versions
            ),
            "preview_fingerprint": request.preview_fingerprint.value,
            "actor": request.actor.actor_id,
            "reason": request.reason,
        }
    )


def _replayed(receipt: HistoricalCompletionReceipt) -> HistoricalCompletionReceipt:
    return HistoricalCompletionReceipt(
        receipt.case_no,
        receipt.lifecycle_event_id,
        receipt.resulting_order_version,
        receipt.after_status,
        True,
    )


def _error_or_value(
    request: ApplyHistoricalCompletion | None,
    code: str,
    blockers: tuple[str, ...] = (),
):
    if request is None:
        raise ValueError(code)
    category = (
        ErrorCategory.CONFLICT
        if code == "historical_order_lifecycle_transition_invalid"
        else ErrorCategory.DOMAIN_BLOCKED
    )
    raise _error(request, category, code, blockers=blockers)


def _error(
    request: ApplyHistoricalCompletion,
    category: ErrorCategory,
    code: str,
    current_version: int | None = None,
    blockers: tuple[str, ...] = (),
) -> HistoricalCompletionApplyError:
    from shared_kernel.identities import ExpectedVersion

    return HistoricalCompletionApplyError(
        TypedError(
            category,
            code,
            "歷史訂單帳務完成狀態未通過驗證。",
            request.correlation_id,
            current_version=(
                None if current_version is None else ExpectedVersion(current_version)
            ),
            domain_blockers=tuple(sorted(set(blockers or (code,)))),
        )
    )


def lifecycle_impact_candidate(
    candidate: HistoricalCompletionCandidate,
) -> LifecycleImpactCandidate:
    """Adapt the bounded completion decision to the canonical Orders writer."""

    return LifecycleImpactCandidate(
        candidate.case_no,
        candidate.before_status,
        candidate.after_status,
        candidate.actual_end_date,
        None,
        candidate.business_date,
        True,
        True,
        True,
        (),
        candidate.fingerprint,
    )


__all__ = [name for name in globals() if name.startswith("Historical") or name.startswith("Apply")]
