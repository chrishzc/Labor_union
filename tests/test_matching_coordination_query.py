"""File: test_matching_coordination_query.py
Description: 驗證 M3-B matching coordination query 的 typed projection 與 source freshness flag。
"""

from datetime import date, datetime, time, timezone

import pytest

from domains.scheduling.matching_coordination import (
    MatchingPackage,
    MatchingPackageMode,
    MatchingPackageState,
    MatchingSegment,
    MatchingSourceVersion,
    SOURCE_KINDS,
    build_criteria_snapshot,
)
from domains.scheduling.assignment_plan import (
    AssignmentPlanFacts,
    EffectiveAssignmentFact,
)
from domains.scheduling.leave_substitution import LeaveResolutionType
from domains.scheduling.staff_availability import (
    StaffAvailabilityConflict,
    StaffAvailabilityFacts,
    StaffAvailabilityBlockStatus,
    StaffUnavailabilityBlock,
    StaffUnavailabilityKind,
)
from domains.scheduling.generation import (
    EffectiveAssignmentSegment,
    SchedulingGenerationFacts,
)
from domains.scheduling.staff_matching_preferences import (
    IntegerRangePreference,
    IntegerSetPreference,
    PreferenceComparisonOperator,
    PreferenceValueKind,
    StaffPreferenceDefinition,
)
from domains.staff.retirement import StaffLifecycleFact, StaffLifecycleState
from domains.orders.terms import OrderAggregateFacts, OrderTerms, ServiceTimeTerms
from shared_kernel.money import MoneyNTD
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.scheduling.matching_coordination_contracts import (
    MatchingCriteriaSnapshotView,
    QueryMatchingCoordination,
)
from subsystems.scheduling.matching_coordination_query import (
    CandidatePoolQueryPort,
    MatchingCoordinationQuery,
    MatchingCoordinationQueryResult,
    IncumbentAssignmentQueryPort,
    LeaveRequestOutcomeQueryPort,
    AssignmentConversionReferenceQueryPort,
    candidate_pool_source_version,
    orders_service_dates_source_version,
    orders_terms_source_version,
    scheduling_availability_source_version,
    scheduling_effective_generation_source_version,
    staff_profile_definition_source_version,
    StaffProfileValuesFacts,
    staff_profile_values_source_version,
    staff_lifecycle_source_version,
    matching_criteria_snapshot_source_version,
    incumbent_assignment_source_version,
    leave_request_or_outcome_source_version,
    assignment_conversion_reference_source_version,
    matching_package_source_version,
)
from subsystems.scheduling.candidate_contact_pool_workflow import (
    CandidateContactEntryState,
    CandidateContactEventState,
    CandidateContactPoolState,
    CandidateInformationDelivery,
    CandidateInformationState,
)
from subsystems.scheduling.matching_leave_integration import (
    CanonicalSchedulingLeaveReference,
)
from subsystems.scheduling.matching_assignment_conversion import (
    AssignmentConversionResultState,
    CanonicalAssignmentConversionReceipt,
)
from domains.scheduling.matching_coordination import MatchingCriteriaSnapshot
from subsystems.orders.service_date_confirmation_workflow import (
    ServiceDateConfirmationFacts,
)
from subsystems.scheduling.matching_coordination_workflow import MatchingCoordinationFacts


def _sources(seed: str = "a") -> tuple[MatchingSourceVersion, ...]:
    return tuple(
        MatchingSourceVersion(kind, f"{kind}:1", 1, seed * 64)
        for kind in SOURCE_KINDS
    )


def _snapshot(case_no: str, sources: tuple[MatchingSourceVersion, ...]):
    return build_criteria_snapshot(
        snapshot_id=f"snapshot:{case_no}",
        case_no=case_no,
        criteria_version=1,
        criteria={"service_days": 2},
        source_versions=sources,
        created_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
    )


def _command(case_no: str, sources: tuple[MatchingSourceVersion, ...]):
    return QueryMatchingCoordination(
        case_no=case_no,
        actor=ActorContext("admin_user_id:1"),
        correlation_id=CorrelationId("corr-matching-query-1"),
        expected_source_versions=sources,
    )


class _FakePort:
    def __init__(self, facts: MatchingCoordinationFacts) -> None:
        self._facts = facts
        self.loaded_case_nos: list[str] = []
        self.call_count = 0

    def load(self, case_no: str) -> MatchingCoordinationFacts:
        self.loaded_case_nos.append(case_no)
        self.call_count += 1
        return self._facts

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"unexpected port attribute access: {name}")


