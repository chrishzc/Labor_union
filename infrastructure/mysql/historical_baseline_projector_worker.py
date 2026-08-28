"""Two-UoW worker orchestration for historical-baseline projector v2."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Callable, Protocol

from pymysql.err import InterfaceError, OperationalError

from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.anomalies.historical_baseline_projection import (
    FreshHistoricalBaselineOwnerVectorReadback,
    HistoricalBaselineProjectionResult,
    project_historical_baseline,
)

from infrastructure.mysql.historical_baseline_projector_checkpoint import (
    HistoricalBaselineSourceCheckpoint,
    validate_checkpoint_progress,
)
from infrastructure.mysql.historical_baseline_projector_delivery import (
    HistoricalBaselineDeliveryError,
    HistoricalBaselineDeliveryStatus,
    HistoricalBaselineProjectorDelivery,
    HistoricalBaselineProjectorTrigger,
)
from infrastructure.mysql.historical_baseline_projector_read_model import (
    HistoricalBaselineProjectorQueryError,
    HistoricalBaselineProjectorReadModel,
    HistoricalBaselineReconcileByIdentityResult,
    historical_baseline_reconcile_by_identity_disposition,
)


@dataclass(frozen=True, slots=True)
class HistoricalBaselineExactReadback:
    actual_readback_digest: PreviewFingerprint | None
    emitted_occurrence_set_digest: PreviewFingerprint | None
    emitted_occurrence_set_count: int | None
    active_membership_set_digest: PreviewFingerprint | None
    active_membership_set_count: int | None
    state_event_set_digest: PreviewFingerprint | None
    successor_set_digest: PreviewFingerprint | None
    workflow_event_set_digest: PreviewFingerprint | None
    current_alert_fingerprint: PreviewFingerprint | None
    error_code: str | None = None

    def matches(self, result: HistoricalBaselineProjectionResult) -> bool:
        receipt = result.receipt
        return (
            self.error_code is None
            and self.actual_readback_digest == receipt.expected_readback_digest
            and self.emitted_occurrence_set_digest
            == receipt.emitted_occurrence_set_digest
            and self.emitted_occurrence_set_count
            == receipt.emitted_occurrence_set_count
            and self.active_membership_set_digest
            == receipt.active_membership_set_digest
            and self.active_membership_set_count
            == receipt.active_membership_set_count
            and self.state_event_set_digest is not None
            and self.successor_set_digest is not None
            and self.workflow_event_set_digest is not None
            and self.current_alert_fingerprint is not None
        )


class HistoricalBaselineProjectorRepositoryPort(Protocol):
    def query_by_delivery_identity(
        self, delivery_identity: str
    ) -> HistoricalBaselineProjectorReadModel | None: ...

    def query_latest_by_case(
        self, case_no: str
    ) -> HistoricalBaselineProjectorReadModel | None: ...

    def register_delivery(
        self,
        trigger: HistoricalBaselineProjectorTrigger,
        *,
        max_attempts: int,
    ) -> HistoricalBaselineProjectorDelivery: ...

    def load_delivery(
        self, trigger: HistoricalBaselineProjectorTrigger, *, for_update: bool
    ) -> HistoricalBaselineProjectorDelivery: ...

    def save_delivery(
        self,
        previous: HistoricalBaselineProjectorDelivery,
        resulting: HistoricalBaselineProjectorDelivery,
    ) -> None: ...

    def lock_projection_case(self, trigger: HistoricalBaselineProjectorTrigger) -> None: ...

    def load_checkpoint(
        self, trigger: HistoricalBaselineProjectorTrigger, *, for_update: bool
    ) -> HistoricalBaselineSourceCheckpoint | None: ...

    def load_active_occurrences(
        self, trigger: HistoricalBaselineProjectorTrigger, *, for_update: bool
    ) -> tuple[object, ...]: ...

    def next_projection_sequence(
        self, trigger: HistoricalBaselineProjectorTrigger, *, for_update: bool
    ) -> int: ...

    def persist_projection(
        self,
        delivery: HistoricalBaselineProjectorDelivery,
        result: HistoricalBaselineProjectionResult,
        checkpoint: HistoricalBaselineSourceCheckpoint,
    ) -> None: ...

    def read_exact_projection(
        self,
        delivery: HistoricalBaselineProjectorDelivery,
        result: HistoricalBaselineProjectionResult,
    ) -> HistoricalBaselineExactReadback: ...

    def append_post_commit_readback(
        self,
        delivery: HistoricalBaselineProjectorDelivery,
        result: HistoricalBaselineProjectionResult,
        readback: HistoricalBaselineExactReadback,
        *,
        exact: bool,
    ) -> None: ...


class HistoricalBaselineProjectorUnitOfWork(Protocol):
    repository: HistoricalBaselineProjectorRepositoryPort

    def __enter__(self) -> HistoricalBaselineProjectorUnitOfWork: ...

    def __exit__(self, exception_type, exception, traceback) -> bool: ...

    def commit(self) -> None: ...


OwnerVectorReader = Callable[
    [HistoricalBaselineProjectorUnitOfWork, HistoricalBaselineProjectorTrigger],
    FreshHistoricalBaselineOwnerVectorReadback,
]


class HistoricalBaselineProjectorWorker:
    def __init__(
        self,
        *,
        unit_of_work_factory: Callable[[], HistoricalBaselineProjectorUnitOfWork],
        owner_vector_reader: OwnerVectorReader,
        max_attempts: int = 5,
        lease_duration: timedelta = timedelta(seconds=60),
        retry_base_delay: timedelta = timedelta(seconds=15),
        retry_delay_cap: timedelta = timedelta(seconds=300),
    ) -> None:
        if max_attempts < 1:
            raise ValueError("historical baseline projector max attempts must be positive")
        if lease_duration <= timedelta(0):
            raise ValueError("historical baseline projector lease duration must be positive")
        if retry_base_delay <= timedelta(0) or retry_delay_cap < retry_base_delay:
            raise ValueError("historical baseline projector retry delay is invalid")
        self._unit_of_work_factory = unit_of_work_factory
        self._owner_vector_reader = owner_vector_reader
        self._max_attempts = max_attempts
        self._lease_duration = lease_duration
        self._retry_base_delay = retry_base_delay
        self._retry_delay_cap = retry_delay_cap

    def query_by_delivery_identity(
        self, delivery_identity: str
    ) -> HistoricalBaselineProjectorReadModel | None:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.repository.query_by_delivery_identity(
                delivery_identity
            )

    def query_latest_by_case(
        self, case_no: str
    ) -> HistoricalBaselineProjectorReadModel | None:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.repository.query_latest_by_case(case_no)

    def reconcile_by_delivery_identity(
        self, delivery_identity: str
    ) -> HistoricalBaselineReconcileByIdentityResult:
        model = self.query_by_delivery_identity(delivery_identity)
        if model is None:
            raise HistoricalBaselineProjectorQueryError(
                "projector_delivery_not_found"
            )
        return historical_baseline_reconcile_by_identity_disposition(model)

    def accept(
        self, trigger: HistoricalBaselineProjectorTrigger
    ) -> HistoricalBaselineProjectorDelivery:
        with self._unit_of_work_factory() as unit_of_work:
            delivery = unit_of_work.repository.register_delivery(
                trigger, max_attempts=self._max_attempts
            )
            unit_of_work.commit()
            return delivery

    def run(
        self,
        trigger: HistoricalBaselineProjectorTrigger,
        *,
        now: datetime,
        lease_owner: str,
    ) -> HistoricalBaselineProjectorDelivery:
        delivery = self.accept(trigger)
        if delivery.status is HistoricalBaselineDeliveryStatus.PROCESSED:
            return delivery
        if delivery.status is HistoricalBaselineDeliveryStatus.COMMITTED_UNVERIFIED:
            raise HistoricalBaselineDeliveryError("projector_reconcile_required")

        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.repository.lock_projection_case(trigger)
            current = unit_of_work.repository.load_delivery(trigger, for_update=True)
            checkpoint = unit_of_work.repository.load_checkpoint(
                trigger, for_update=True
            )
            validate_checkpoint_progress(checkpoint, trigger)
            claimed = current.claim(
                now=now,
                lease_owner=lease_owner,
                lease_duration=self._lease_duration,
            )
            unit_of_work.repository.save_delivery(current, claimed)
            unit_of_work.commit()

        try:
            with self._unit_of_work_factory() as unit_of_work:
                repository = unit_of_work.repository
                repository.lock_projection_case(trigger)
                current = repository.load_delivery(trigger, for_update=True)
                if (
                    current.status is not HistoricalBaselineDeliveryStatus.PROCESSING
                    or current.lease_owner != lease_owner
                    or current.lease_expires_at is None
                    or current.lease_expires_at <= now
                ):
                    raise HistoricalBaselineDeliveryError("projector_delivery_lease_lost")
                checkpoint = repository.load_checkpoint(trigger, for_update=True)
                validate_checkpoint_progress(checkpoint, trigger)
                projection_sequence = repository.next_projection_sequence(
                    trigger, for_update=True
                )
                readback = self._owner_vector_reader(unit_of_work, trigger)
                prior = repository.load_active_occurrences(trigger, for_update=True)
                result = project_historical_baseline(
                    replace(
                        trigger.source_intent,
                        projection_sequence=projection_sequence,
                    ),
                    readback,
                    prior_active_occurrences=prior,
                )
                next_checkpoint = HistoricalBaselineSourceCheckpoint.advance(
                    trigger, projection_sequence=projection_sequence
                )
                committed = current.committed(
                    projection_sequence=projection_sequence,
                    projector_receipt_identity=result.receipt.projector_receipt_identity,
                )
                repository.persist_projection(current, result, next_checkpoint)
                repository.save_delivery(current, committed)
                unit_of_work.commit()
        except Exception as error:
            self._record_projection_failure(trigger, now=now, error=error)
            raise

        return self.reconcile(trigger, result)

    def _record_projection_failure(
        self,
        trigger: HistoricalBaselineProjectorTrigger,
        *,
        now: datetime,
        error: Exception,
    ) -> None:
        with self._unit_of_work_factory() as unit_of_work:
            repository = unit_of_work.repository
            repository.lock_projection_case(trigger)
            delivery = repository.load_delivery(trigger, for_update=True)
            if delivery.status is HistoricalBaselineDeliveryStatus.COMMITTED_UNVERIFIED:
                unit_of_work.commit()
                return
            if delivery.status is not HistoricalBaselineDeliveryStatus.PROCESSING:
                raise HistoricalBaselineDeliveryError(
                    "projector_failure_delivery_state_conflict"
                ) from error
            retryable = _is_retryable_projector_error(error)
            delay = min(
                self._retry_base_delay * (2 ** max(delivery.attempt_count - 1, 0)),
                self._retry_delay_cap,
            )
            failed = delivery.fail(
                error_code=_projector_error_code(error),
                retryable=retryable,
                next_attempt_at=now + delay if retryable else None,
            )
            repository.save_delivery(delivery, failed)
            unit_of_work.commit()

    def reconcile(
        self,
        trigger: HistoricalBaselineProjectorTrigger,
        result: HistoricalBaselineProjectionResult,
    ) -> HistoricalBaselineProjectorDelivery:
        with self._unit_of_work_factory() as unit_of_work:
            repository = unit_of_work.repository
            repository.lock_projection_case(trigger)
            delivery = repository.load_delivery(trigger, for_update=True)
            if delivery.status is HistoricalBaselineDeliveryStatus.PROCESSED:
                unit_of_work.commit()
                return delivery
            if delivery.status is not HistoricalBaselineDeliveryStatus.COMMITTED_UNVERIFIED:
                raise HistoricalBaselineDeliveryError("projector_delivery_not_committed")
            if delivery.projector_receipt_identity != result.receipt.projector_receipt_identity:
                raise HistoricalBaselineDeliveryError("projector_receipt_integrity_conflict")
            readback = repository.read_exact_projection(delivery, result)
            exact = readback.matches(result)
            repository.append_post_commit_readback(
                delivery, result, readback, exact=exact
            )
            if exact:
                processed = delivery.processed()
                repository.save_delivery(delivery, processed)
                unit_of_work.commit()
                return processed
            unit_of_work.commit()
            return delivery


def _is_retryable_projector_error(error: Exception) -> bool:
    return isinstance(error, (OperationalError, InterfaceError)) and bool(error.args) and (
        error.args[0] in {1205, 1213, 2003, 2006, 2013}
    )


def _projector_error_code(error: Exception) -> str:
    if isinstance(error, HistoricalBaselineDeliveryError):
        return error.code
    if isinstance(error, HistoricalBaselineProjectorQueryError):
        return error.code
    if _is_retryable_projector_error(error):
        return "projector_storage_transient"
    return "projector_execution_failed"


__all__ = [
    "HistoricalBaselineExactReadback",
    "HistoricalBaselineProjectorRepositoryPort",
    "HistoricalBaselineProjectorUnitOfWork",
    "HistoricalBaselineProjectorWorker",
    "HistoricalBaselineReconcileByIdentityResult",
]
