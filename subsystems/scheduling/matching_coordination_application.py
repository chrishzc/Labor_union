"""
File: matching_coordination_application.py
Description: 編排 M3 typed Query／Preview／Apply 與單一 outer Unit of Work。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Callable, Protocol, TypeAlias

from domains.orders.terms import OrderAggregateFacts
from domains.scheduling.matching_coordination import (
    MatchingSourceTuple,
    build_criteria_snapshot,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.clock import BusinessClock, SystemBusinessClock
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, IdempotencyKey
from domains.scheduling.staff_availability import StaffAvailabilityFacts
from subsystems.scheduling.matching_coordination_contracts import (
    ApplyInitialCriteriaSnapshot,
    ApplyLeaveImpactOnMatching,
    ApplyServiceDateChangeRematch,
    MatchingApplyReceipt,
    MatchingCommand,
    MatchingCriteriaSnapshotView,
    PreviewInitialCriteriaSnapshot,
    PreviewLeaveImpactOnMatching,
    PreviewServiceDateChangeRematch,
    QueryMatchingCoordination,
    snapshot_view,
)
from subsystems.orders.service_date_confirmation_workflow import (
    ServiceDateConfirmationFacts,
)
from subsystems.scheduling.matching_coordination_query import (
    MatchingCoordinationQuery,
    MatchingCoordinationQueryResult,
)
from subsystems.scheduling.matching_coordination_workflow import (
    MatchingCoordinationFacts,
    MatchingCoordinationWorkflow,
)
from subsystems.scheduling.matching_leave_integration import (
    MatchingLeaveImpactRequest,
    MatchingLeaveImpactResult,
)


class MatchingApplicationError(Exception):
    """Application boundary failure with a stable M3 error code."""

    def __init__(self, error: TypedError) -> None:
        super().__init__(error.message)
        self.error = error


class MatchingCoordinationFactsReader(Protocol):
    """Typed owner-fact reader; it never returns persistence mappings."""

    def load(self, case_no: str) -> MatchingCoordinationFacts: ...

    def load_fresh(
        self, case_no: str, *, for_update: bool
    ) -> MatchingCoordinationFacts: ...

    def load_initial(self, case_no: str) -> "InitialCriteriaSourceFacts": ...

    def load_initial_fresh(
        self, case_no: str, *, for_update: bool
    ) -> "InitialCriteriaSourceFacts": ...


class MatchingCoordinationRepository(Protocol):
    """M3 persistence port; every method borrows the application transaction."""

    def claim_or_replay(
        self,
        idempotency_key: IdempotencyKey,
        command_fingerprint: PreviewFingerprint,
        correlation_id: CorrelationId,
    ) -> MatchingApplyReceipt | None: ...

    def lock_matching_root(self, case_no: str) -> None: ...

    def append_lineage(
        self,
        command: MatchingCommand,
        facts: MatchingCoordinationFacts,
        receipt: MatchingApplyReceipt,
    ) -> None: ...

    def append_typed_intents(
        self, command: MatchingCommand, receipt: MatchingApplyReceipt
    ) -> None: ...

    def save_receipt(
        self,
        command: MatchingCommand,
        command_fingerprint: PreviewFingerprint,
        receipt: MatchingApplyReceipt,
    ) -> None: ...


class MatchingUnitOfWork(Protocol):
    """The composition-owned transaction boundary."""

    def __enter__(self) -> "MatchingUnitOfWork": ...

    def __exit__(self, exception_type, exception, traceback) -> bool: ...

    def commit(self) -> None: ...


class LeaveImpactPreviewPort(Protocol):
    def evaluate(
        self, request: MatchingLeaveImpactRequest
    ) -> MatchingLeaveImpactResult: ...


PreviewResult: TypeAlias = object


@dataclass(frozen=True, slots=True)
class InitialCriteriaSourceFacts:
    """Orders-owned facts sufficient to create the first M3 snapshot."""

    case_no: str
    orders_terms: OrderAggregateFacts
    orders_service_dates: ServiceDateConfirmationFacts
    source_versions: MatchingSourceTuple

    def __post_init__(self) -> None:
        if self.orders_terms.case_no != self.case_no:
            raise ValueError("initial criteria orders identity mismatch")
        if self.orders_service_dates.case_no != self.case_no:
            raise ValueError("initial criteria service-date identity mismatch")
        if (
            self.orders_service_dates.current_version is None
            or not self.orders_service_dates.current_dates
        ):
            raise ValueError("matching confirmed service dates are required")


@dataclass(frozen=True, slots=True)
class ServiceDateRematchPreviewInput:
    """Typed inputs supplied by the owning Scheduling facts adapter."""

    case_no: str
    assignment_id: int
    original_staff_id: int
    original_service_dates: tuple[date, ...]
    shifted_service_dates: tuple[date, ...]
    availability: StaffAvailabilityFacts


class MatchingCoordinationApplication:
    """Single composition for typed M3 query, preview, and apply operations."""

    def __init__(
        self,
        facts_reader: MatchingCoordinationFactsReader,
        repository: MatchingCoordinationRepository,
        unit_of_work_factory: Callable[[], MatchingUnitOfWork] | None = None,
        workflow: MatchingCoordinationWorkflow | None = None,
        *,
        uow_factory: Callable[[], MatchingUnitOfWork] | None = None,
        leave_impact: LeaveImpactPreviewPort | None = None,
        service_date_input_loader: Callable[
            [
                PreviewServiceDateChangeRematch | ApplyServiceDateChangeRematch,
                bool,
            ],
            ServiceDateRematchPreviewInput,
        ]
        | None = None,
        clock: BusinessClock | None = None,
    ) -> None:
        if unit_of_work_factory is not None and uow_factory is not None:
            raise TypeError("provide only one unit-of_work_factory")
        selected_factory = unit_of_work_factory or uow_factory
        if selected_factory is None:
            raise TypeError("unit_of_work_factory is required")
        self._facts_reader = facts_reader
        self._repository = repository
        self._unit_of_work_factory = selected_factory
        self._workflow = workflow or MatchingCoordinationWorkflow()
        self._leave_impact = leave_impact
        self._service_date_input_loader = service_date_input_loader
        self._clock = clock or SystemBusinessClock()
        self._query = MatchingCoordinationQuery(facts_reader)

    def query(
        self, command: QueryMatchingCoordination
    ) -> MatchingCoordinationQueryResult:
        """Load owner facts once and return the complete typed query result."""

        return self._query.execute(command)

    def preview(self, command: MatchingCommand) -> PreviewResult:
        """Run the existing pure workflow against a non-locking typed snapshot."""

        if isinstance(command, PreviewInitialCriteriaSnapshot):
            return snapshot_view(self._initial_facts(command.case_no, for_update=False).snapshot)
        facts = self._facts_reader.load(command.case_no)
        return self._workflow.preview(command, facts)

    def apply(self, command: MatchingCommand) -> MatchingApplyReceipt:
        """Claim, fresh-read, evaluate, append M3 lineage, then commit once."""

        command_fingerprint = _command_fingerprint(command)
        with self._unit_of_work_factory() as unit:
            replay = self._repository.claim_or_replay(
                command.idempotency_key,
                command_fingerprint,
                command.correlation_id,
            )
            if replay is not None:
                return replay

            # The M3 root lock precedes the fresh owner-fact read.  Owner roots
            # are locked by their typed reader, never by this coordinator.
            self._repository.lock_matching_root(command.case_no)
            facts = (
                self._initial_facts(command.case_no, for_update=True)
                if isinstance(command, ApplyInitialCriteriaSnapshot)
                else self._load_fresh(command.case_no)
            )
            if isinstance(command, ApplyServiceDateChangeRematch):
                service_date_inputs = self._service_date_inputs(
                    command,
                    for_update=True,
                )
                outcome = self._workflow.preview_service_date_shift(
                    command,
                    facts,
                    service_date_inputs.availability,
                )
                preview_fingerprint = outcome.source_fingerprint
            elif isinstance(command, ApplyLeaveImpactOnMatching):
                leave_result = self._evaluate_leave_impact(
                    command,
                    facts,
                    receipt_key=command.leave_reference,
                    criteria_snapshot_id=command.criteria_snapshot_id,
                    expected_leave_version=command.expected_leave_version,
                    original_staff_id=command.original_staff_id,
                )
                if command.expected_source_versions != leave_result.source_versions:
                    raise self._blocked(
                        command.correlation_id, "matching_leave_reference_stale"
                    )
                facts = replace(facts, source_versions=leave_result.source_versions)
                preview_fingerprint = leave_result.preview_fingerprint
            else:
                preview_fingerprint = _preview_fingerprint(command, facts)
            receipt = self._workflow.apply(
                command,
                facts,
                preview_fingerprint=preview_fingerprint,
            )
            self._repository.append_lineage(command, facts, receipt)
            self._repository.save_receipt(
                command,
                command_fingerprint,
                receipt,
            )
            self._repository.append_typed_intents(command, receipt)
            unit.commit()
            return receipt

    def _initial_facts(
        self, case_no: str, *, for_update: bool
    ) -> MatchingCoordinationFacts:
        method_name = "load_initial_fresh" if for_update else "load_initial"
        loader = getattr(self._facts_reader, method_name, None)
        if not callable(loader):
            raise self._blocked(
                CorrelationId(f"matching:initial:{case_no}"),
                "matching_lock_set_stale" if for_update else "matching_criteria_invalid",
            )
        source = loader(case_no, for_update=True) if for_update else loader(case_no)
        if not isinstance(source, InitialCriteriaSourceFacts):
            raise TypeError("initial matching criteria facts must be typed")
        criteria = _initial_criteria_payload(source)
        provisional = build_criteria_snapshot(
            snapshot_id=f"matching:{case_no}:criteria:initial",
            case_no=case_no,
            criteria_version=1,
            criteria=criteria,
            source_versions=source.source_versions,
            created_at=self._clock.now(),
        )
        snapshot = build_criteria_snapshot(
            snapshot_id=(
                f"matching:{case_no}:criteria:1:{provisional.fingerprint.value[:16]}"
            ),
            case_no=case_no,
            criteria_version=1,
            criteria=criteria,
            source_versions=source.source_versions,
            created_at=provisional.created_at,
        )
        return MatchingCoordinationFacts(
            snapshot=snapshot,
            package=None,
            source_versions=source.source_versions,
        )

    def preview_leave_impact(
        self,
        command: PreviewLeaveImpactOnMatching,
        request: MatchingLeaveImpactRequest,
    ) -> MatchingLeaveImpactResult:
        """Evaluate a canonical leave receipt without mutating Scheduling roots."""

        evaluator = self._leave_impact
        facts = self._facts_reader.load(command.case_no)
        if request.expected_source_versions != command.expected_source_versions:
            raise self._blocked(command.correlation_id, "matching_leave_reference_stale")
        if command.expected_source_versions != facts.source_versions:
            raise self._blocked(command.correlation_id, "matching_source_version_conflict")
        return self._evaluate_leave_impact(
            command,
            facts,
            receipt_key=request.receipt_key,
            criteria_snapshot_id=request.criteria_snapshot_id,
            expected_leave_version=request.expected_leave_version,
            original_staff_id=request.original_staff_id,
        )

    def _evaluate_leave_impact(
        self,
        command: PreviewLeaveImpactOnMatching | ApplyLeaveImpactOnMatching,
        facts: MatchingCoordinationFacts,
        *,
        receipt_key: str,
        criteria_snapshot_id: str,
        expected_leave_version: int,
        original_staff_id: int,
    ) -> MatchingLeaveImpactResult:
        evaluator = self._leave_impact
        if evaluator is None:
            raise self._blocked(command.correlation_id, "matching_leave_reference_stale")
        if (
            facts.package is None
            or command.package_id != facts.package.package_id
            or criteria_snapshot_id != facts.snapshot.snapshot_id
            or facts.package.criteria_snapshot_id != criteria_snapshot_id
        ):
            raise self._blocked(command.correlation_id, "matching_package_stale")
        return evaluator.evaluate(
            MatchingLeaveImpactRequest(
                receipt_key=receipt_key,
                case_no=command.case_no,
                package_id=command.package_id,
                criteria_snapshot_id=criteria_snapshot_id,
                expected_leave_version=expected_leave_version,
                original_staff_id=original_staff_id,
                expected_source_versions=facts.source_versions,
                correlation_id=command.correlation_id,
            )
        )

    def preview_service_date_rematch(
        self,
        command: PreviewServiceDateChangeRematch,
        inputs: ServiceDateRematchPreviewInput | None = None,
    ) -> PreviewResult:
        """Project a date shift through the existing pure workflow."""

        facts = self._facts_reader.load(command.case_no)
        selected_inputs = inputs
        if selected_inputs is None:
            selected_inputs = self._service_date_inputs(command, for_update=False)
        self._validate_service_date_inputs(command, selected_inputs)
        return self._workflow.preview_service_date_shift(
            command,
            facts,
            selected_inputs.availability,
        )

    def _service_date_inputs(
        self,
        command: PreviewServiceDateChangeRematch | ApplyServiceDateChangeRematch,
        *,
        for_update: bool,
    ) -> ServiceDateRematchPreviewInput:
        loader = self._service_date_input_loader
        if loader is None:
            raise self._blocked(
                command.correlation_id, "matching_service_date_conflict"
            )
        try:
            selected = loader(command, for_update=for_update)
        except (TypeError, ValueError) as error:
            raise self._blocked(
                command.correlation_id, "matching_service_date_conflict"
            ) from error
        if not isinstance(selected, ServiceDateRematchPreviewInput):
            raise TypeError("service-date rematch inputs must be typed")
        self._validate_service_date_inputs(command, selected)
        return selected

    def _validate_service_date_inputs(
        self,
        command: PreviewServiceDateChangeRematch | ApplyServiceDateChangeRematch,
        selected: ServiceDateRematchPreviewInput,
    ) -> None:
        if (
            selected.case_no != command.case_no
            or selected.assignment_id != command.assignment_id
            or selected.original_staff_id != command.original_staff_id
            or selected.original_service_dates != command.original_service_dates
            or selected.shifted_service_dates != command.shifted_service_dates
        ):
            raise self._blocked(
                command.correlation_id, "matching_service_date_conflict"
            )

    def _load_fresh(self, case_no: str) -> MatchingCoordinationFacts:
        loader = getattr(self._facts_reader, "load_fresh", None)
        if not callable(loader):
            raise self._blocked(
                CorrelationId(f"matching:fresh:{case_no}"),
                "matching_lock_set_stale",
            )
        facts = loader(case_no, for_update=True)
        if not isinstance(facts, MatchingCoordinationFacts):
            raise TypeError("fresh matching facts must be typed")
        return facts

    @staticmethod
    def _blocked(correlation_id: CorrelationId, code: str) -> MatchingApplicationError:
        return MatchingApplicationError(
            TypedError(ErrorCategory.DOMAIN_BLOCKED, code, code, correlation_id)
        )


def _command_fingerprint(command: MatchingCommand) -> PreviewFingerprint:
    from subsystems.scheduling.matching_coordination_contracts import command_fingerprint

    return command_fingerprint(command)


def _preview_fingerprint(
    command: MatchingCommand, facts: MatchingCoordinationFacts
) -> PreviewFingerprint:
    request_fingerprint = getattr(command, "preview_fingerprint", None)
    if isinstance(request_fingerprint, PreviewFingerprint):
        return request_fingerprint
    package = facts.package
    if package is not None and package.fingerprint is not None:
        return package.fingerprint
    return facts.snapshot.fingerprint


def _initial_criteria_payload(source: InitialCriteriaSourceFacts) -> dict[str, object]:
    terms = source.orders_terms.terms
    return {
        "confirmed_service_dates": tuple(
            value.isoformat() for value in source.orders_service_dates.current_dates
        ),
        "planned_start_date": terms.planned_start_date.isoformat(),
        "requires_cooking": terms.requires_cooking,
        "service_days": terms.service_days,
        "service_hours_per_day": terms.service_hours_per_day,
        "service_time": terms.service_time.canonical_payload(),
    }


__all__ = [
    "InitialCriteriaSourceFacts",
    "LeaveImpactPreviewPort",
    "MatchingApplicationError",
    "MatchingCoordinationApplication",
    "MatchingCoordinationFactsReader",
    "MatchingCoordinationRepository",
    "MatchingUnitOfWork",
    "ServiceDateRematchPreviewInput",
]