def test_execute_returns_typed_result_and_loads_once() -> None:
    sources = _sources()
    facts = MatchingCoordinationFacts(
        snapshot=_snapshot("CASE-001", sources),
        package=None,
        candidates=(),
        source_versions=sources,
        refusal_history=(),
        willingness_lineage=(),
    )
    port = _FakePort(facts)

    result = MatchingCoordinationQuery(port).execute(_command("CASE-001", sources))

    assert isinstance(result, MatchingCoordinationQueryResult)
    assert isinstance(result.snapshot, MatchingCriteriaSnapshotView)
    assert result.package is None
    assert isinstance(result.candidates, tuple)
    assert not isinstance(result.candidates, dict)
    assert result.candidates == ()
    assert result.source_versions == sources
    assert result.expected_source_versions_match is True
    assert port.loaded_case_nos == ["CASE-001"]
    assert port.call_count == 1


def test_execute_preserves_current_sources_and_marks_expected_mismatch() -> None:
    current_sources = _sources("a")
    expected_sources = (
        MatchingSourceVersion(SOURCE_KINDS[0], f"{SOURCE_KINDS[0]}:2", 2, "b" * 64),
        *current_sources[1:],
    )
    facts = MatchingCoordinationFacts(
        snapshot=_snapshot("CASE-001", current_sources),
        package=None,
        candidates=(),
        source_versions=current_sources,
        refusal_history=(),
        willingness_lineage=(),
    )
    port = _FakePort(facts)

    result = MatchingCoordinationQuery(port).execute(
        _command("CASE-001", expected_sources)
    )

    assert result.source_versions == current_sources
    assert result.source_versions != expected_sources
    assert result.expected_source_versions_match is False
    assert facts.source_versions == current_sources
    assert port.call_count == 1


def test_execute_rejects_facts_for_a_different_case_after_one_load() -> None:
    sources = _sources()
    facts = MatchingCoordinationFacts(
        snapshot=_snapshot("CASE-OTHER", sources),
        package=None,
        candidates=(),
        source_versions=sources,
        refusal_history=(),
        willingness_lineage=(),
    )
    port = _FakePort(facts)

    with pytest.raises(ValueError, match="case number mismatch"):
        MatchingCoordinationQuery(port).execute(_command("CASE-001", sources))

    assert port.loaded_case_nos == ["CASE-001"]
    assert port.call_count == 1


def _orders_terms_facts(*, version: int = 3, service_days: int = 2) -> OrderAggregateFacts:
    return OrderAggregateFacts(
        case_no="CASE-001",
        version=version,
        terms=OrderTerms(
            planned_start_date=date(2026, 9, 1),
            service_days=service_days,
            service_hours_per_day=8,
            floor_fee=MoneyNTD(1000),
            service_time=ServiceTimeTerms(time(8), time(16), 0),
        ),
        service_data_locked=False,
        client_identity_status="verified",
    )


def test_orders_terms_source_version_is_typed_and_deterministic() -> None:
    facts = _orders_terms_facts()

    source = orders_terms_source_version(facts)
    repeat = orders_terms_source_version(facts)

    assert source.source_kind == "orders_terms"
    assert source.source_id == "CASE-001"
    assert source.version == 3
    assert isinstance(source.fingerprint, str)
    assert len(source.fingerprint) == 64
    assert source == repeat
    assert source.fingerprint == source.fingerprint.lower()

    assert source.fingerprint != orders_terms_source_version(
        _orders_terms_facts(version=4)
    ).fingerprint
    assert source.fingerprint != orders_terms_source_version(
        _orders_terms_facts(service_days=3)
    ).fingerprint


def test_orders_terms_source_version_rejects_untyped_facts() -> None:
    with pytest.raises(TypeError, match="orders terms facts must be typed"):
        orders_terms_source_version(object())


def _service_date_facts(
    *,
    current_version: int | None = 4,
    current_dates: tuple[date, ...] = (date(2026, 9, 1), date(2026, 9, 3)),
    order_version: int = 7,
) -> ServiceDateConfirmationFacts:
    return ServiceDateConfirmationFacts(
        case_no="CASE-001",
        order_version=order_version,
        scheduling_version=8,
        contracted_service_days=2,
        suggested_dates=current_dates,
        selectable_dates=current_dates,
        current_version=current_version,
        current_dates=current_dates,
    )


