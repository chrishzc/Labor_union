"""
File: test_matching_coordination_facts_adapter.py
Description: 驗證 M3 十三來源 facts adapter 的順序、型別與唯讀失敗邊界。
"""

from datetime import date, datetime, time, timezone

import pytest

import infrastructure.mysql.matching_coordination_facts_adapter as adapter_module
from domains.orders.terms import OrderAggregateFacts, OrderTerms, ServiceTimeTerms
from domains.scheduling.assignment_plan import AssignmentPlanFacts
from domains.scheduling.generation import SchedulingGenerationFacts
from domains.scheduling.matching_coordination import (
    CandidateEligibility,
    DynamicWillingnessLineage,
    MatchingCandidateResult,
    MatchingPackage,
    MatchingPackageMode,
    MatchingPackageState,
    MatchingSegment,
    MatchingSourceVersion,
    SOURCE_KINDS,
    build_criteria_snapshot,
)
from domains.scheduling.staff_availability import StaffAvailabilityFacts
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.money import MoneyNTD
from subsystems.orders.service_date_confirmation_workflow import ServiceDateConfirmationFacts
from subsystems.scheduling.candidate_contact_pool_workflow import CandidateContactPoolState
from subsystems.scheduling.matching_coordination_query import StaffProfileValuesFacts


CASE_NO = "CASE-001"


def _sources() -> tuple[MatchingSourceVersion, ...]:
    values = tuple(
        MatchingSourceVersion(kind, f"{kind}:1", 1, "a" * 64)
        for kind in SOURCE_KINDS
    )
    return values[:-2] + (
        MatchingSourceVersion.not_consulted("leave_request_or_outcome"),
        MatchingSourceVersion.not_consulted("assignment_conversion_reference"),
    )


def _facts() -> dict[str, object]:
    return {
        "orders_terms": OrderAggregateFacts(
            case_no=CASE_NO,
            version=3,
            terms=OrderTerms(
                planned_start_date=date(2026, 9, 1),
                service_days=1,
                service_hours_per_day=8,
                floor_fee=MoneyNTD(1000),
                service_time=ServiceTimeTerms(time(8), time(16), 0),
            ),
            service_data_locked=False,
            client_identity_status="verified",
        ),
        "orders_service_dates": ServiceDateConfirmationFacts(
            case_no=CASE_NO,
            order_version=3,
            scheduling_version=4,
            contracted_service_days=1,
            suggested_dates=(date(2026, 9, 1),),
            selectable_dates=(date(2026, 9, 1),),
            current_version=1,
            current_dates=(date(2026, 9, 1),),
        ),
        "scheduling_availability": (),
        "scheduling_effective_generation": SchedulingGenerationFacts(
            case_no=CASE_NO,
            aggregate_version=4,
            generation_number=1,
            segments=(),
            service_started=False,
        ),
        "staff_profile_definition": (),
        "staff_profile_values": (),
        "staff_lifecycle": (),
        "candidate_pool": CandidateContactPoolState(
            pool_id=None, case_no=CASE_NO, candidates=()
        ),
        "incumbent_assignment": AssignmentPlanFacts(
            case_no=CASE_NO,
            order_version=3,
            scheduling_version=4,
            scheduling_generation=1,
            client_finance_version=1,
            payroll_version=1,
            contracted_service_days=1,
            service_hours_per_day=8,
            service_started=False,
        ),
    }


