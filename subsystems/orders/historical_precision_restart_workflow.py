"""Atomic Q/P/A orchestration for historical precision restart."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Callable, Protocol

from domains.orders.historical_precision_restart import (
    HistoricalPrecisionRestartCandidate as DomainCandidate,
    HistoricalPrecisionRestartFacts,
    HistoricalPrecisionRestartIntent,
    build_historical_precision_restart_candidate,
)
from domains.orders.lifecycle import LifecycleImpactCandidate
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey


@dataclass(frozen=True, slots=True)
class HistoricalPrecisionRestartContext:
    facts: HistoricalPrecisionRestartFacts
    terms_facts: Any


@dataclass(frozen=True, slots=True)
class HistoricalPrecisionRestartPreview:
    domain: DomainCandidate
    client_finance_impact: Any | None
    payroll_impact: Any | None
    lifecycle_impact: LifecycleImpactCandidate | None
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ApplyHistoricalPrecisionRestart:
    intent: HistoricalPrecisionRestartIntent
    expected_order_version: int
    expected_scheduling_version: int
    expected_historical_day_revision: int
    expected_confirmed_service_date_version: int | None
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class HistoricalPrecisionRestartReceipt:
    case_no: str
    lifecycle_status: str
    order_version: int
    scheduling_version: int
    scheduling_generation: int
    client_finance_version: int
    payroll_version: int
    historical_day_revision: int
    preview_fingerprint: PreviewFingerprint
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class StoredHistoricalPrecisionRestartReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: HistoricalPrecisionRestartReceipt


class HistoricalPrecisionRestartError(Exception):
    def __init__(self, error: TypedError) -> None:
        self.error = error
        super().__init__(error.code)


class HistoricalPrecisionRestartRepository(Protocol):
    def load(self, case_no: str, *, for_update: bool) -> HistoricalPrecisionRestartContext: ...
    def preflight_staff_ids(self, case_no: str) -> tuple[int, ...]: ...
    def find_receipt(self, key: IdempotencyKey) -> StoredHistoricalPrecisionRestartReceipt | None: ...
    def claim(self, request: ApplyHistoricalPrecisionRestart, command_fingerprint: PreviewFingerprint) -> StoredHistoricalPrecisionRestartReceipt | None: ...
    def persist(self, request: ApplyHistoricalPrecisionRestart, preview: HistoricalPrecisionRestartPreview) -> HistoricalPrecisionRestartReceipt: ...


class HistoricalPrecisionRestartWorkflow:
    def __init__(self, repository: HistoricalPrecisionRestartRepository, unit_of_work_factory: Callable[[], object], now: Callable[[], datetime]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory
        self._now = now

    def query(self, case_no: str) -> HistoricalPrecisionRestartPreview:
        context = self._repository.load(case_no, for_update=False)
        return _preview(context, HistoricalPrecisionRestartIntent(case_no), self._now())

    def preview(self, intent: HistoricalPrecisionRestartIntent) -> HistoricalPrecisionRestartPreview:
        return _preview(self._repository.load(intent.case_no, for_update=False), intent, self._now())

    def apply(self, request: ApplyHistoricalPrecisionRestart) -> HistoricalPrecisionRestartReceipt:
        command_fingerprint = _command_fingerprint(request)
        with self._unit_of_work_factory() as unit:
            stored = self._repository.find_receipt(request.idempotency_key)
            if stored is not None:
                if stored.command_fingerprint != command_fingerprint:
                    raise _error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_conflict")
                return replace(stored.receipt, replayed=True)
            try:
                claimed = self._repository.claim(request, command_fingerprint)
            except ValueError as error:
                if str(error) != "idempotency_conflict":
                    raise
                raise _error(request, ErrorCategory.IDEMPOTENCY_MISMATCH, "idempotency_conflict") from error
            if claimed is not None:
                return replace(claimed.receipt, replayed=True)
            self._repository.preflight_staff_ids(request.intent.case_no)
            context = self._repository.load(request.intent.case_no, for_update=True)
            preview = _preview(context, request.intent, self._now())
            facts = context.facts
            if (
                facts.order_version != request.expected_order_version
                or facts.scheduling_version != request.expected_scheduling_version
                or facts.historical_day_revision != request.expected_historical_day_revision
                or facts.confirmed_service_date_version != request.expected_confirmed_service_date_version
                or preview.fingerprint != request.preview_fingerprint
            ):
                raise _error(request, ErrorCategory.CONFLICT, "historical_precision_restart_candidate_stale", facts.order_version)
            receipt = self._repository.persist(request, preview)
            unit.commit()
            return receipt


def _preview(context, intent, evaluation_at):
    domain = build_historical_precision_restart_candidate(context.facts, intent)
    if domain.blockers:
        raise HistoricalPrecisionRestartError(
            TypedError(ErrorCategory.DOMAIN_BLOCKED, domain.blockers[0], "歷史訂單目前不能重啟正常流程。", CorrelationId("historical-precision-restart-preview"), domain_blockers=domain.blockers)
        )
    assert domain.scheduling is not None and domain.target_status is not None
    lifecycle = _lifecycle(domain, evaluation_at)
    fingerprint = fingerprint_payload({
        "domain": domain.fingerprint.value,
        "lifecycle": lifecycle.fingerprint.value,
        "normal_flow_requires_service_date_confirmation": True,
    })
    return HistoricalPrecisionRestartPreview(domain, None, None, lifecycle, fingerprint)


def _lifecycle(domain, evaluation_at):
    facts = domain.facts
    payload = {
        "case_no": facts.case_no,
        "before": facts.lifecycle_status.value,
        "after": domain.target_status.value,
        "actual_end": None,
        "business_date": evaluation_at.date().isoformat(),
        "normal_flow_requires_service_date_confirmation": True,
    }
    return LifecycleImpactCandidate(
        facts.case_no, facts.lifecycle_status, domain.target_status, None,
        None, evaluation_at.date(), False, facts.service_data_locked, False, (), fingerprint_payload(payload)
    )


def _command_fingerprint(request):
    return fingerprint_payload({
        "case_no": request.intent.case_no,
        "restart_mode": "return_to_normal_order_workflow",
        "versions": (
            request.expected_order_version,
            request.expected_scheduling_version,
            request.expected_historical_day_revision,
            request.expected_confirmed_service_date_version,
        ),
        "preview": request.preview_fingerprint.value,
        "actor": request.actor.actor_id,
        "reason": request.reason,
    })


def _error(request, category, code, current_version=None):
    return HistoricalPrecisionRestartError(TypedError(category, code, "歷史訂單重啟正常流程失敗。", request.correlation_id, current_version=None if current_version is None else ExpectedVersion(current_version)))


__all__ = [name for name in globals() if name.startswith("Historical") or name.startswith("Apply")]