def test_orders_service_dates_source_version_is_typed_and_deterministic() -> None:
    facts = _service_date_facts()

    source = orders_service_dates_source_version(facts)
    repeat = orders_service_dates_source_version(facts)

    assert source.source_kind == "orders_service_dates"
    assert source.source_id == "CASE-001"
    assert source.version == 4
    assert len(source.fingerprint) == 64
    assert source == repeat
    assert source.fingerprint != orders_service_dates_source_version(
        _service_date_facts(current_dates=(date(2026, 9, 1), date(2026, 9, 4)))
    ).fingerprint
    assert source.fingerprint != orders_service_dates_source_version(
        _service_date_facts(current_version=5)
    ).fingerprint


def test_orders_service_dates_source_version_handles_unconfirmed_and_rejects_invalid() -> None:
    source = orders_service_dates_source_version(
        _service_date_facts(current_version=None, current_dates=())
    )
    assert source.version == "unconfirmed"

    with pytest.raises(ValueError, match="unique and sorted"):
        orders_service_dates_source_version(
            _service_date_facts(current_dates=(date(2026, 9, 2), date(2026, 9, 1)))
        )
    with pytest.raises(ValueError, match="unique and sorted"):
        orders_service_dates_source_version(
            _service_date_facts(current_dates=(date(2026, 9, 1), date(2026, 9, 1)))
        )
    with pytest.raises(TypeError, match="date values"):
        orders_service_dates_source_version(
            _service_date_facts(current_dates=("2026-09-01",))  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="typed"):
        orders_service_dates_source_version(object())


def _availability_facts(
    *,
    staff_one_version: int = 2,
    block_reason: str = "annual leave",
    target_block: StaffUnavailabilityBlock | None = None,
) -> tuple[StaffAvailabilityFacts, ...]:
    return (
        StaffAvailabilityFacts(
            staff_id=7,
            aggregate_version=staff_one_version,
            blocks=(
                StaffUnavailabilityBlock(
                    block_id=101,
                    staff_id=7,
                    kind=StaffUnavailabilityKind.LONG_LEAVE,
                    start_date=date(2026, 9, 10),
                    end_date=date(2026, 9, 12),
                    status=StaffAvailabilityBlockStatus.EFFECTIVE,
                    reason=block_reason,
                ),
            ),
            conflicts=(
                StaffAvailabilityConflict(
                    source_kind="assignment",
                    source_identity="case:001",
                    start_date=date(2026, 9, 15),
                    end_date=date(2026, 9, 16),
                ),
            ),
            target_block=target_block,
        ),
        StaffAvailabilityFacts(
            staff_id=9,
            aggregate_version=3,
            blocks=(),
            conflicts=(),
        ),
    )


def test_scheduling_availability_source_version_is_exact_and_deterministic() -> None:
    facts = _availability_facts()

    source = scheduling_availability_source_version("CASE-001", facts)
    repeat = scheduling_availability_source_version("CASE-001", facts)

    assert source.source_kind == "scheduling_availability"
    assert source.source_id == "CASE-001"
    assert len(source.version) == 64
    assert len(source.fingerprint) == 64
    assert source == repeat
    assert source.fingerprint != scheduling_availability_source_version(
        "CASE-001", _availability_facts(block_reason="medical leave")
    ).fingerprint
    assert source.fingerprint != scheduling_availability_source_version(
        "CASE-001", _availability_facts(staff_one_version=4)
    ).fingerprint


def test_scheduling_availability_source_version_rejects_noncanonical_facts() -> None:
    facts = _availability_facts()

    with pytest.raises(ValueError, match="staff ids must be sorted"):
        scheduling_availability_source_version("CASE-001", facts[::-1])
    with pytest.raises(ValueError, match="blocks must be sorted and unique"):
        scheduling_availability_source_version(
            "CASE-001", (
                StaffAvailabilityFacts(
                    staff_id=7,
                    aggregate_version=2,
                    blocks=facts[0].blocks + facts[0].blocks,
                    conflicts=facts[0].conflicts,
                ),
                facts[1],
            )
        )
    with pytest.raises(ValueError, match="target block"):
        scheduling_availability_source_version(
            "CASE-001", _availability_facts(target_block=facts[0].blocks[0])
        )
    with pytest.raises(TypeError, match="typed tuple"):
        scheduling_availability_source_version("CASE-001", (object(),))


