"""
File: matching_coordination_facts_adapter.py
Description: 以既有 typed owner ports 唯讀組合 M3 十三來源事實。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from domains.scheduling.matching_coordination import (
    CandidateEligibility,
    DynamicWillingnessLineage,
    MatchingCandidateResult,
    MatchingCriteriaSnapshot,
    MatchingSourceTuple,
    MatchingSourceVersion,
    StableRejectionReason,
    canonical_source_tuple,
)
from subsystems.scheduling.candidate_contact_pool_workflow import (
    CandidateContactPoolState,
)
from subsystems.scheduling.matching_assignment_conversion import (
    CanonicalAssignmentConversionReceipt,
)
from subsystems.scheduling.matching_coordination_query import (
    AssignmentConversionReferenceQueryPort,
    CandidatePoolQueryPort,
    IncumbentAssignmentQueryPort,
    LeaveRequestOutcomeQueryPort,
    MatchingCriteriaSnapshotQueryPort,
    MatchingPackageQueryPort,
    OrdersServiceDateQueryPort,
    OrdersTermsQueryPort,
    SchedulingAvailabilityQueryPort,
    SchedulingEffectiveGenerationQueryPort,
    StaffLifecycleQueryPort,
    StaffMatchingProfileQueryPort,
    StaffProfileValuesFacts,
    incumbent_assignment_source_version,
    leave_request_or_outcome_source_version,
    assignment_conversion_reference_source_version,
    candidate_pool_source_version,
    matching_criteria_snapshot_source_version,
    matching_package_source_version,
    orders_service_dates_source_version,
    orders_terms_source_version,
    scheduling_availability_source_version,
    scheduling_effective_generation_source_version,
    staff_lifecycle_source_version,
    staff_profile_definition_source_version,
    staff_profile_values_source_version,
)
from subsystems.scheduling.matching_coordination_workflow import (
    MatchingCoordinationFacts,
)
from subsystems.scheduling.matching_coordination_application import (
    InitialCriteriaSourceFacts,
)
from domains.scheduling.matching_coordination import MatchingPackage
from domains.scheduling.assignment_plan import AssignmentPlanFacts
from domains.scheduling.staff_availability import StaffAvailabilityFacts
from domains.scheduling.generation import SchedulingGenerationFacts
from domains.scheduling.staff_matching_preferences import StaffPreferenceDefinition
from domains.staff.retirement import StaffLifecycleFact
from domains.orders.terms import OrderAggregateFacts
from subsystems.orders.service_date_confirmation_workflow import (
    ServiceDateConfirmationFacts,
)
from subsystems.scheduling.matching_leave_integration import (
    CanonicalSchedulingLeaveReference,
)


SOURCE_ORDER: tuple[str, ...] = (
    "orders_terms",
    "orders_service_dates",
    "scheduling_availability",
    "scheduling_effective_generation",
    "staff_profile_definition",
    "staff_profile_values",
    "staff_lifecycle",
    "matching_criteria_snapshot",
    "candidate_pool",
    "matching_package",
    "incumbent_assignment",
    "leave_request_or_outcome",
    "assignment_conversion_reference",
)


class MatchingCoordinationFactsAdapterError(ValueError):
    """所有來源不可用、部分回傳或歧義時的 typed fail-closed error。"""

    def __init__(self, source_kind: str, reason: str) -> None:
        self.source_kind = source_kind
        self.reason = reason
        super().__init__(f"matching source {source_kind} {reason}")


class MatchingAvailabilityQueryAdapter:
    """Compose confirmed owner dates with Staff Availability's typed read."""

    def __init__(self, service_dates: Any, availability: Any) -> None:
        self._service_dates = service_dates
        self._availability = availability

    def load_availability(
        self,
        case_no: str,
        staff_ids: tuple[int, ...],
        *,
        for_update: bool = False,
    ) -> tuple[StaffAvailabilityFacts, ...]:
        dates = self._service_dates.load_service_dates(
            case_no, for_update=for_update
        )
        if dates.current_version is None or not dates.current_dates:
            raise MatchingCoordinationFactsAdapterError(
                "orders_service_dates", "not_confirmed"
            )
        return tuple(
            self._availability.load_matching_facts(
                staff_id, dates.current_dates, for_update=for_update
            )
            for staff_id in staff_ids
        )