class _RecordingPort:
    def __init__(self, facts: dict[str, object], calls: list[str]) -> None:
        self._facts = facts
        self._calls = calls
        self.locked_calls: list[str] = []

    def _record(self, name: str, for_update: bool) -> None:
        self._calls.append(name)
        if for_update:
            self.locked_calls.append(name)

    def load_order_terms(self, case_no: str, *, for_update: bool = False):
        self._record("orders_terms", for_update)
        return self._facts["orders_terms"]

    def load_service_dates(self, case_no: str, *, for_update: bool = False):
        self._record("orders_service_dates", for_update)
        return self._facts["orders_service_dates"]

    def load_availability(
        self, case_no: str, staff_ids: tuple[int, ...], *, for_update: bool = False
    ):
        self._record("scheduling_availability", for_update)
        return self._facts["scheduling_availability"]

    def load_effective_generation(self, case_no: str, *, for_update: bool = False):
        self._record("scheduling_effective_generation", for_update)
        return self._facts["scheduling_effective_generation"]

    def load_definitions(self, *, for_update: bool = False):
        self._record("staff_profile_definition", for_update)
        return self._facts["staff_profile_definition"]

    def load_profile_values(
        self, staff_ids: tuple[int, ...], *, for_update: bool = False
    ):
        self._record("staff_profile_values", for_update)
        return self._facts["staff_profile_values"]

    def load_lifecycle(
        self, staff_ids: tuple[int, ...], *, for_update: bool = False
    ):
        self._record("staff_lifecycle", for_update)
        return self._facts["staff_lifecycle"]

    def load_current_snapshot(self, case_no: str, *, for_update: bool = False):
        self._record("matching_criteria_snapshot", for_update)
        return self._facts["matching_criteria_snapshot"]

    def load_snapshot_history(self, case_no: str, *, for_update: bool = False):
        self._record("matching_criteria_snapshot_history", for_update)
        return self._facts["matching_criteria_snapshot_history"]

    def load_willingness_history(self, case_no: str, *, for_update: bool = False):
        self._record("matching_willingness_history", for_update)
        return self._facts["matching_willingness_history"]

    def load_candidate_pool(self, case_no: str, *, for_update: bool = False):
        self._record("candidate_pool", for_update)
        return self._facts["candidate_pool"]

    def load_current_package(self, case_no: str, *, for_update: bool = False):
        self._record("matching_package", for_update)
        return self._facts["matching_package"]

    def load_current_assignments(self, case_no: str, *, for_update: bool = False):
        self._record("incumbent_assignment", for_update)
        return self._facts["incumbent_assignment"]


def _adapter(monkeypatch: pytest.MonkeyPatch, *, calls: list[str], facts=None):
    values = _facts() if facts is None else facts
    sources = _sources()
    values["matching_criteria_snapshot"] = build_criteria_snapshot(
        snapshot_id="snapshot-1",
        case_no=CASE_NO,
        criteria_version=1,
        criteria={"service_days": 1},
        source_versions=sources,
        created_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )
    values["matching_package"] = MatchingPackage(
        package_id="package-empty",
        version=1,
        mode=MatchingPackageMode.SINGLE,
        segments=(MatchingSegment(7, (date(2026, 9, 1),), 1),),
        required_service_dates=(date(2026, 9, 1),),
        candidate_results=(),
        criteria_snapshot_id="snapshot-1",
        source_versions=sources,
        state=MatchingPackageState.NO_CANDIDATE,
    )
    values["matching_criteria_snapshot_history"] = (
        values["matching_criteria_snapshot"],
    )
    values["matching_willingness_history"] = ()
    port = _RecordingPort(values, calls)
    fixed = lambda kind: lambda *_args, **_kwargs: next(
        source for source in sources if source.source_kind == kind
    )
    for name, kind in (
        ("orders_terms_source_version", "orders_terms"),
        ("orders_service_dates_source_version", "orders_service_dates"),
        ("scheduling_availability_source_version", "scheduling_availability"),
        ("scheduling_effective_generation_source_version", "scheduling_effective_generation"),
        ("staff_profile_definition_source_version", "staff_profile_definition"),
        ("staff_profile_values_source_version", "staff_profile_values"),
        ("staff_lifecycle_source_version", "staff_lifecycle"),
        ("matching_criteria_snapshot_source_version", "matching_criteria_snapshot"),
        ("candidate_pool_source_version", "candidate_pool"),
        ("matching_package_source_version", "matching_package"),
        ("incumbent_assignment_source_version", "incumbent_assignment"),
    ):
        monkeypatch.setattr(adapter_module, name, fixed(kind))
    return adapter_module.MySqlMatchingCoordinationFactsAdapter(
        orders_terms=port,
        orders_service_dates=port,
        scheduling_availability=port,
        scheduling_effective_generation=port,
        staff_profile=port,
        staff_lifecycle=port,
        matching_criteria_snapshot=port,
        candidate_pool=port,
        matching_package=port,
        incumbent_assignment=port,
        staff_ids=(),
    ), values, sources