def _generation_facts(
    *,
    generation_number: int = 3,
    second_date: date = date(2026, 9, 3),
) -> SchedulingGenerationFacts:
    return SchedulingGenerationFacts(
        case_no="CASE-001",
        aggregate_version=6,
        generation_number=generation_number,
        segments=(
            EffectiveAssignmentSegment(
                assignment_id=201,
                staff_id=7,
                sequence=1,
                service_day_count=2,
                assigned_start_date=date(2026, 9, 1),
                assigned_end_date=date(2026, 9, 2),
                official_service_dates=(date(2026, 9, 1), date(2026, 9, 2)),
            ),
            EffectiveAssignmentSegment(
                assignment_id=202,
                staff_id=8,
                sequence=2,
                service_day_count=1,
                assigned_start_date=second_date,
                assigned_end_date=second_date,
                official_service_dates=(second_date,),
            ),
        ),
        service_started=False,
    )


def test_scheduling_effective_generation_source_version_is_exact_and_deterministic() -> None:
    facts = _generation_facts()

    source = scheduling_effective_generation_source_version(facts)
    repeat = scheduling_effective_generation_source_version(facts)

    assert source.source_kind == "scheduling_effective_generation"
    assert source.source_id == "CASE-001"
    assert source.version == 6
    assert len(source.fingerprint) == 64
    assert source == repeat
    assert source.fingerprint != scheduling_effective_generation_source_version(
        _generation_facts(generation_number=4)
    ).fingerprint
    assert source.fingerprint != scheduling_effective_generation_source_version(
        _generation_facts(second_date=date(2026, 9, 4))
    ).fingerprint


def test_scheduling_effective_generation_source_version_rejects_noncanonical_facts() -> None:
    facts = _generation_facts()

    with pytest.raises(ValueError, match="sequences must be sorted"):
        scheduling_effective_generation_source_version(
            SchedulingGenerationFacts(
                facts.case_no,
                facts.aggregate_version,
                facts.generation_number,
                facts.segments[::-1],
                facts.service_started,
            )
        )
    with pytest.raises(ValueError, match="assignment ids must be unique"):
        scheduling_effective_generation_source_version(
            SchedulingGenerationFacts(
                facts.case_no,
                facts.aggregate_version,
                facts.generation_number,
                (
                    facts.segments[0],
                    EffectiveAssignmentSegment(
                        assignment_id=201,
                        staff_id=8,
                        sequence=2,
                        service_day_count=1,
                        assigned_start_date=date(2026, 9, 3),
                        assigned_end_date=date(2026, 9, 3),
                        official_service_dates=(date(2026, 9, 3),),
                    ),
                ),
                facts.service_started,
            )
        )
    with pytest.raises(TypeError, match="typed"):
        scheduling_effective_generation_source_version(object())


def _profile_definitions(
    *,
    first_version: int = 2,
    first_name: str = "服務天數",
) -> tuple[tuple[StaffPreferenceDefinition, int], ...]:
    return (
        (
            StaffPreferenceDefinition(
                preference_key="service_days",
                display_name=first_name,
                value_kind=PreferenceValueKind.INTEGER_RANGE,
                is_filterable=True,
                order_fact_key="service_days",
                comparison_operator=PreferenceComparisonOperator.RANGE_WITH_TOLERANCE,
            ),
            first_version,
        ),
        (
            StaffPreferenceDefinition(
                preference_key="service_hours_per_day",
                display_name="每日服務時數",
                value_kind=PreferenceValueKind.INTEGER_SET,
                is_filterable=True,
                order_fact_key="service_hours_per_day",
                comparison_operator=PreferenceComparisonOperator.CONTAINS_INTEGER,
            ),
            3,
        ),
    )


def test_staff_profile_definition_source_version_is_exact_and_deterministic() -> None:
    definitions = _profile_definitions()

    source = staff_profile_definition_source_version(definitions)
    repeat = staff_profile_definition_source_version(definitions)

    assert source.source_kind == "staff_profile_definition"
    assert source.source_id == "active_definitions"
    assert len(source.version) == 64
    assert len(source.fingerprint) == 64
    assert source == repeat
    assert source.fingerprint != staff_profile_definition_source_version(
        _profile_definitions(first_version=4)
    ).fingerprint
    assert source.fingerprint != staff_profile_definition_source_version(
        _profile_definitions(first_name="可承接服務天數")
    ).fingerprint