class MatchingEffectiveGenerationQueryAdapter:
    """Narrow the existing typed Orders/Scheduling read model to generation facts."""

    def __init__(self, order_terms: Any) -> None:
        self._order_terms = order_terms

    def load_effective_generation(
        self, case_no: str, *, for_update: bool = False
    ) -> SchedulingGenerationFacts:
        if for_update:
            staff_ids = self._order_terms.preflight_impacted_staff_ids(case_no)
            return self._order_terms.load_for_apply(case_no, staff_ids).scheduling
        return self._order_terms.load_for_preview(case_no).scheduling


@dataclass(frozen=True, slots=True)
class MatchingCoordinationFactsProjection:
    """完整且已翻譯的 owner facts；不含 persistence mapping。"""

    case_no: str
    orders_terms: OrderAggregateFacts
    orders_service_dates: ServiceDateConfirmationFacts
    scheduling_availability: tuple[StaffAvailabilityFacts, ...]
    scheduling_effective_generation: SchedulingGenerationFacts
    staff_profile_definition: tuple[tuple[StaffPreferenceDefinition, int], ...]
    staff_profile_values: tuple[StaffProfileValuesFacts, ...]
    staff_lifecycle: tuple[StaffLifecycleFact, ...]
    matching_criteria_snapshot: MatchingCriteriaSnapshot
    candidate_pool: CandidateContactPoolState
    matching_package: MatchingPackage | None
    incumbent_assignment: AssignmentPlanFacts
    leave_request_or_outcome: CanonicalSchedulingLeaveReference | None
    assignment_conversion_reference: CanonicalAssignmentConversionReceipt | None
    source_versions: MatchingSourceTuple