def test_load_sources_uses_canonical_thirteen_source_order(monkeypatch):
    calls: list[str] = []
    adapter, _, _ = _adapter(monkeypatch, calls=calls)

    projection = adapter.load_sources(CASE_NO)

    assert calls == list(adapter_module.SOURCE_ORDER[:11])
    assert tuple(item.source_kind for item in projection.source_versions) == adapter_module.SOURCE_ORDER


def test_optional_references_are_explicit_not_consulted_without_keys(monkeypatch):
    calls: list[str] = []
    adapter, _, _ = _adapter(monkeypatch, calls=calls)
    adapter = adapter_module.MySqlMatchingCoordinationFactsAdapter(
        **{name: getattr(adapter, f"_{name}", None) for name in ()},
        orders_terms=adapter._ports["orders_terms"],
        orders_service_dates=adapter._ports["orders_service_dates"],
        scheduling_availability=adapter._ports["scheduling_availability"],
        scheduling_effective_generation=adapter._ports["scheduling_effective_generation"],
        staff_profile=adapter._ports["staff_profile_definition"],
        staff_lifecycle=adapter._ports["staff_lifecycle"],
        matching_criteria_snapshot=adapter._ports["matching_criteria_snapshot"],
        candidate_pool=adapter._ports["candidate_pool"],
        matching_package=adapter._ports["matching_package"],
        incumbent_assignment=adapter._ports["incumbent_assignment"],
        staff_ids=(),
    )

    projection = adapter.load_sources(CASE_NO)
    assert projection.source_versions[-2:] == (
        MatchingSourceVersion.not_consulted("leave_request_or_outcome"),
        MatchingSourceVersion.not_consulted("assignment_conversion_reference"),
    )


def test_missing_owner_port_fails_closed(monkeypatch):
    adapter, _, _ = _adapter(monkeypatch, calls=[])
    adapter = adapter_module.MySqlMatchingCoordinationFactsAdapter(
        orders_terms=adapter._ports["orders_terms"], staff_ids=()
    )

    with pytest.raises(adapter_module.MatchingCoordinationFactsAdapterError, match="orders_service_dates unavailable"):
        adapter.load_sources(CASE_NO)


def test_partial_and_ambiguous_owner_facts_fail_closed(monkeypatch):
    calls: list[str] = []
    adapter, facts, _ = _adapter(monkeypatch, calls=calls)
    facts["orders_service_dates"] = object()
    with pytest.raises(adapter_module.MatchingCoordinationFactsAdapterError, match="orders_service_dates partial"):
        adapter.load_sources(CASE_NO)

    class AmbiguousFactsError(RuntimeError):
        pass

    class AmbiguousPort(_RecordingPort):
        def load_order_terms(self, case_no: str):
            raise AmbiguousFactsError("owner result")

    ambiguous = AmbiguousPort(_facts(), [])
    with pytest.raises(adapter_module.MatchingCoordinationFactsAdapterError, match="orders_terms ambiguous"):
        adapter_module.MySqlMatchingCoordinationFactsAdapter(
            orders_terms=ambiguous, staff_ids=()
        ).load_sources(CASE_NO)