def test_staff_profile_definition_source_version_rejects_noncanonical_definitions() -> None:
    definitions = _profile_definitions()

    with pytest.raises(ValueError, match="sorted and unique"):
        staff_profile_definition_source_version(definitions[::-1])
    with pytest.raises(ValueError, match="sorted and unique"):
        staff_profile_definition_source_version(
            (definitions[0], definitions[0])
        )
    with pytest.raises(ValueError, match="must be active"):
        staff_profile_definition_source_version(
            (
                (
                    StaffPreferenceDefinition(
                        preference_key="inactive_definition",
                        display_name="停用定義",
                        value_kind=PreferenceValueKind.INTEGER_SET,
                        is_filterable=False,
                        order_fact_key=None,
                        comparison_operator=None,
                        active=False,
                    ),
                    1,
                ),
            )
        )
    with pytest.raises(TypeError, match="typed"):
        staff_profile_definition_source_version(object())


def _profile_values(
    *,
    first_version: int = 4,
    first_minimum: int = 2,
) -> tuple[StaffProfileValuesFacts, ...]:
    return (
        StaffProfileValuesFacts(
            staff_id=7,
            profile_version=first_version,
            values=(
                ("service_days", IntegerRangePreference(first_minimum, 5)),
            ),
        ),
        StaffProfileValuesFacts(
            staff_id=9,
            profile_version=5,
            values=(
                ("service_hours_per_day", IntegerSetPreference((4, 8))),
            ),
        ),
    )


def test_staff_profile_values_source_version_is_exact_and_deterministic() -> None:
    facts = _profile_values()

    source = staff_profile_values_source_version("CASE-001", facts)
    repeat = staff_profile_values_source_version("CASE-001", facts)

    assert source.source_kind == "staff_profile_values"
    assert source.source_id == "CASE-001"
    assert len(source.version) == 64
    assert len(source.fingerprint) == 64
    assert source == repeat
    assert source.fingerprint != staff_profile_values_source_version(
        "CASE-001", _profile_values(first_version=6)
    ).fingerprint
    assert source.fingerprint != staff_profile_values_source_version(
        "CASE-001", _profile_values(first_minimum=3)
    ).fingerprint


def test_staff_profile_values_source_version_rejects_noncanonical_facts() -> None:
    facts = _profile_values()

    with pytest.raises(ValueError, match="staff ids must be sorted"):
        staff_profile_values_source_version("CASE-001", facts[::-1])
    with pytest.raises(ValueError, match="staff ids must be sorted and unique"):
        staff_profile_values_source_version("CASE-001", (facts[0], facts[0]))
    with pytest.raises(ValueError, match="preference keys"):
        StaffProfileValuesFacts(
            staff_id=7,
            profile_version=1,
            values=(
                ("z_value", IntegerSetPreference((1,))),
                ("a_value", IntegerSetPreference((2,))),
            ),
        )
    with pytest.raises(TypeError, match="preference value must be typed"):
        StaffProfileValuesFacts(
            staff_id=7,
            profile_version=1,
            values=(("service_days", object()),),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="typed tuple"):
        staff_profile_values_source_version("CASE-001", (object(),))


def _lifecycle_facts(
    *,
    retired_version: int = 3,
    reason_code: str | None = "left_union",
) -> tuple[StaffLifecycleFact, ...]:
    return (
        StaffLifecycleFact(
            staff_id=7,
            state=StaffLifecycleState.ACTIVE,
            version=2,
        ),
        StaffLifecycleFact(
            staff_id=9,
            state=StaffLifecycleState.RETIRED,
            version=retired_version,
            effective_at=datetime(2026, 8, 20, 10, tzinfo=timezone.utc),
            reason_code=reason_code,
        ),
    )


def test_staff_lifecycle_source_version_is_exact_and_deterministic() -> None:
    facts = _lifecycle_facts()

    source = staff_lifecycle_source_version("CASE-001", facts)
    repeat = staff_lifecycle_source_version("CASE-001", facts)

    assert source.source_kind == "staff_lifecycle"
    assert source.source_id == "CASE-001"
    assert len(source.version) == 64
    assert len(source.fingerprint) == 64
    assert source == repeat
    assert source.fingerprint != staff_lifecycle_source_version(
        "CASE-001", _lifecycle_facts(retired_version=4)
    ).fingerprint
    assert source.fingerprint != staff_lifecycle_source_version(
        "CASE-001", _lifecycle_facts(reason_code="qualification_changed")
    ).fingerprint
    assert source.fingerprint != staff_lifecycle_source_version(
        "CASE-001",
        (
            _lifecycle_facts()[0],
            StaffLifecycleFact(9, StaffLifecycleState.ACTIVE, 3),
        ),
    ).fingerprint