class MySqlMatchingCoordinationFactsAdapter:
    """以注入 ports 讀取 M3 facts；自身不建立連線、不執行 SQL、不 commit。"""

    def __init__(
        self,
        *,
        orders_terms: OrdersTermsQueryPort | None = None,
        orders_service_dates: OrdersServiceDateQueryPort | None = None,
        scheduling_availability: SchedulingAvailabilityQueryPort | None = None,
        scheduling_effective_generation: SchedulingEffectiveGenerationQueryPort | None = None,
        staff_profile: StaffMatchingProfileQueryPort | None = None,
        staff_lifecycle: StaffLifecycleQueryPort | None = None,
        matching_criteria_snapshot: MatchingCriteriaSnapshotQueryPort | None = None,
        candidate_pool: CandidatePoolQueryPort | None = None,
        matching_package: MatchingPackageQueryPort | None = None,
        incumbent_assignment: IncumbentAssignmentQueryPort | None = None,
        leave_request_or_outcome: LeaveRequestOutcomeQueryPort | None = None,
        assignment_conversion_reference: AssignmentConversionReferenceQueryPort | None = None,
        staff_ids: tuple[int, ...] | Callable[[str], tuple[int, ...]] = (),
        leave_receipt_key: str | None = None,
        assignment_request_id: str | None = None,
        not_consulted_sources: Iterable[str] = (),
        fresh_loader: Callable[[str], MatchingCoordinationFacts] | None = None,
        initial_fresh_loader: Callable[[str], InitialCriteriaSourceFacts] | None = None,
    ) -> None:
        self._ports = {
            "orders_terms": orders_terms,
            "orders_service_dates": orders_service_dates,
            "scheduling_availability": scheduling_availability,
            "scheduling_effective_generation": scheduling_effective_generation,
            "staff_profile_definition": staff_profile,
            "staff_profile_values": staff_profile,
            "staff_lifecycle": staff_lifecycle,
            "matching_criteria_snapshot": matching_criteria_snapshot,
            "candidate_pool": candidate_pool,
            "matching_package": matching_package,
            "incumbent_assignment": incumbent_assignment,
            "leave_request_or_outcome": leave_request_or_outcome,
            "assignment_conversion_reference": assignment_conversion_reference,
        }
        self._staff_ids = staff_ids
        self._leave_receipt_key = leave_receipt_key
        self._assignment_request_id = assignment_request_id
        self._fresh_loader = fresh_loader
        self._initial_fresh_loader = initial_fresh_loader
        self._not_consulted = frozenset(not_consulted_sources)
        unknown = self._not_consulted.difference(SOURCE_ORDER)
        if unknown:
            raise ValueError(f"unknown not_consulted source: {sorted(unknown)}")
        unsupported = self._not_consulted.difference(
            {"leave_request_or_outcome", "assignment_conversion_reference"}
        )
        if unsupported:
            raise ValueError(
                "required owner facts cannot be marked not_consulted: "
                f"{sorted(unsupported)}"
            )
        if not isinstance(staff_ids, tuple) and not callable(staff_ids):
            raise TypeError("staff ids must be a typed tuple or resolver")
        if isinstance(staff_ids, tuple) and staff_ids != tuple(sorted(set(staff_ids))):
            raise ValueError("staff ids must be sorted and unique")

    def _staff_ids_for(self, case_no: str) -> tuple[int, ...]:
        values = self._staff_ids(case_no) if callable(self._staff_ids) else self._staff_ids
        if not isinstance(values, tuple) or any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in values
        ):
            raise MatchingCoordinationFactsAdapterError(
                "scheduling_availability", "partial_staff_identity"
            )
        if values != tuple(sorted(set(values))):
            raise MatchingCoordinationFactsAdapterError(
                "scheduling_availability", "ambiguous_staff_identity"
            )
        return values

    def _read(self, source_kind: str, operation: Callable[[], Any]) -> Any:
        if source_kind in self._not_consulted:
            return None
        try:
            value = operation()
        except MatchingCoordinationFactsAdapterError:
            raise
        except Exception as exc:
            reason = "ambiguous" if "ambiguous" in exc.__class__.__name__.lower() else "unavailable"
            raise MatchingCoordinationFactsAdapterError(source_kind, reason) from exc
        if value is None:
            raise MatchingCoordinationFactsAdapterError(source_kind, "unavailable")
        return value

    def _read_allow_none(
        self, source_kind: str, operation: Callable[[], Any]
    ) -> Any | None:
        """Read a source whose canonical contract defines absence as a state."""

        if source_kind in self._not_consulted:
            return None
        try:
            return operation()
        except MatchingCoordinationFactsAdapterError:
            raise
        except Exception as exc:
            reason = (
                "ambiguous"
                if "ambiguous" in exc.__class__.__name__.lower()
                else "unavailable"
            )
            raise MatchingCoordinationFactsAdapterError(source_kind, reason) from exc

    @staticmethod
    def _owner_read(method: Callable[..., Any], *args: Any, for_update: bool) -> Any:
        return method(*args, for_update=True) if for_update else method(*args)

    def load_sources(
        self, case_no: str, *, for_update: bool = False
    ) -> MatchingCoordinationFactsProjection:
        if not isinstance(case_no, str) or not case_no.strip():
            raise TypeError("case number must be canonical text")
        case_no = case_no.strip()
        staff_ids = self._staff_ids_for(case_no)

        orders_terms = self._read(
            "orders_terms",
            lambda: self._owner_read(
                self._ports["orders_terms"].load_order_terms,
                case_no,
                for_update=for_update,
            ),
        )
        if not isinstance(orders_terms, OrderAggregateFacts):
            raise MatchingCoordinationFactsAdapterError("orders_terms", "partial")
        orders_dates = self._read(
            "orders_service_dates",
            lambda: self._owner_read(
                self._ports["orders_service_dates"].load_service_dates,
                case_no,
                for_update=for_update,
            ),
        )
        if not isinstance(orders_dates, ServiceDateConfirmationFacts):
            raise MatchingCoordinationFactsAdapterError("orders_service_dates", "partial")

        availability = self._read(
            "scheduling_availability",
            lambda: self._owner_read(
                self._ports["scheduling_availability"].load_availability,
                case_no,
                staff_ids,
                for_update=for_update,
            ),
        )
        if not isinstance(availability, tuple) or any(not isinstance(item, StaffAvailabilityFacts) for item in availability):
            raise MatchingCoordinationFactsAdapterError("scheduling_availability", "partial")

        generation = self._read(
            "scheduling_effective_generation",
            lambda: self._owner_read(
                self._ports["scheduling_effective_generation"].load_effective_generation,
                case_no,
                for_update=for_update,
            ),
        )
        if not isinstance(generation, SchedulingGenerationFacts):
            raise MatchingCoordinationFactsAdapterError("scheduling_effective_generation", "partial")

        definitions = self._read(
            "staff_profile_definition",
            lambda: self._owner_read(
                self._ports["staff_profile_definition"].load_definitions,
                for_update=for_update,
            ),
        )
        values = self._read(
            "staff_profile_values",
            lambda: self._owner_read(
                self._ports["staff_profile_values"].load_profile_values,
                staff_ids,
                for_update=for_update,
            ),
        )
        lifecycle = self._read(
            "staff_lifecycle",
            lambda: self._owner_read(
                self._ports["staff_lifecycle"].load_lifecycle,
                staff_ids,
                for_update=for_update,
            ),
        )
        if not isinstance(definitions, tuple) or any(
            not isinstance(item, tuple) or len(item) != 2 or not isinstance(item[1], int)
            for item in definitions
        ):
            raise MatchingCoordinationFactsAdapterError("staff_profile_definition", "partial")
        if not isinstance(values, tuple) or any(
            not isinstance(item, StaffProfileValuesFacts) for item in values
        ):
            raise MatchingCoordinationFactsAdapterError("staff_profile_values", "partial")
        if not isinstance(lifecycle, tuple) or any(not isinstance(item, StaffLifecycleFact) for item in lifecycle):
            raise MatchingCoordinationFactsAdapterError("staff_lifecycle", "partial")
        if orders_terms.case_no != case_no:
            raise MatchingCoordinationFactsAdapterError("orders_terms", "ambiguous_identity")
        if orders_dates.case_no != case_no or generation.case_no != case_no:
            raise MatchingCoordinationFactsAdapterError("orders_service_dates", "ambiguous_identity")

        snapshot = self._read(
            "matching_criteria_snapshot",
            lambda: self._owner_read(
                self._ports["matching_criteria_snapshot"].load_current_snapshot,
                case_no,
                for_update=for_update,
            ),
        )
        if not isinstance(snapshot, MatchingCriteriaSnapshot):
            raise MatchingCoordinationFactsAdapterError("matching_criteria_snapshot", "partial")
        if snapshot.case_no != case_no:
            raise MatchingCoordinationFactsAdapterError("matching_criteria_snapshot", "ambiguous_identity")
        pool = self._read(
            "candidate_pool",
            lambda: self._owner_read(
                self._ports["candidate_pool"].load_candidate_pool,
                case_no,
                for_update=for_update,
            ),
        )
        if not isinstance(pool, CandidateContactPoolState):
            raise MatchingCoordinationFactsAdapterError("candidate_pool", "partial")
        if pool.case_no != case_no:
            raise MatchingCoordinationFactsAdapterError("candidate_pool", "ambiguous_identity")
        if for_update and tuple(
            sorted({item.staff_id for item in pool.candidates})
        ) != staff_ids:
            raise MatchingCoordinationFactsAdapterError(
                "candidate_pool", "lock_set_changed"
            )
        package = self._read_allow_none(
            "matching_package",
            lambda: self._owner_read(
                self._ports["matching_package"].load_current_package,
                case_no,
                for_update=for_update,
            ),
        )
        if package is not None and not isinstance(package, MatchingPackage):
            raise MatchingCoordinationFactsAdapterError("matching_package", "partial")
        incumbent = self._read(
            "incumbent_assignment",
            lambda: self._owner_read(
                self._ports["incumbent_assignment"].load_current_assignments,
                case_no,
                for_update=for_update,
            ),
        )
        if not isinstance(incumbent, AssignmentPlanFacts):
            raise MatchingCoordinationFactsAdapterError("incumbent_assignment", "partial")
        if incumbent.case_no != case_no:
            raise MatchingCoordinationFactsAdapterError("incumbent_assignment", "ambiguous_identity")

        leave = self._load_optional_reference(
            "leave_request_or_outcome", self._leave_receipt_key,
            lambda key: self._ports["leave_request_or_outcome"].get_canonical_receipt(key),
        )
        conversion = self._load_optional_reference(
            "assignment_conversion_reference", self._assignment_request_id,
            lambda key: self._ports["assignment_conversion_reference"].get_canonical_receipt(key),
        )
        if leave is not None and not isinstance(leave, CanonicalSchedulingLeaveReference):
            raise MatchingCoordinationFactsAdapterError("leave_request_or_outcome", "partial")
        if conversion is not None and not isinstance(conversion, CanonicalAssignmentConversionReceipt):
            raise MatchingCoordinationFactsAdapterError("assignment_conversion_reference", "partial")

        source_versions = canonical_source_tuple(
            (
                self._version("orders_terms", lambda: orders_terms_source_version(orders_terms)),
                self._version("orders_service_dates", lambda: orders_service_dates_source_version(orders_dates)),
                self._version("scheduling_availability", lambda: scheduling_availability_source_version(case_no, availability)),
                self._version("scheduling_effective_generation", lambda: scheduling_effective_generation_source_version(generation)),
                self._version("staff_profile_definition", lambda: staff_profile_definition_source_version(definitions)),
                self._version("staff_profile_values", lambda: staff_profile_values_source_version(case_no, values)),
                self._version("staff_lifecycle", lambda: staff_lifecycle_source_version(case_no, lifecycle)),
                self._version("matching_criteria_snapshot", lambda: matching_criteria_snapshot_source_version(snapshot)),
                self._version("candidate_pool", lambda: candidate_pool_source_version(pool)),
                self._version("matching_package", lambda: matching_package_source_version(package, case_no=case_no)),
                self._version("incumbent_assignment", lambda: incumbent_assignment_source_version(incumbent)),
                MatchingSourceVersion.not_consulted("leave_request_or_outcome")
                if self._leave_receipt_key is None or "leave_request_or_outcome" in self._not_consulted
                else self._version("leave_request_or_outcome", lambda: leave_request_or_outcome_source_version(leave, case_no=case_no)),
                MatchingSourceVersion.not_consulted("assignment_conversion_reference")
                if self._assignment_request_id is None or "assignment_conversion_reference" in self._not_consulted
                else self._version("assignment_conversion_reference", lambda: assignment_conversion_reference_source_version(conversion, request_id=self._assignment_request_id)),
            )
        )
        return MatchingCoordinationFactsProjection(
            case_no, orders_terms, orders_dates, availability, generation,
            definitions, values, lifecycle, snapshot, pool, package, incumbent,
            leave, conversion, source_versions,
        )

    def _load_optional_reference(
        self, source_kind: str, key: str | None, operation: Callable[[str], Any]
    ) -> Any:
        if source_kind in self._not_consulted or key is None:
            return None
        return self._read(source_kind, lambda: operation(key))

    def _version(self, source_kind: str, operation: Callable[[], Any]) -> Any:
        try:
            return operation()
        except MatchingCoordinationFactsAdapterError:
            raise
        except Exception as exc:
            reason = "ambiguous" if "ambiguous" in exc.__class__.__name__.lower() else "partial"
            raise MatchingCoordinationFactsAdapterError(source_kind, reason) from exc

    def load(
        self, case_no: str, *, for_update: bool = False
    ) -> MatchingCoordinationFacts:
        if for_update and (
            self._leave_receipt_key is not None
            or self._assignment_request_id is not None
        ):
            raise MatchingCoordinationFactsAdapterError(
                "owner_lock_set", "optional_reference_lock_unavailable"
            )
        projection = self.load_sources(case_no, for_update=for_update)
        snapshots = self._read(
            "matching_criteria_snapshot",
            lambda: self._owner_read(
                self._ports[
                    "matching_criteria_snapshot"
                ].load_snapshot_history,
                case_no,
                for_update=for_update,
            ),
        )
        if not isinstance(snapshots, tuple) or any(
            not isinstance(item, MatchingCriteriaSnapshot) for item in snapshots
        ):
            raise MatchingCoordinationFactsAdapterError(
                "matching_criteria_snapshot", "partial_history"
            )
        versions = tuple(item.criteria_version for item in snapshots)
        if not snapshots or versions != tuple(sorted(set(versions))):
            raise MatchingCoordinationFactsAdapterError(
                "matching_criteria_snapshot", "ambiguous_history"
            )
        if any(item.case_no != case_no for item in snapshots):
            raise MatchingCoordinationFactsAdapterError(
                "matching_criteria_snapshot", "ambiguous_identity"
            )
        if snapshots[-1] != projection.matching_criteria_snapshot:
            raise MatchingCoordinationFactsAdapterError(
                "matching_criteria_snapshot", "stale_history"
            )
        willingness = self._read(
            "matching_criteria_snapshot",
            lambda: self._owner_read(
                self._ports[
                    "matching_criteria_snapshot"
                ].load_willingness_history,
                case_no,
                for_update=for_update,
            ),
        )
        if not isinstance(willingness, tuple) or any(
            not isinstance(item, DynamicWillingnessLineage) for item in willingness
        ):
            raise MatchingCoordinationFactsAdapterError(
                "matching_criteria_snapshot", "partial_willingness_history"
            )
        event_ids = tuple(item.event_id for item in willingness)
        snapshot_by_id = {item.snapshot_id: item for item in snapshots}
        if len(event_ids) != len(set(event_ids)) or any(
            item.snapshot_id not in snapshot_by_id for item in willingness
        ):
            raise MatchingCoordinationFactsAdapterError(
                "matching_criteria_snapshot", "ambiguous_willingness_history"
            )
        candidate_staff: dict[str, int] = {}
        for item in projection.candidate_pool.candidates:
            candidate_id = str(item.id)
            if candidate_id in candidate_staff:
                raise MatchingCoordinationFactsAdapterError(
                    "candidate_pool", "ambiguous_identity"
                )
            candidate_staff[candidate_id] = item.staff_id
        lineage_staff: dict[str, int] = {}
        for item in willingness:
            snapshot = snapshot_by_id[item.snapshot_id]
            if item.source_versions != snapshot.source_versions:
                raise MatchingCoordinationFactsAdapterError(
                    "matching_criteria_snapshot", "stale_willingness_source"
                )
            known_staff_id = lineage_staff.setdefault(item.candidate_id, item.staff_id)
            if known_staff_id != item.staff_id or (
                item.candidate_id in candidate_staff
                and candidate_staff[item.candidate_id] != item.staff_id
            ):
                raise MatchingCoordinationFactsAdapterError(
                    "candidate_pool", "ambiguous_willingness_identity"
                )
        required_dates = projection.orders_service_dates.current_dates
        candidates = tuple(
            _candidate_result(item, required_dates)
            for item in projection.candidate_pool.candidates
        )
        return MatchingCoordinationFacts(
            snapshot=projection.matching_criteria_snapshot,
            package=projection.matching_package,
            candidates=candidates,
            source_versions=projection.source_versions,
            criteria_snapshots=snapshots,
            willingness_lineage=willingness,
        )

    def load_initial(self, case_no: str) -> InitialCriteriaSourceFacts:
        """Read only the two owner sources needed before an M3 snapshot exists."""

        return self._load_initial_owner_facts(case_no, for_update=False)

    def _load_initial_owner_facts(
        self, case_no: str, *, for_update: bool
    ) -> InitialCriteriaSourceFacts:
        """Project the same two owner roots with optional borrowed locks."""

        if not isinstance(case_no, str) or not case_no.strip():
            raise TypeError("case number must be canonical text")
        case_no = case_no.strip()
        orders_terms = self._read(
            "orders_terms",
            lambda: self._ports["orders_terms"].load_order_terms(
                case_no, for_update=for_update
            ),
        )
        orders_dates = self._read(
            "orders_service_dates",
            lambda: self._ports["orders_service_dates"].load_service_dates(
                case_no, for_update=for_update
            ),
        )
        if not isinstance(orders_terms, OrderAggregateFacts):
            raise MatchingCoordinationFactsAdapterError("orders_terms", "partial")
        if not isinstance(orders_dates, ServiceDateConfirmationFacts):
            raise MatchingCoordinationFactsAdapterError(
                "orders_service_dates", "partial"
            )
        if orders_terms.case_no != case_no or orders_dates.case_no != case_no:
            raise MatchingCoordinationFactsAdapterError(
                "orders_service_dates", "ambiguous_identity"
            )
        source_versions = canonical_source_tuple(
            (
                self._version(
                    "orders_terms", lambda: orders_terms_source_version(orders_terms)
                ),
                self._version(
                    "orders_service_dates",
                    lambda: orders_service_dates_source_version(orders_dates),
                ),
                *(
                    MatchingSourceVersion.not_consulted(source_kind)
                    for source_kind in SOURCE_ORDER[2:]
                ),
            )
        )
        try:
            return InitialCriteriaSourceFacts(
                case_no, orders_terms, orders_dates, source_versions
            )
        except ValueError as exc:
            raise MatchingCoordinationFactsAdapterError(
                "orders_service_dates", "not_confirmed"
            ) from exc

    def load_initial_fresh(
        self, case_no: str, *, for_update: bool
    ) -> InitialCriteriaSourceFacts:
        """Require the composition-owned Orders lock path for initial Apply."""

        if for_update is not True:
            raise MatchingCoordinationFactsAdapterError(
                "owner_lock_set", "unavailable"
            )
        facts = (
            self._initial_fresh_loader(case_no)
            if self._initial_fresh_loader is not None
            else self._load_initial_owner_facts(case_no, for_update=True)
        )
        if not isinstance(facts, InitialCriteriaSourceFacts):
            raise MatchingCoordinationFactsAdapterError("owner_lock_set", "partial")
        return facts

    def load_fresh(
        self, case_no: str, *, for_update: bool
    ) -> MatchingCoordinationFacts:
        """Require an owner-locking composition for Apply; never fake freshness."""

        if for_update is not True:
            raise MatchingCoordinationFactsAdapterError(
                "owner_lock_set", "unavailable"
            )
        facts = (
            self._fresh_loader(case_no)
            if self._fresh_loader is not None
            else self.load(case_no, for_update=True)
        )
        if not isinstance(facts, MatchingCoordinationFacts):
            raise MatchingCoordinationFactsAdapterError(
                "owner_lock_set", "partial"
            )
        return facts


