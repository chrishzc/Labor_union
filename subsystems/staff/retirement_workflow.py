"""
File: retirement_workflow.py
Description: 協調 Staff lifecycle 的 Query、Preview、Apply 與 strict receipt 冪等交易。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol

from domains.staff.retirement import StaffLifecycleCandidate, StaffLifecycleFact, StaffLifecycleState, StaffLifecycleTransition, build_transition
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.clock import BusinessClock
from shared_kernel.ports import UnitOfWork


@dataclass(frozen=True, slots=True)
class StaffLifecyclePreview:
    candidate: StaffLifecycleCandidate
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StaffLifecycleApplyRequest:
    staff_id: int
    transition: StaffLifecycleTransition
    effective_at: datetime
    reason_code: str
    expected_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class StaffLifecycleReceipt:
    staff_id: int
    state: StaffLifecycleState
    version: int
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey | None = None


class StaffLifecycleRepository(Protocol):
    def load(self, staff_id: int, *, lock: bool) -> StaffLifecycleFact: ...
    def ensure_no_open_assignments(self, staff_id: int, *, lock: bool) -> None: ...
    def claim_command(self, request: StaffLifecycleApplyRequest, command_fingerprint: PreviewFingerprint) -> None: ...
    def load_receipt(self, key: IdempotencyKey) -> tuple[PreviewFingerprint, StaffLifecycleReceipt] | None: ...
    def persist(self, request: StaffLifecycleApplyRequest, preview: StaffLifecyclePreview, receipt: StaffLifecycleReceipt, command_fingerprint: PreviewFingerprint) -> None: ...


class StaffLifecycleEffectPort(Protocol):
    def on_transition(
        self,
        unit_of_work: UnitOfWork,
        request: StaffLifecycleApplyRequest,
        preview: StaffLifecyclePreview,
        receipt: StaffLifecycleReceipt,
    ) -> None: ...


class StaffLifecycleWorkflow:
    def __init__(self, repository: StaffLifecycleRepository, unit_of_work_factory: Callable[[], UnitOfWork], clock: BusinessClock, effect: StaffLifecycleEffectPort | None = None) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._effect = effect

    def query(self, staff_id: int) -> StaffLifecycleFact:
        return self._repository.load(staff_id, lock=False)

    def preview(self, staff_id: int, transition: StaffLifecycleTransition, effective_at: datetime, reason_code: str) -> StaffLifecyclePreview:
        fact = self._repository.load(staff_id, lock=False)
        self._guard_open_assignments(staff_id, fact, transition, lock=False)
        return self._build_preview(fact, transition, effective_at, reason_code)

    def apply(self, request: StaffLifecycleApplyRequest) -> StaffLifecycleReceipt:
        command_fingerprint = fingerprint_payload(
            {
                "staff_id": request.staff_id,
                "transition": request.transition.value,
                "effective_at": request.effective_at.isoformat(),
                "reason_code": request.reason_code,
                "expected_version": request.expected_version.value,
                "preview_fingerprint": request.preview_fingerprint.value,
                "actor": request.actor.actor_id,
            }
        )
        with self._unit_of_work_factory() as unit_of_work:
            self._repository.claim_command(request, command_fingerprint)
            replay = self._repository.load_receipt(request.idempotency_key)
            if replay is not None:
                stored_fingerprint, receipt = replay
                if stored_fingerprint != command_fingerprint:
                    raise ValueError("idempotency_mismatch")
                unit_of_work.commit()
                return _receipt_with_idempotency_key(receipt, request.idempotency_key)
            fact = self._repository.load(request.staff_id, lock=True)
            self._guard_open_assignments(
                request.staff_id,
                fact,
                request.transition,
                lock=True,
            )
            replay = self._repository.load_receipt(request.idempotency_key)
            if replay is not None:
                stored_fingerprint, receipt = replay
                if stored_fingerprint != command_fingerprint:
                    raise ValueError("idempotency_mismatch")
                unit_of_work.commit()
                return _receipt_with_idempotency_key(receipt, request.idempotency_key)
            if fact.version != request.expected_version.value:
                raise ValueError("stale_version")
            preview = self._build_preview(fact, request.transition, request.effective_at, request.reason_code)
            if preview.fingerprint != request.preview_fingerprint:
                raise ValueError("stale_preview")
            receipt = StaffLifecycleReceipt(
                fact.staff_id,
                preview.candidate.after.state,
                preview.candidate.after.version,
                preview.fingerprint,
                request.idempotency_key,
            )
            self._repository.persist(request, preview, receipt, command_fingerprint)
            if self._effect is not None and not preview.candidate.is_noop:
                self._effect.on_transition(unit_of_work, request, preview, receipt)
            unit_of_work.commit()
            return receipt

    def _guard_open_assignments(
        self,
        staff_id: int,
        fact: StaffLifecycleFact,
        transition: StaffLifecycleTransition,
        *,
        lock: bool,
    ) -> None:
        """Retirement cannot orphan an existing Scheduling assignment.

        The optional lookup keeps existing in-memory owner adapters compatible;
        the MySQL owner implements it against the existing assignment status
        column. Apply repeats the check after the lifecycle row lock so a
        concurrent assignment cannot slip through the retirement boundary.
        """
        if transition is not StaffLifecycleTransition.RETIRE:
            return
        if fact.state is not StaffLifecycleState.ACTIVE:
            return
        guard = getattr(self._repository, "ensure_no_open_assignments", None)
        if guard is not None:
            guard(staff_id, lock=lock)

    def _build_preview(self, fact: StaffLifecycleFact, transition: StaffLifecycleTransition, effective_at: datetime, reason_code: str) -> StaffLifecyclePreview:
        if effective_at.tzinfo is None or effective_at.utcoffset() is None:
            raise ValueError("staff_retirement_effective_at_invalid")
        if effective_at > self._clock.now():
            raise ValueError("staff_retirement_future_effective_at_unsupported")
        candidate = build_transition(fact, transition, effective_at=effective_at, reason_code=reason_code)
        return StaffLifecyclePreview(candidate, fingerprint_payload({"staff_id": fact.staff_id, "before": fact.state.value, "after": candidate.after.state.value, "version": candidate.after.version, "effective_at": effective_at.isoformat(), "reason_code": reason_code}))


def _receipt_with_idempotency_key(
    receipt: StaffLifecycleReceipt,
    key: IdempotencyKey,
) -> StaffLifecycleReceipt:
    if receipt.idempotency_key == key:
        return receipt
    return StaffLifecycleReceipt(
        receipt.staff_id,
        receipt.state,
        receipt.version,
        receipt.preview_fingerprint,
        key,
    )