def test_staff_lifecycle_source_version_rejects_noncanonical_facts() -> None:
    facts = _lifecycle_facts()

    with pytest.raises(ValueError, match="staff ids must be sorted"):
        staff_lifecycle_source_version("CASE-001", facts[::-1])
    with pytest.raises(ValueError, match="staff ids must be sorted and unique"):
        staff_lifecycle_source_version("CASE-001", (facts[0], facts[0]))
    with pytest.raises(TypeError, match="typed tuple"):
        staff_lifecycle_source_version("CASE-001", (object(),))


def test_matching_criteria_snapshot_source_version_preserves_immutable_identity() -> None:
    snapshot = _snapshot("CASE-001", _sources())

    source = matching_criteria_snapshot_source_version(snapshot)
    repeat = matching_criteria_snapshot_source_version(snapshot)
    changed = matching_criteria_snapshot_source_version(
        build_criteria_snapshot(
            snapshot_id="snapshot:CASE-002",
            case_no="CASE-001",
            criteria_version=2,
            criteria={"service_days": 2},
            source_versions=_sources(),
            created_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
        )
    )

    assert isinstance(snapshot, MatchingCriteriaSnapshot)
    assert source.source_kind == "matching_criteria_snapshot"
    assert source.source_id == snapshot.snapshot_id
    assert source.version == snapshot.criteria_version
    assert source.fingerprint == snapshot.fingerprint.value
    assert source == repeat
    assert source != changed


def test_matching_criteria_snapshot_source_version_rejects_untyped_snapshot() -> None:
    with pytest.raises(TypeError, match="typed"):
        matching_criteria_snapshot_source_version(object())


def _matching_package(*, package_id: str = "package:1", version: int = 1) -> MatchingPackage:
    service_day = date(2026, 9, 1)
    return MatchingPackage(
        package_id=package_id,
        version=version,
        mode=MatchingPackageMode.SINGLE,
        segments=(MatchingSegment(staff_id=7, service_dates=(service_day,), sequence=1),),
        required_service_dates=(service_day,),
        candidate_results=(),
        criteria_snapshot_id="snapshot:CASE-001",
        source_versions=_sources(),
        state=MatchingPackageState.PROPOSED,
    )


def test_matching_package_source_version_is_exact_and_deterministic() -> None:
    package = _matching_package()
    source = matching_package_source_version(package, case_no="CASE-001")
    repeat = matching_package_source_version(package, case_no="CASE-001")
    changed = matching_package_source_version(
        _matching_package(package_id="package:2", version=2), case_no="CASE-001"
    )

    assert source.source_kind == "matching_package"
    assert source.source_id == package.package_id
    assert source.version == package.version
    assert source.fingerprint == package.fingerprint.value
    assert source == repeat
    assert source.version != changed.version
    assert source.fingerprint != changed.fingerprint


def test_matching_package_source_version_supports_absent_and_rejects_untyped() -> None:
    source = matching_package_source_version(None, case_no="CASE-001")
    repeat = matching_package_source_version(None, case_no="CASE-001")

    assert source.source_kind == "matching_package"
    assert source.source_id == "CASE-001"
    assert source.version == "absent"
    assert len(source.fingerprint) == 64
    assert source == repeat
    with pytest.raises(TypeError, match="typed"):
        matching_package_source_version(object(), case_no="CASE-001")


def _assignment_plan_facts(
    *, generation: int = 3, assignment_id: int = 201
) -> AssignmentPlanFacts:
    return AssignmentPlanFacts(
        case_no="CASE-001",
        order_version=4,
        scheduling_version=6,
        scheduling_generation=generation,
        client_finance_version=2,
        payroll_version=3,
        contracted_service_days=1,
        service_hours_per_day=8,
        service_started=False,
        effective_assignments=(
            EffectiveAssignmentFact(
                assignment_id=assignment_id,
                staff_id=7,
                sequence=1,
                assigned_start_date=date(2026, 9, 1),
                assigned_end_date=date(2026, 9, 1),
                official_service_dates=(date(2026, 9, 1),),
            ),
        ),
    )