MatchingCoordinationFactsAdapter = MySqlMatchingCoordinationFactsAdapter


def _candidate_result(
    item: Any, required_service_dates: tuple[date, ...]
) -> MatchingCandidateResult:
    eligibility = (
        CandidateEligibility.INELIGIBLE
        if item.status == "withdrawn"
        else CandidateEligibility.ELIGIBLE
    )
    reasons: tuple[str, ...] = ()
    if item.willingness == "unwilling":
        reason = item.reason if item.reason in {value.value for value in StableRejectionReason} else StableRejectionReason.WILLINGNESS_UNCONFIRMED.value
        reasons = (reason,)
    return MatchingCandidateResult(
        candidate_id=str(item.id),
        staff_id=item.staff_id,
        eligibility=eligibility,
        criteria_results=(),
        rejection_reasons=reasons,
        coverage_evidence=tuple(
            day
            for day in required_service_dates
            if item.service_start_date <= day <= item.service_end_date
        ),
        willingness=item.willingness,
        staff_name=item.staff_name,
    )


__all__ = [
    "SOURCE_ORDER",
    "MatchingAvailabilityQueryAdapter",
    "MatchingCoordinationFactsAdapterError",
    "MatchingCoordinationFactsProjection",
    "MatchingEffectiveGenerationQueryAdapter",
    "MySqlMatchingCoordinationFactsAdapter",
    "MatchingCoordinationFactsAdapter",
]
