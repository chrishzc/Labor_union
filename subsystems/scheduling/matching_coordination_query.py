"""File: matching_coordination_query.py
Description: 提供 M3-B matching coordination 的唯讀 typed query result 與 facts port。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from domains.orders.terms import OrderAggregateFacts
from domains.scheduling.matching_coordination import (
    DynamicWillingnessLineage,
    MatchingCriteriaSnapshot,
    MatchingPackage,
    MatchingSourceVersion,
    MatchingSourceTuple,
    RefusalHistoryEntry,
)
from domains.scheduling.assignment_plan import (
    AssignmentPlanFacts,
    EffectiveAssignmentFact,
)
from domains.scheduling.staff_availability import (
    StaffAvailabilityFacts,
    StaffAvailabilityConflict,
    StaffUnavailabilityBlock,
)
from domains.scheduling.generation import (
    EffectiveAssignmentSegment,
    SchedulingGenerationFacts,
)
from domains.scheduling.staff_matching_preferences import (
    IntegerRangePreference,
    IntegerSetPreference,
    PreferenceValue,
    StaffPreferenceDefinition,
)
from domains.staff.retirement import (
    StaffLifecycleFact,
    StaffLifecycleState,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.validation import require_canonical_text
from subsystems.orders.service_date_confirmation_workflow import (
    ServiceDateConfirmationFacts,
)
from subsystems.scheduling.matching_coordination_contracts import (
    MatchingCandidateResultView,
    MatchingCriteriaSnapshotView,
    MatchingPackageView,
    QueryMatchingCoordination,
    candidate_view,
    package_view,
    snapshot_view,
)
from subsystems.scheduling.matching_coordination_workflow import (
    MatchingCoordinationFacts,
)
from subsystems.scheduling.candidate_contact_pool_workflow import (
    CandidateContactPoolState,
)
from subsystems.scheduling.matching_leave_integration import (
    CanonicalSchedulingLeaveReference,
)
from subsystems.scheduling.matching_assignment_conversion import (
    CanonicalAssignmentConversionReceipt,
)


class MatchingCoordinationFactsQueryPort(Protocol):
    def load(
        self, case_no: str, *, for_update: bool = False
    ) -> MatchingCoordinationFacts: ...


class MatchingCriteriaSnapshotQueryPort(Protocol):
    def load_current_snapshot(
        self, case_no: str, *, for_update: bool = False
    ) -> MatchingCriteriaSnapshot: ...

    def load_snapshot_history(
        self, case_no: str, *, for_update: bool = False
    ) -> tuple[MatchingCriteriaSnapshot, ...]: ...

    def load_willingness_history(
        self, case_no: str, *, for_update: bool = False
    ) -> tuple[DynamicWillingnessLineage, ...]: ...


class CandidatePoolQueryPort(Protocol):
    def load_candidate_pool(
        self, case_no: str, *, for_update: bool = False
    ) -> CandidateContactPoolState: ...


class MatchingPackageQueryPort(Protocol):
    def load_current_package(
        self, case_no: str, *, for_update: bool = False
    ) -> MatchingPackage | None: ...


class IncumbentAssignmentQueryPort(Protocol):
    def load_current_assignments(
        self, case_no: str, *, for_update: bool = False
    ) -> AssignmentPlanFacts: ...


class LeaveRequestOutcomeQueryPort(Protocol):
    def get_canonical_receipt(
        self, receipt_key: str
    ) -> CanonicalSchedulingLeaveReference | None: ...


class AssignmentConversionReferenceQueryPort(Protocol):
    def get_canonical_receipt(
        self, request_id: str
    ) -> CanonicalAssignmentConversionReceipt | None: ...


class OrdersTermsQueryPort(Protocol):
    def load_order_terms(
        self, case_no: str, *, for_update: bool = False
    ) -> OrderAggregateFacts: ...


class OrdersServiceDateQueryPort(Protocol):
    def load_service_dates(
        self, case_no: str, *, for_update: bool = False
    ) -> ServiceDateConfirmationFacts: ...


class SchedulingAvailabilityQueryPort(Protocol):
    def load_availability(
        self,
        case_no: str,
        staff_ids: tuple[int, ...],
        *,
        for_update: bool = False,
    ) -> tuple[StaffAvailabilityFacts, ...]: ...


class SchedulingEffectiveGenerationQueryPort(Protocol):
    def load_effective_generation(
        self, case_no: str, *, for_update: bool = False
    ) -> SchedulingGenerationFacts: ...


class StaffMatchingProfileQueryPort(Protocol):
    def load_definitions(
        self,
        *,
        for_update: bool = False,
    ) -> tuple[tuple[StaffPreferenceDefinition, int], ...]: ...

    def load_profile_values(
        self, staff_ids: tuple[int, ...], *, for_update: bool = False
    ) -> tuple["StaffProfileValuesFacts", ...]: ...


class StaffLifecycleQueryPort(Protocol):
    def load_lifecycle(
        self, staff_ids: tuple[int, ...], *, for_update: bool = False
    ) -> tuple[StaffLifecycleFact, ...]: ...


@dataclass(frozen=True, slots=True)
class StaffProfileValuesFacts:
    staff_id: int
    profile_version: int
    values: tuple[tuple[str, PreferenceValue], ...]

    def __post_init__(self) -> None:
        if isinstance(self.staff_id, bool) or not isinstance(self.staff_id, int):
            raise TypeError("staff profile staff id must be an integer")
        if self.staff_id <= 0:
            raise ValueError("staff profile staff id must be positive")
        if isinstance(self.profile_version, bool) or not isinstance(
            self.profile_version, int
        ):
            raise TypeError("staff profile version must be an integer")
        if self.profile_version < 0:
            raise ValueError("staff profile version must be nonnegative")
        if not isinstance(self.values, tuple):
            raise TypeError("staff profile values must be a typed tuple")
        keys: list[str] = []
        for item in self.values:
            if not isinstance(item, tuple) or len(item) != 2:
                raise TypeError("staff profile value pair must be typed")
            key, value = item
            require_canonical_text(key, "staff profile preference key", 64)
            if not isinstance(value, (IntegerRangePreference, IntegerSetPreference)):
                raise TypeError("staff profile preference value must be typed")
            keys.append(key)
        if tuple(keys) != tuple(sorted(set(keys))):
            raise ValueError("staff profile preference keys must be sorted and unique")


def orders_terms_source_version(
    facts: OrderAggregateFacts,
) -> MatchingSourceVersion:
    if not isinstance(facts, OrderAggregateFacts):
        raise TypeError("orders terms facts must be typed")
    fingerprint = fingerprint_payload(
        {
            "case_no": facts.case_no,
            "version": facts.version,
            "terms": facts.terms.canonical_payload(),
        }
    )
    return MatchingSourceVersion(
        source_kind="orders_terms",
        source_id=facts.case_no,
        version=facts.version,
        fingerprint=fingerprint,
    )


def matching_criteria_snapshot_source_version(
    snapshot: MatchingCriteriaSnapshot,
) -> MatchingSourceVersion:
    if not isinstance(snapshot, MatchingCriteriaSnapshot):
        raise TypeError("matching criteria snapshot must be typed")
    return MatchingSourceVersion(
        source_kind="matching_criteria_snapshot",
        source_id=snapshot.snapshot_id,
        version=snapshot.criteria_version,
        fingerprint=snapshot.fingerprint,
    )


def candidate_pool_source_version(
    state: CandidateContactPoolState,
) -> MatchingSourceVersion:
    if not isinstance(state, CandidateContactPoolState):
        raise TypeError("candidate pool state must be typed")
    candidate_ids = tuple(item.id for item in state.candidates)
    if candidate_ids != tuple(sorted(set(candidate_ids))):
        raise ValueError("candidate pool candidate ids must be sorted and unique")
    event_ids = tuple(item.id for item in state.events)
    if state.pool_id is None:
        if state.candidates or state.events:
            raise ValueError("empty candidate pool cannot contain state")
        version = "empty"
    else:
        version = fingerprint_payload(
            {
                "pool_id": state.pool_id,
                "candidates": [
                    {
                        "id": item.id,
                        "staff_id": item.staff_id,
                        "status": item.status,
                    }
                    for item in state.candidates
                ],
                "event_ids": list(event_ids),
            }
        ).value

    def _information_payload(item: object) -> dict[str, object] | None:
        if item is None:
            return None
        delivery = item
        return {
            "status": delivery.status,
            "sent_at": delivery.sent_at.isoformat(),
        }

    full_fingerprint = fingerprint_payload(
        {
            "case_no": state.case_no,
            "pool_id": state.pool_id,
            "candidates": [
                {
                    "id": item.id,
                    "staff_id": item.staff_id,
                    "staff_name": item.staff_name,
                    "service_start_date": item.service_start_date.isoformat(),
                    "service_end_date": item.service_end_date.isoformat(),
                    "status": item.status,
                    "created_at": item.created_at.isoformat(),
                    "willingness": item.willingness,
                    "reason": item.reason,
                    "information": {
                        "1": _information_payload(item.information.information_1),
                        "2": _information_payload(item.information.information_2),
                    },
                }
                for item in state.candidates
            ],
            "events": [
                {
                    "id": event.id,
                    "candidate_id": event.candidate_id,
                    "event_key": event.event_key,
                    "event_type": event.event_type,
                    "occurred_at": event.occurred_at.isoformat(),
                    "payload_fingerprint": event.payload_fingerprint,
                }
                for event in state.events
            ],
        }
    )
    return MatchingSourceVersion(
        source_kind="candidate_pool",
        source_id=state.case_no,
        version=version,
        fingerprint=full_fingerprint,
    )


def matching_package_source_version(
    package: MatchingPackage | None,
    *,
    case_no: str,
) -> MatchingSourceVersion:
    require_canonical_text(case_no, "case number", 50)
    if package is None:
        return MatchingSourceVersion(
            source_kind="matching_package",
            source_id=case_no,
            version="absent",
            fingerprint=fingerprint_payload(
                {"case_no": case_no, "state": "absent"}
            ),
        )
    if not isinstance(package, MatchingPackage):
        raise TypeError("matching package must be typed")
    if package.fingerprint is None:
        raise TypeError("matching package fingerprint is required")
    return MatchingSourceVersion(
        source_kind="matching_package",
        source_id=package.package_id,
        version=package.version,
        fingerprint=package.fingerprint,
    )


def incumbent_assignment_source_version(
    facts: AssignmentPlanFacts,
) -> MatchingSourceVersion:
    if not isinstance(facts, AssignmentPlanFacts):
        raise TypeError("incumbent assignment facts must be typed")
    require_canonical_text(facts.case_no, "case number", 50)
    if not isinstance(facts.effective_assignments, tuple) or any(
        not isinstance(item, EffectiveAssignmentFact)
        for item in facts.effective_assignments
    ):
        raise TypeError("incumbent assignments must be a typed tuple")
    assignment_ids = tuple(item.assignment_id for item in facts.effective_assignments)
    if assignment_ids != tuple(sorted(set(assignment_ids))):
        raise ValueError("incumbent assignment ids must be sorted and unique")
    sequences = tuple(item.sequence for item in facts.effective_assignments)
    if sequences != tuple(sorted(set(sequences))):
        raise ValueError("incumbent assignment sequences must be sorted and unique")
    if not facts.effective_assignments:
        version: int | str = "empty"
    else:
        version = fingerprint_payload(
            {
                "scheduling_version": facts.scheduling_version,
                "scheduling_generation": facts.scheduling_generation,
                "assignment_ids": assignment_ids,
                "staff_ids": tuple(item.staff_id for item in facts.effective_assignments),
                "sequences": sequences,
            }
        ).value
    fingerprint = fingerprint_payload(
        {
            "case_no": facts.case_no,
            "scheduling_version": facts.scheduling_version,
            "scheduling_generation": facts.scheduling_generation,
            "effective_assignments": tuple(
                {
                    "assignment_id": item.assignment_id,
                    "staff_id": item.staff_id,
                    "sequence": item.sequence,
                    "assigned_start_date": (
                        item.assigned_start_date.isoformat()
                        if item.assigned_start_date is not None
                        else None
                    ),
                    "assigned_end_date": (
                        item.assigned_end_date.isoformat()
                        if item.assigned_end_date is not None
                        else None
                    ),
                    "official_service_dates": tuple(
                        value.isoformat() for value in item.official_service_dates
                    ),
                }
                for item in facts.effective_assignments
            ),
        }
    )
    return MatchingSourceVersion(
        source_kind="incumbent_assignment",
        source_id=facts.case_no,
        version=version,
        fingerprint=fingerprint,
    )


def leave_request_or_outcome_source_version(
    reference: CanonicalSchedulingLeaveReference | None,
    *,
    case_no: str | None = None,
) -> MatchingSourceVersion:
    if reference is None:
        if case_no is None:
            raise ValueError("case number is required for absent leave reference")
        require_canonical_text(case_no, "case number", 50)
        return MatchingSourceVersion(
            source_kind="leave_request_or_outcome",
            source_id=case_no,
            version="absent",
            fingerprint=fingerprint_payload(
                {"case_no": case_no, "state": "absent"}
            ),
        )
    if not isinstance(reference, CanonicalSchedulingLeaveReference):
        raise TypeError("leave reference must be typed")
    if case_no is not None:
        require_canonical_text(case_no, "case number", 50)
        if reference.case_no != case_no:
            raise ValueError("leave reference case number mismatch")
    return MatchingSourceVersion(
        source_kind="leave_request_or_outcome",
        source_id=reference.receipt_key,
        version=reference.leave_version,
        fingerprint=reference.receipt_fingerprint,
    )


def assignment_conversion_reference_source_version(
    receipt: CanonicalAssignmentConversionReceipt | None,
    *,
    request_id: str | None = None,
) -> MatchingSourceVersion:
    if receipt is None:
        if request_id is None:
            raise ValueError("request ID is required for absent conversion receipt")
        require_canonical_text(request_id, "request ID", 191)
        return MatchingSourceVersion(
            source_kind="assignment_conversion_reference",
            source_id=request_id,
            version="absent",
            fingerprint=fingerprint_payload(
                {"request_id": request_id, "state": "absent"}
            ),
        )
    if not isinstance(receipt, CanonicalAssignmentConversionReceipt):
        raise TypeError("assignment conversion receipt must be typed")
    if request_id is not None:
        require_canonical_text(request_id, "request ID", 191)
        if receipt.request_id != request_id:
            raise ValueError("assignment conversion request ID mismatch")
    return MatchingSourceVersion(
        source_kind="assignment_conversion_reference",
        source_id=receipt.request_id,
        version=receipt.package_version,
        fingerprint=receipt.receipt_fingerprint,
    )


def orders_service_dates_source_version(
    facts: ServiceDateConfirmationFacts,
) -> MatchingSourceVersion:
    if not isinstance(facts, ServiceDateConfirmationFacts):
        raise TypeError("orders service date facts must be typed")
    require_canonical_text(facts.case_no, "case number", 50)
    if not isinstance(facts.current_dates, tuple):
        raise TypeError("current service dates must be a tuple")
    if any(type(value) is not date for value in facts.current_dates):
        raise TypeError("current service dates must contain date values")
    if facts.current_dates != tuple(sorted(set(facts.current_dates))):
        raise ValueError("current service dates must be unique and sorted")
    if facts.current_version is not None and (
        isinstance(facts.current_version, bool)
        or not isinstance(facts.current_version, int)
    ):
        raise TypeError("current service date version must be an integer or None")
    version: int | str = (
        facts.current_version
        if facts.current_version is not None
        else "unconfirmed"
    )
    fingerprint = fingerprint_payload(
        {
            "case_no": facts.case_no,
            "confirmed_version": version,
            "service_dates": [value.isoformat() for value in facts.current_dates],
            "order_version": facts.order_version,
            "scheduling_version": facts.scheduling_version,
        }
    )
    return MatchingSourceVersion(
        source_kind="orders_service_dates",
        source_id=facts.case_no,
        version=version,
        fingerprint=fingerprint,
    )


def scheduling_availability_source_version(
    case_no: str,
    facts: tuple[StaffAvailabilityFacts, ...],
) -> MatchingSourceVersion:
    require_canonical_text(case_no, "case number", 50)
    if not isinstance(facts, tuple) or any(
        not isinstance(item, StaffAvailabilityFacts) for item in facts
    ):
        raise TypeError("scheduling availability facts must be a typed tuple")
    staff_ids = tuple(item.staff_id for item in facts)
    if staff_ids != tuple(sorted(set(staff_ids))):
        raise ValueError("scheduling availability staff ids must be sorted and unique")

    staff_payload: list[dict[str, object]] = []
    version_vector = tuple(
        (item.staff_id, item.aggregate_version) for item in facts
    )
    for item in facts:
        if item.target_block is not None:
            raise ValueError("scheduling availability target block must be absent")
        if not isinstance(item.blocks, tuple) or any(
            not isinstance(block, StaffUnavailabilityBlock)
            for block in item.blocks
        ):
            raise TypeError("scheduling availability blocks must be typed tuples")
        block_ids = tuple(block.block_id for block in item.blocks)
        if block_ids != tuple(sorted(set(block_ids))):
            raise ValueError("scheduling availability blocks must be sorted and unique")
        if not isinstance(item.conflicts, tuple) or any(
            not isinstance(conflict, StaffAvailabilityConflict)
            for conflict in item.conflicts
        ):
            raise TypeError("scheduling availability conflicts must be typed tuples")
        conflict_keys = tuple(
            (
                conflict.source_kind,
                conflict.source_identity,
                conflict.start_date,
                conflict.end_date,
            )
            for conflict in item.conflicts
        )
        if conflict_keys != tuple(sorted(set(conflict_keys))):
            raise ValueError(
                "scheduling availability conflicts must be sorted and unique"
            )
        staff_payload.append(
            {
                "staff_id": item.staff_id,
                "aggregate_version": item.aggregate_version,
                "blocks": tuple(
                    {
                        "block_id": block.block_id,
                        "kind": block.kind.value,
                        "start_date": block.start_date.isoformat(),
                        "end_date": (
                            block.end_date.isoformat()
                            if block.end_date is not None
                            else None
                        ),
                        "status": block.status.value,
                        "reason": block.reason,
                    }
                    for block in item.blocks
                ),
                "conflicts": tuple(
                    {
                        "source_kind": conflict.source_kind,
                        "source_identity": conflict.source_identity,
                        "start_date": conflict.start_date.isoformat(),
                        "end_date": conflict.end_date.isoformat(),
                    }
                    for conflict in item.conflicts
                ),
            }
        )
    version = fingerprint_payload({"staff_versions": version_vector}).value
    fingerprint = fingerprint_payload(
        {
            "case_no": case_no,
            "version": version,
            "staff_versions": version_vector,
            "staff_facts": tuple(staff_payload),
        }
    ).value
    return MatchingSourceVersion(
        source_kind="scheduling_availability",
        source_id=case_no,
        version=version,
        fingerprint=fingerprint,
    )


def scheduling_effective_generation_source_version(
    facts: SchedulingGenerationFacts,
) -> MatchingSourceVersion:
    if not isinstance(facts, SchedulingGenerationFacts):
        raise TypeError("scheduling generation facts must be typed")
    if not isinstance(facts.segments, tuple) or any(
        not isinstance(segment, EffectiveAssignmentSegment)
        for segment in facts.segments
    ):
        raise TypeError("scheduling generation segments must be a typed tuple")
    sequences = tuple(segment.sequence for segment in facts.segments)
    if sequences != tuple(sorted(set(sequences))):
        raise ValueError("scheduling generation sequences must be sorted and unique")
    assignment_ids = tuple(segment.assignment_id for segment in facts.segments)
    if len(assignment_ids) != len(set(assignment_ids)):
        raise ValueError("scheduling generation assignment ids must be unique")
    segments = tuple(
        {
            "assignment_id": segment.assignment_id,
            "staff_id": segment.staff_id,
            "sequence": segment.sequence,
            "service_day_count": segment.service_day_count,
            "assigned_start_date": segment.assigned_start_date.isoformat(),
            "assigned_end_date": segment.assigned_end_date.isoformat(),
            "official_service_dates": tuple(
                value.isoformat() for value in segment.official_service_dates
            ),
        }
        for segment in facts.segments
    )
    fingerprint = fingerprint_payload(
        {
            "case_no": facts.case_no,
            "aggregate_version": facts.aggregate_version,
            "generation_number": facts.generation_number,
            "service_started": facts.service_started,
            "segments": segments,
        }
    ).value
    return MatchingSourceVersion(
        source_kind="scheduling_effective_generation",
        source_id=facts.case_no,
        version=facts.aggregate_version,
        fingerprint=fingerprint,
    )


def staff_profile_definition_source_version(
    definitions: tuple[tuple[StaffPreferenceDefinition, int], ...],
) -> MatchingSourceVersion:
    if not isinstance(definitions, tuple):
        raise TypeError("staff profile definitions must be a typed tuple")
    keys: list[str] = []
    versions: list[int] = []
    full_definitions: list[dict[str, object]] = []
    for item in definitions:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError("staff profile definition pair must be typed")
        definition, version = item
        if not isinstance(definition, StaffPreferenceDefinition):
            raise TypeError("staff profile definition must be typed")
        if not definition.active:
            raise ValueError("staff profile definitions must be active")
        if isinstance(version, bool) or not isinstance(version, int):
            raise TypeError("staff profile definition version must be an integer")
        if version < 0:
            raise ValueError("staff profile definition version must be nonnegative")
        keys.append(definition.preference_key)
        versions.append(version)
        full_definitions.append(
            {
                "preference_key": definition.preference_key,
                "version": version,
                "definition": definition.canonical_payload(),
            }
        )
    if tuple(keys) != tuple(sorted(set(keys))):
        raise ValueError("staff profile definition keys must be sorted and unique")
    version = fingerprint_payload(
        {"keys": tuple(keys), "versions": tuple(versions)}
    ).value
    fingerprint = fingerprint_payload(
        {"definitions": tuple(full_definitions)}
    ).value
    return MatchingSourceVersion(
        source_kind="staff_profile_definition",
        source_id="active_definitions",
        version=version,
        fingerprint=fingerprint,
    )


def staff_profile_values_source_version(
    case_no: str,
    facts: tuple[StaffProfileValuesFacts, ...],
) -> MatchingSourceVersion:
    require_canonical_text(case_no, "case number", 50)
    if not isinstance(facts, tuple) or any(
        not isinstance(item, StaffProfileValuesFacts) for item in facts
    ):
        raise TypeError("staff profile values facts must be a typed tuple")
    staff_ids = tuple(item.staff_id for item in facts)
    if staff_ids != tuple(sorted(set(staff_ids))):
        raise ValueError("staff profile value staff ids must be sorted and unique")
    version_vector = tuple(
        (item.staff_id, item.profile_version) for item in facts
    )
    version = fingerprint_payload({"staff_versions": version_vector}).value
    staff_values = tuple(
        {
            "staff_id": item.staff_id,
            "profile_version": item.profile_version,
            "values": tuple(
                {
                    "preference_key": key,
                    "value": value.canonical_payload(),
                }
                for key, value in item.values
            ),
        }
        for item in facts
    )
    fingerprint = fingerprint_payload(
        {
            "case_no": case_no,
            "staff_versions": version_vector,
            "staff_values": staff_values,
        }
    ).value
    return MatchingSourceVersion(
        source_kind="staff_profile_values",
        source_id=case_no,
        version=version,
        fingerprint=fingerprint,
    )


def staff_lifecycle_source_version(
    case_no: str,
    facts: tuple[StaffLifecycleFact, ...],
) -> MatchingSourceVersion:
    require_canonical_text(case_no, "case number", 50)
    if not isinstance(facts, tuple) or any(
        not isinstance(item, StaffLifecycleFact) for item in facts
    ):
        raise TypeError("staff lifecycle facts must be a typed tuple")
    staff_ids = tuple(item.staff_id for item in facts)
    if staff_ids != tuple(sorted(set(staff_ids))):
        raise ValueError("staff lifecycle staff ids must be sorted and unique")
    version_vector = tuple((item.staff_id, item.version) for item in facts)
    version = fingerprint_payload({"staff_versions": version_vector}).value
    staff_states = tuple(
        {
            "staff_id": item.staff_id,
            "state": item.state.value,
            "version": item.version,
            "effective_at": (
                item.effective_at.isoformat()
                if item.effective_at is not None
                else None
            ),
            "reason_code": item.reason_code,
        }
        for item in facts
    )
    fingerprint = fingerprint_payload(
        {
            "case_no": case_no,
            "staff_states": staff_states,
        }
    ).value
    return MatchingSourceVersion(
        source_kind="staff_lifecycle",
        source_id=case_no,
        version=version,
        fingerprint=fingerprint,
    )


class MatchingCoordinationQuery:
    def __init__(self, port: MatchingCoordinationFactsQueryPort) -> None:
        self._port = port

    def execute(
        self, command: QueryMatchingCoordination
    ) -> "MatchingCoordinationQueryResult":
        if not isinstance(command, QueryMatchingCoordination):
            raise TypeError("matching coordination query command is invalid")
        facts = self._port.load(command.case_no)
        if not isinstance(facts, MatchingCoordinationFacts):
            raise TypeError("matching coordination facts are invalid")
        if facts.snapshot.case_no != command.case_no:
            raise ValueError("matching coordination facts/case number mismatch")
        return MatchingCoordinationQueryResult(
            case_no=command.case_no,
            snapshot=snapshot_view(facts.snapshot),
            package=package_view(facts.package) if facts.package is not None else None,
            candidates=tuple(
                candidate_view(item)
                for item in sorted(
                    facts.candidates,
                    key=lambda item: (
                        not bool(item.staff_name),
                        item.staff_name.casefold(),
                        item.staff_id,
                        item.candidate_id,
                    ),
                )
            ),
            source_versions=facts.source_versions,
            refusal_history=facts.refusal_history,
            willingness_lineage=facts.willingness_lineage,
            expected_source_versions_match=(
                command.expected_source_versions is None
                or command.expected_source_versions == facts.source_versions
            ),
        )


@dataclass(frozen=True, slots=True)
class MatchingCoordinationQueryResult:
    case_no: str
    snapshot: MatchingCriteriaSnapshotView
    package: MatchingPackageView | None
    candidates: tuple[MatchingCandidateResultView, ...]
    source_versions: MatchingSourceTuple
    refusal_history: tuple[RefusalHistoryEntry, ...]
    willingness_lineage: tuple[DynamicWillingnessLineage, ...]
    expected_source_versions_match: bool

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        if not isinstance(self.snapshot, MatchingCriteriaSnapshotView):
            raise TypeError("matching query snapshot must be typed")
        if self.snapshot.case_no != self.case_no:
            raise ValueError("matching query snapshot/case number mismatch")
        if self.package is not None:
            if not isinstance(self.package, MatchingPackageView):
                raise TypeError("matching query package must be typed")
        if not isinstance(self.candidates, tuple) or any(
            not isinstance(item, MatchingCandidateResultView)
            for item in self.candidates
        ):
            raise TypeError("matching query candidates must be a typed tuple")
        if not isinstance(self.refusal_history, tuple) or any(
            not isinstance(item, RefusalHistoryEntry) for item in self.refusal_history
        ):
            raise TypeError("matching query refusal history must be a typed tuple")
        if not isinstance(self.willingness_lineage, tuple) or any(
            not isinstance(item, DynamicWillingnessLineage)
            for item in self.willingness_lineage
        ):
            raise TypeError("matching query willingness lineage must be a typed tuple")
        if not isinstance(self.source_versions, tuple):
            raise TypeError("matching query source versions must be a tuple")
        if not isinstance(self.expected_source_versions_match, bool):
            raise TypeError("matching query source match flag must be bool")


__all__ = [
    "MatchingCoordinationFactsQueryPort",
    "MatchingCriteriaSnapshotQueryPort",
    "CandidatePoolQueryPort",
    "MatchingPackageQueryPort",
    "IncumbentAssignmentQueryPort",
    "LeaveRequestOutcomeQueryPort",
    "AssignmentConversionReferenceQueryPort",
    "MatchingCoordinationQuery",
    "MatchingCoordinationQueryResult",
    "OrdersTermsQueryPort",
    "OrdersServiceDateQueryPort",
    "SchedulingAvailabilityQueryPort",
    "SchedulingEffectiveGenerationQueryPort",
    "StaffMatchingProfileQueryPort",
    "StaffProfileValuesFacts",
    "StaffLifecycleQueryPort",
    "staff_profile_definition_source_version",
    "staff_profile_values_source_version",
    "staff_lifecycle_source_version",
    "scheduling_effective_generation_source_version",
    "scheduling_availability_source_version",
    "orders_service_dates_source_version",
    "orders_terms_source_version",
    "matching_criteria_snapshot_source_version",
    "candidate_pool_source_version",
    "matching_package_source_version",
    "incumbent_assignment_source_version",
    "leave_request_or_outcome_source_version",
    "assignment_conversion_reference_source_version",
]