def test_incumbent_assignment_source_version_is_generation_distinct_and_deterministic() -> None:
    facts = _assignment_plan_facts()
    source = incumbent_assignment_source_version(facts)
    repeat = incumbent_assignment_source_version(facts)
    changed_generation = incumbent_assignment_source_version(
        _assignment_plan_facts(generation=4)
    )
    changed_assignment = incumbent_assignment_source_version(
        _assignment_plan_facts(assignment_id=202)
    )

    assert isinstance(IncumbentAssignmentQueryPort, type)
    assert source.source_kind == "incumbent_assignment"
    assert source.source_id == "CASE-001"
    assert len(source.version) == 64
    assert len(source.fingerprint) == 64
    assert source == repeat
    assert source.version != changed_generation.version
    assert source.fingerprint != changed_generation.fingerprint
    assert source.version != changed_assignment.version


def test_incumbent_assignment_source_version_supports_empty_and_rejects_untyped() -> None:
    empty = AssignmentPlanFacts(
        case_no="CASE-001",
        order_version=1,
        scheduling_version=0,
        scheduling_generation=0,
        client_finance_version=1,
        payroll_version=1,
        contracted_service_days=1,
        service_hours_per_day=8,
        service_started=False,
    )
    source = incumbent_assignment_source_version(empty)

    assert source.source_kind == "incumbent_assignment"
    assert source.source_id == "CASE-001"
    assert source.version == "empty"
    assert len(source.fingerprint) == 64
    with pytest.raises(TypeError, match="typed"):
        incumbent_assignment_source_version(object())


def _leave_reference(
    *,
    leave_version: int = 2,
    receipt_key: str = "leave-receipt:1",
    fingerprint: str = "a" * 64,
) -> CanonicalSchedulingLeaveReference:
    return CanonicalSchedulingLeaveReference(
        receipt_key=receipt_key,
        case_no="CASE-001",
        package_id="package:1",
        criteria_snapshot_id="snapshot:CASE-001",
        leave_version=leave_version,
        original_staff_id=7,
        resolution_type=LeaveResolutionType.SUBSTITUTE,
        original_work_date=date(2026, 9, 1),
        resulting_work_date=date(2026, 9, 1),
        outcome_event_ids=("leave-event:1",),
        source_versions=_sources(),
        receipt_fingerprint=fingerprint,
        substitute_staff_id=8,
    )


def test_leave_request_or_outcome_source_version_projects_owner_reference() -> None:
    reference = _leave_reference()
    source = leave_request_or_outcome_source_version(reference)
    repeat = leave_request_or_outcome_source_version(reference, case_no="CASE-001")
    changed = leave_request_or_outcome_source_version(
        _leave_reference(leave_version=3, fingerprint="b" * 64)
    )

    assert isinstance(LeaveRequestOutcomeQueryPort, type)
    assert source.source_kind == "leave_request_or_outcome"
    assert source.source_id == reference.receipt_key
    assert source.version == reference.leave_version
    assert source.fingerprint == reference.receipt_fingerprint.value
    assert source == repeat
    assert source.version != changed.version
    assert source.fingerprint != changed.fingerprint


def test_leave_request_or_outcome_source_version_supports_absent_and_rejects_wrong_owner() -> None:
    absent = leave_request_or_outcome_source_version(None, case_no="CASE-001")
    assert absent.source_kind == "leave_request_or_outcome"
    assert absent.source_id == "CASE-001"
    assert absent.version == "absent"
    assert len(absent.fingerprint) == 64
    with pytest.raises(ValueError, match="case number"):
        leave_request_or_outcome_source_version(
            _leave_reference(), case_no="CASE-002"
        )
    with pytest.raises(TypeError, match="typed"):
        leave_request_or_outcome_source_version(object())


def _conversion_receipt(
    *, request_id: str = "conversion-request:1", package_version: int = 2, fingerprint: str = "a" * 64
) -> CanonicalAssignmentConversionReceipt:
    return CanonicalAssignmentConversionReceipt(
        request_id=request_id,
        result_state=AssignmentConversionResultState.CONVERTED,
        package_id="package:1",
        package_version=package_version,
        criteria_snapshot_id="snapshot:CASE-001",
        candidate_id="candidate:7",
        source_versions=_sources(),
        assignment_reference="assignment:201",
        receipt_fingerprint=PreviewFingerprint(fingerprint),
    )


