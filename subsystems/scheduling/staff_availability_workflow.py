"""
File: staff_availability_workflow.py
Description: 編排 Staff Availability 的 canonical mutex、Preview、Apply 與唯一 outer UoW。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Protocol

from domains.scheduling.staff_availability import (
    StaffAvailabilityAction,
    StaffAvailabilityCandidate,
    StaffAvailabilityDomainError,
    StaffAvailabilityErrorCode,
    StaffAvailabilityFacts,
    StaffAvailabilityIntent,
    StaffAvailabilityPreview,
    StaffUnavailabilityBlock,
    build_staff_availability_preview,
    error_code_for_blockers,
)
from shared_kernel.clock import BusinessClock
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_positive_integer

_MAXIMUM_QUERY_DAY_COUNT = 366


class StaffAvailabilityReceiptRaceError(RuntimeError):
    """另一個交易已先取得相同全域 Idempotency-Key。"""


@dataclass(frozen=True, slots=True)
class StaffAvailabilityQuery:
    staff_id: int
    range_start: date
    range_end: date

    def __post_init__(self) -> None:
        require_positive_integer(self.staff_id, "staff availability query staff id")
        _validate_query_range(self.range_start, self.range_end)


@dataclass(frozen=True, slots=True)
class StaffAvailabilityPreviewRequest:
    intent: StaffAvailabilityIntent


@dataclass(frozen=True, slots=True)
class StaffAvailabilityApplyRequest:
    intent: StaffAvailabilityIntent
    expected_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class StaffAvailabilityApplyReceipt:
    staff_id: int
    action: StaffAvailabilityAction
    block: StaffUnavailabilityBlock
    aggregate_version: int
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey


@dataclass(frozen=True, slots=True)
class StoredStaffAvailabilityReceipt:
    request_fingerprint: PreviewFingerprint
    receipt: StaffAvailabilityApplyReceipt


class StaffAvailabilityRepository(Protocol):
    def list_blocks(self, query: StaffAvailabilityQuery) -> tuple[StaffUnavailabilityBlock, ...]: ...

    def load_facts(
        self,
        intent: StaffAvailabilityIntent,
        *,
        for_update: bool,
    ) -> StaffAvailabilityFacts: ...

    def load_receipt(
        self,
        key: IdempotencyKey,
    ) -> StoredStaffAvailabilityReceipt | None: ...

    def create_block(
        self,
        intent: StaffAvailabilityIntent,
        candidate: StaffAvailabilityCandidate,
        actor: ActorContext,
        occurred_at: datetime,
    ) -> StaffUnavailabilityBlock: ...

    def end_pause(
        self,
        target: StaffUnavailabilityBlock,
        candidate: StaffAvailabilityCandidate,
        actor: ActorContext,
        occurred_at: datetime,
    ) -> StaffUnavailabilityBlock: ...

    def cancel_block(
        self,
        target: StaffUnavailabilityBlock,
        actor: ActorContext,
        occurred_at: datetime,
    ) -> StaffUnavailabilityBlock: ...

    def increment_version(self, staff_id: int, expected_version: int) -> int: ...

    def append_event(
        self,
        request: StaffAvailabilityApplyRequest,
        before: StaffUnavailabilityBlock | None,
        after: StaffUnavailabilityBlock,
        aggregate_version: int,
        occurred_at: datetime,
    ) -> None: ...

    def save_receipt(
        self,
        request: StaffAvailabilityApplyRequest,
        request_fingerprint: PreviewFingerprint,
        receipt: StaffAvailabilityApplyReceipt,
        occurred_at: datetime,
    ) -> None: ...

    def lock_staff_occupancy_mutex(self, staff_id: int) -> None: ...


class StaffAvailabilityWorkflow:
    def __init__(
        self,
        repository: StaffAvailabilityRepository,
        clock: BusinessClock,
        unit_of_work_factory: Callable[[], UnitOfWork],
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._unit_of_work_factory = unit_of_work_factory

    def query(self, request: StaffAvailabilityQuery) -> tuple[StaffUnavailabilityBlock, ...]:
        return self._repository.list_blocks(request)

    def preview(self, request: StaffAvailabilityPreviewRequest) -> StaffAvailabilityPreview:
        facts = self._repository.load_facts(request.intent, for_update=False)
        return build_staff_availability_preview(request.intent, facts)

    def apply(self, request: StaffAvailabilityApplyRequest) -> StaffAvailabilityApplyReceipt:
        request_fingerprint = _request_fingerprint(request)
        try:
            with self._unit_of_work_factory() as unit_of_work:
                _lock_staff_occupancy_mutex(self._repository, request.intent.staff_id)
                replay = self._repository.load_receipt(request.idempotency_key)
                if replay is not None:
                    receipt = _replayed_receipt(replay, request_fingerprint)
                    unit_of_work.commit()
                    return receipt
                receipt = self._apply_fresh(request, request_fingerprint, unit_of_work)
                unit_of_work.commit()
                return receipt
        except StaffAvailabilityReceiptRaceError:
            return self._resolve_receipt_race(request, request_fingerprint)

    def _resolve_receipt_race(self, request, request_fingerprint):
        """原交易已回滾後，以新交易讀取勝出交易的 immutable receipt。"""
        with self._unit_of_work_factory() as unit_of_work:
            _lock_staff_occupancy_mutex(self._repository, request.intent.staff_id)
            replay = self._repository.load_receipt(request.idempotency_key)
            if replay is None:
                raise StaffAvailabilityDomainError(
                    StaffAvailabilityErrorCode.IDEMPOTENCY_CONFLICT
                )
            receipt = _replayed_receipt(replay, request_fingerprint)
            unit_of_work.commit()
            return receipt

    def _apply_fresh(self, request, request_fingerprint, unit_of_work):
        facts = self._repository.load_facts(request.intent, for_update=True)
        concurrent_replay = self._repository.load_receipt(request.idempotency_key)
        if concurrent_replay is not None:
            receipt = _replayed_receipt(concurrent_replay, request_fingerprint)
            unit_of_work.commit()
            return receipt
        _require_version(facts.aggregate_version, request.expected_version)
        preview = build_staff_availability_preview(request.intent, facts)
        _require_preview(preview, request.preview_fingerprint)
        occurred_at = self._clock.now()
        block = _mutate_block(self._repository, request, preview, occurred_at)
        version = self._repository.increment_version(request.intent.staff_id, facts.aggregate_version)
        receipt = _receipt(request, block, version)
        self._repository.append_event(request, preview.target_block, block, version, occurred_at)
        self._repository.save_receipt(request, request_fingerprint, receipt, occurred_at)
        return receipt


def _mutate_block(repository, request, preview, occurred_at):
    if preview.blockers:
        raise StaffAvailabilityDomainError(
            error_code_for_blockers(preview.blockers),
            preview.blockers,
        )
    if request.intent.action in {
        StaffAvailabilityAction.CREATE_LONG_LEAVE,
        StaffAvailabilityAction.CREATE_PAUSE,
    }:
        return repository.create_block(request.intent, preview.candidate, request.actor, occurred_at)
    if request.intent.action is StaffAvailabilityAction.END_PAUSE:
        return repository.end_pause(preview.target_block, preview.candidate, request.actor, occurred_at)
    return repository.cancel_block(preview.target_block, request.actor, occurred_at)


def _request_fingerprint(request):
    intent = request.intent
    return fingerprint_payload(
        {
            "contract_version": "staff-availability-apply-v1",
            "action": intent.action.value,
            "staff_id": intent.staff_id,
            "reason": intent.reason,
            "start_date": _date_text(intent.start_date),
            "end_date": _date_text(intent.end_date),
            "block_id": intent.block_id,
            "resume_date": _date_text(intent.resume_date),
            "expected_version": request.expected_version.value,
            "preview_fingerprint": request.preview_fingerprint.value,
            "actor": request.actor.actor_id,
        }
    )


def _replayed_receipt(stored, request_fingerprint):
    if stored.request_fingerprint != request_fingerprint:
        raise StaffAvailabilityDomainError(StaffAvailabilityErrorCode.IDEMPOTENCY_CONFLICT)
    return stored.receipt


def _require_version(current, expected):
    if current != expected.value:
        raise StaffAvailabilityDomainError(
            StaffAvailabilityErrorCode.STALE,
            (f"current_version:{current}",),
        )


def _require_preview(preview, expected):
    if preview.preview_fingerprint != expected:
        raise StaffAvailabilityDomainError(
            StaffAvailabilityErrorCode.STALE,
            ("preview_fingerprint_changed",),
        )


def _receipt(request, block, version):
    return StaffAvailabilityApplyReceipt(
        request.intent.staff_id,
        request.intent.action,
        block,
        version,
        request.preview_fingerprint,
        request.idempotency_key,
    )


def _validate_query_range(range_start, range_end):
    if type(range_start) is not date or type(range_end) is not date:
        raise TypeError("staff availability query boundaries must be dates")
    if range_end < range_start:
        raise ValueError("staff availability query range is inverted")
    if (range_end - range_start).days + 1 > _MAXIMUM_QUERY_DAY_COUNT:
        raise ValueError("staff availability query exceeds 366 days")


def _date_text(value):
    return value.isoformat() if value is not None else None


def _lock_staff_occupancy_mutex(repository, staff_id: int) -> None:
    """Acquire the shared occupancy mutex before any receipt or fact read."""
    repository.lock_staff_occupancy_mutex(staff_id)


__all__ = [
    "StaffAvailabilityApplyReceipt",
    "StaffAvailabilityApplyRequest",
    "StaffAvailabilityPreviewRequest",
    "StaffAvailabilityQuery",
    "StaffAvailabilityRepository",
    "StaffAvailabilityWorkflow",
    "StoredStaffAvailabilityReceipt",
]