def test_load_preserves_package_candidate_criteria_and_rejection_reasons(monkeypatch):
    calls: list[str] = []
    adapter, facts, sources = _adapter(monkeypatch, calls=calls)
    candidate = MatchingCandidateResult(
        "candidate-1",
        7,
        CandidateEligibility.INELIGIBLE,
        (),
        rejection_reasons=("region_mismatch",),
        willingness="unwilling",
    )
    facts["matching_package"] = MatchingPackage(
        package_id="package-1",
        version=1,
        mode=MatchingPackageMode.SINGLE,
        segments=(MatchingSegment(7, (date(2026, 9, 1),), 1),),
        required_service_dates=(date(2026, 9, 1),),
        candidate_results=(candidate,),
        criteria_snapshot_id="snapshot-1",
        source_versions=sources,
        state=MatchingPackageState.PROPOSED,
    )
    result = adapter.load(CASE_NO)
    assert result.package is facts["matching_package"]
    assert result.package.candidate_results[0].rejection_reasons == ("region_mismatch",)
    assert result.package.candidate_results[0].eligibility is CandidateEligibility.INELIGIBLE
    assert result.criteria_snapshots == facts["matching_criteria_snapshot_history"]


def test_load_rejects_snapshot_history_that_does_not_end_at_current(monkeypatch):
    adapter, facts, sources = _adapter(monkeypatch, calls=[])
    facts["matching_criteria_snapshot_history"] = (
        build_criteria_snapshot(
            snapshot_id="snapshot-stale",
            case_no=CASE_NO,
            criteria_version=2,
            criteria={"service_days": 2},
            source_versions=sources,
            created_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
        ),
    )

    with pytest.raises(
        adapter_module.MatchingCoordinationFactsAdapterError,
        match="matching_criteria_snapshot stale_history",
    ):
        adapter.load(CASE_NO)


def test_load_rejects_willingness_lineage_with_stale_snapshot_sources(monkeypatch):
    adapter, facts, sources = _adapter(monkeypatch, calls=[])
    stale_sources = list(sources)
    stale_sources[0] = MatchingSourceVersion(
        SOURCE_KINDS[0], f"{SOURCE_KINDS[0]}:2", 2, "b" * 64
    )
    facts["matching_willingness_history"] = (
        DynamicWillingnessLineage(
            event_id="event-stale-source",
            candidate_id="candidate-1",
            staff_id=7,
            snapshot_id="snapshot-1",
            source_versions=tuple(stale_sources),
            previous_state="pending",
            current_state="willing",
            affected_criteria=("service_days",),
        ),
    )

    with pytest.raises(
        adapter_module.MatchingCoordinationFactsAdapterError,
        match="matching_criteria_snapshot stale_willingness_source",
    ):
        adapter.load(CASE_NO)


def test_load_rejects_candidate_lineage_that_changes_staff_identity(monkeypatch):
    adapter, facts, sources = _adapter(monkeypatch, calls=[])
    facts["matching_willingness_history"] = tuple(
        DynamicWillingnessLineage(
            event_id=f"event-{staff_id}",
            candidate_id="candidate-1",
            staff_id=staff_id,
            snapshot_id="snapshot-1",
            source_versions=sources,
            previous_state="pending",
            current_state="willing",
            affected_criteria=("service_days",),
        )
        for staff_id in (7, 8)
    )

    with pytest.raises(
        adapter_module.MatchingCoordinationFactsAdapterError,
        match="candidate_pool ambiguous_willingness_identity",
    ):
        adapter.load(CASE_NO)


def test_adapter_has_no_mutation_or_commit_surface(monkeypatch):
    adapter, _, _ = _adapter(monkeypatch, calls=[])
    assert not any(hasattr(adapter, name) for name in ("commit", "write", "persist", "save"))


def test_apply_fresh_read_uses_locked_owner_projection_without_override(monkeypatch):
    adapter, facts, _ = _adapter(monkeypatch, calls=[])
    result = adapter.load_fresh(CASE_NO, for_update=True)

    assert result.snapshot == facts["matching_criteria_snapshot"]
    port = adapter._ports["orders_terms"]
    assert port.locked_calls == [
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
        "matching_criteria_snapshot_history",
        "matching_willingness_history",
    ]

    with pytest.raises(
        adapter_module.MatchingCoordinationFactsAdapterError,
        match="owner_lock_set unavailable",
    ):
        adapter.load_fresh(CASE_NO, for_update=False)