def test_assignment_conversion_reference_source_version_projects_owner_receipt() -> None:
    receipt = _conversion_receipt()
    source = assignment_conversion_reference_source_version(receipt)
    repeat = assignment_conversion_reference_source_version(
        receipt, request_id="conversion-request:1"
    )
    changed = assignment_conversion_reference_source_version(
        _conversion_receipt(package_version=3, fingerprint="b" * 64)
    )

    assert isinstance(AssignmentConversionReferenceQueryPort, type)
    assert source.source_kind == "assignment_conversion_reference"
    assert source.source_id == receipt.request_id
    assert source.version == receipt.package_version
    assert source.fingerprint == receipt.receipt_fingerprint.value
    assert source == repeat
    assert source.version != changed.version
    assert source.fingerprint != changed.fingerprint


def test_assignment_conversion_reference_source_version_supports_absent_and_rejects_wrong_owner() -> None:
    absent = assignment_conversion_reference_source_version(
        None, request_id="conversion-request:1"
    )
    assert absent.source_kind == "assignment_conversion_reference"
    assert absent.source_id == "conversion-request:1"
    assert absent.version == "absent"
    assert len(absent.fingerprint) == 64
    with pytest.raises(ValueError, match="request ID"):
        assignment_conversion_reference_source_version(
            _conversion_receipt(), request_id="conversion-request:2"
        )
    with pytest.raises(TypeError, match="typed"):
        assignment_conversion_reference_source_version(object())


def _candidate_pool_state(
    *, willingness: str = "willing", event_id: int = 11
) -> CandidateContactPoolState:
    occurred_at = datetime(2026, 8, 22, 10, 0, tzinfo=timezone.utc)
    event = CandidateContactEventState(
        id=event_id,
        candidate_id=8,
        event_key=f"event-{event_id}",
        event_type="willingness_changed",
        actor="admin",
        occurred_at=occurred_at,
        payload_fingerprint="a" * 64,
    )
    entry = CandidateContactEntryState(
        id=8,
        staff_id=7,
        service_start_date=date(2026, 9, 1),
        service_end_date=date(2026, 9, 3),
        status="active",
        created_at=occurred_at,
        staff_name="王小美",
        willingness=willingness,
        reason="region_mismatch" if willingness == "unwilling" else None,
        information=CandidateInformationState(
            information_1=CandidateInformationDelivery(
                status="queued", sent_at=occurred_at
            )
        ),
    )
    return CandidateContactPoolState(
        pool_id=3,
        case_no="CASE-001",
        candidates=(entry,),
        events=(event,),
    )


def test_candidate_pool_source_version_is_exact_and_deterministic() -> None:
    state = _candidate_pool_state()
    source = candidate_pool_source_version(state)
    repeat = candidate_pool_source_version(state)

    assert isinstance(CandidatePoolQueryPort, type)
    assert source.source_kind == "candidate_pool"
    assert source.source_id == "CASE-001"
    assert source.version == repeat.version
    assert source.fingerprint == repeat.fingerprint
    assert len(source.version) == 64
    assert len(source.fingerprint) == 64
    assert source.fingerprint != candidate_pool_source_version(
        _candidate_pool_state(willingness="unwilling")
    ).fingerprint
    assert source.version != candidate_pool_source_version(
        _candidate_pool_state(event_id=12)
    ).version


def test_candidate_pool_source_version_accepts_empty_only_and_rejects_drift() -> None:
    empty = CandidateContactPoolState(pool_id=None, case_no="CASE-001", candidates=())
    source = candidate_pool_source_version(empty)
    assert source.version == "empty"
    assert source.source_id == "CASE-001"

    state = _candidate_pool_state()
    with pytest.raises(ValueError, match="empty candidate pool"):
        candidate_pool_source_version(
            CandidateContactPoolState(
                pool_id=None,
                case_no="CASE-001",
                candidates=state.candidates,
            )
        )

    second = CandidateContactEntryState(
        id=9,
        staff_id=8,
        service_start_date=date(2026, 9, 1),
        service_end_date=date(2026, 9, 3),
        status="active",
        created_at=datetime(2026, 8, 22, 10, 0, tzinfo=timezone.utc),
        staff_name="王小明",
        willingness="pending",
        reason=None,
        information=CandidateInformationState(),
    )
    with pytest.raises(ValueError, match="candidate ids"):
        candidate_pool_source_version(
            CandidateContactPoolState(
                pool_id=3,
                case_no="CASE-001",
                candidates=(second, state.candidates[0]),
                events=state.events,
            )
        )
    with pytest.raises(TypeError, match="typed"):
        candidate_pool_source_version(object())
