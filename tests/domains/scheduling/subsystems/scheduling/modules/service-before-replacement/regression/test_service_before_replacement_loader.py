"""
File: test_service_before_replacement_loader.py
Description: 驗證 RPRE production loader 的 BusinessClock、scenario 與 Matching source fail-closed 邊界。
"""

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest

from domains.scheduling.service_before_replacement import (
    ReplacementRootIdentity,
    ReplacementRootKind,
    ReplacementScenario,
)
from infrastructure.mysql.service_before_replacement_loader import (
    MySqlServiceBeforeReplacementLoader,
    ServiceBeforeReplacementSourceUnavailable,
    _matching_sources_match_current,
    _mysql_time,
    _recipient_delivery_identity_present,
    _validate_exact_plan_segments,
    _validate_matching_event_binding,
    _validate_signback_row,
)
from infrastructure.mysql.matching_coordination_facts_adapter import (
    MatchingCoordinationFactsAdapterError,
    SOURCE_ORDER,
)
from shared_kernel.clock import FixedBusinessClock
from shared_kernel.fingerprints import fingerprint_payload


class _Loader(MySqlServiceBeforeReplacementLoader):
    def __init__(self, current_time):
        super().__init__(object(), object(), FixedBusinessClock(current_time))

    def _scheduling_base(self, case_no, *, for_update):
        assert case_no == "CASE-1"
        assert for_update is False
        return (
            {
                "service_start_time": time(8),
                "generation_id": 17,
                "generation_number": 4,
                "aggregate_version": 8,
                "prior_event_identity": "scheduling-rebuild-event:CASE-1:23",
                "event_version": 6,
            },
            (
                {"assignment_id": 31, "staff_id": 5, "assignment_sequence": 1, "assignment_status": "planned", "schedule_id": 41, "work_date": date(2026, 8, 27), "is_work_day": 1, "effective_marker": 1},
                {"assignment_id": 31, "staff_id": 5, "assignment_sequence": 1, "assignment_status": "planned", "schedule_id": 42, "work_date": date(2026, 8, 29), "is_work_day": 1, "effective_marker": 1},
            ),
        )

    def _scenario_roots(self, case_no, scenario, base, schedules, *, for_update):
        assert scenario is ReplacementScenario.R01
        return (
            ReplacementRootIdentity(ReplacementRootKind.CANDIDATE_BINDING, "pool:set", case_no),
            ReplacementRootIdentity(ReplacementRootKind.WILLINGNESS, "willingness:set", case_no),
        )

    def _candidate_reuse(self, case_no, base, *, for_update):
        return None


def test_loader_uses_explicit_scenario_and_only_started_official_moments():
    request = SimpleNamespace(
        case_no="CASE-1",
        scenario=ReplacementScenario.R01,
        reason="人工換人",
        evidence=("ticket:1",),
    )
    facts = _Loader(datetime(2026, 8, 28, 9, tzinfo=timezone.utc)).load_facts(
        request, for_update=False
    )

    assert facts.scenario is ReplacementScenario.R01
    assert facts.actual_service_dates == (date(2026, 8, 27),)
    assert date(2026, 8, 29) not in facts.actual_service_dates
    assert facts.prior_event_identity == "scheduling-rebuild-event:CASE-1:23"
    assert facts.replacement_reason == "人工換人"


def test_mysql_time_normalizes_driver_timedelta_without_changing_wall_time():
    assert _mysql_time(timedelta(hours=9, minutes=30)) == time(9, 30)


def test_loader_rejects_request_without_explicit_scenario():
    with pytest.raises(
        ServiceBeforeReplacementSourceUnavailable,
        match="replacement_scenario_invalid",
    ):
        _Loader(datetime(2026, 8, 28, 9, tzinfo=timezone.utc)).load_facts(
            SimpleNamespace(case_no="CASE-1", scenario=None), for_update=False
        )


def test_r03_apply_locks_staff_mutex_before_loading_fresh_owner_roots(monkeypatch):
    from infrastructure.mysql import service_before_replacement_loader as module

    order = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Connection:
        def cursor(self):
            return Cursor()

    class Loader(MySqlServiceBeforeReplacementLoader):
        def _scheduling_base(self, case_no, *, for_update):
            order.append("case_aggregate")
            return ({
                "generation_id": 17,
                "generation_number": 1,
                "aggregate_version": 1,
                "prior_event_identity": "scheduling-rebuild-event:CASE-1:1",
                "event_version": 1,
                "service_start_time": time(8),
            }, ())

        def _preflight_r03_staff_ids(self, case_no):
            order.append("preflight")
            return (5,)

        def _scenario_roots(
            self, case_no, scenario, base, schedules, *, for_update,
            locked_staff_ids=(),
        ):
            order.append(("fresh_roots", locked_staff_ids))
            return tuple(
                ReplacementRootIdentity(kind, f"{kind.value}:CASE-1", case_no)
                for kind in (
                    ReplacementRootKind.WAITING_LOCK,
                    ReplacementRootKind.COMMITMENT,
                    ReplacementRootKind.SIGNBACK,
                    ReplacementRootKind.RECIPIENT_BINDING,
                )
            )

        def _started_service_dates(self, base, schedules):
            return ()

        def _candidate_reuse(self, case_no, base, *, for_update):
            return None

    def lock_mutex(cursor, staff_ids):
        order.append(("staff_mutex", tuple(staff_ids)))
        return tuple(staff_ids)

    monkeypatch.setattr(module, "lock_staff_occupancy_mutex", lock_mutex)

    Loader(Connection(), object()).load_facts(
        SimpleNamespace(case_no="CASE-1", scenario=ReplacementScenario.R03),
        for_update=True,
    )

    assert order == [
        "case_aggregate",
        "preflight",
        ("staff_mutex", (5,)),
        ("fresh_roots", (5,)),
    ]


def test_matching_source_requires_package_bound_event():
    class MatchingFacts:
        def load_sources(self, case_no, *, for_update):
            sources = tuple(
                SimpleNamespace(
                    source_kind=kind,
                    source_id=f"{kind}:CASE-1",
                    version=1,
                    fingerprint="a" * 64,
                )
                for kind in SOURCE_ORDER
            )
            return SimpleNamespace(
                matching_criteria_snapshot=SimpleNamespace(
                    snapshot_id="snapshot:1",
                    criteria_version=1,
                    criteria={"service_days": 1},
                    fingerprint=fingerprint_payload({"snapshot": 1}),
                ),
                matching_package=SimpleNamespace(
                    package_id="package:1", candidate_results=()
                ),
                source_versions=sources,
                orders_service_dates=SimpleNamespace(current_dates=(date(2026, 9, 1),)),
            )

    loader = MySqlServiceBeforeReplacementLoader(object(), MatchingFacts())
    loader._one = lambda *args, **kwargs: None
    with pytest.raises(
        ServiceBeforeReplacementSourceUnavailable,
        match="replacement_matching_source_event_unavailable",
    ):
        loader.load_matching_source(
            SimpleNamespace(case_no="CASE-1", scenario=ReplacementScenario.R01),
            for_update=True,
        )


def test_matching_source_failure_cannot_be_interpreted_as_no_reuse():
    class MatchingFacts:
        def load_sources(self, case_no, *, for_update):
            raise RuntimeError("connection dropped")

    loader = MySqlServiceBeforeReplacementLoader(object(), MatchingFacts())
    with pytest.raises(
        ServiceBeforeReplacementSourceUnavailable,
        match="replacement_matching_sources_unavailable",
    ):
        loader._candidate_reuse(
            "CASE-1",
            {"generation_number": 1, "event_version": 1},
            for_update=True,
        )


def test_matching_source_preserves_exact_missing_source_code():
    class MatchingFacts:
        def load_sources(self, case_no, *, for_update):
            raise MatchingCoordinationFactsAdapterError(
                "orders_service_dates", "unavailable"
            )

    loader = MySqlServiceBeforeReplacementLoader(object(), MatchingFacts())
    with pytest.raises(
        ServiceBeforeReplacementSourceUnavailable,
        match="replacement_matching_orders_service_dates_unavailable",
    ):
        loader._candidate_reuse(
            "CASE-1",
            {"generation_number": 1, "event_version": 1},
            for_update=True,
        )


def test_matching_source_comparison_preserves_consulted_facts_without_self_reference():
    current = tuple(
        {
            "source_kind": kind,
            "source_id": f"{kind}:current",
            "version": 2,
            "fingerprint": "b" * 64,
        }
        for kind in SOURCE_ORDER
    )
    persisted = tuple(
        (
            {
                "source_kind": kind,
                "source_id": "not_consulted",
                "version": "not_consulted",
                "fingerprint": "not_consulted",
            }
            if kind not in {"orders_terms", "matching_package"}
            else {
                "source_kind": kind,
                "source_id": f"{kind}:current" if kind == "orders_terms" else "CASE-1",
                "version": 2 if kind == "orders_terms" else "absent",
                "fingerprint": "b" * 64 if kind == "orders_terms" else "a" * 64,
            }
        )
        for kind in SOURCE_ORDER
    )

    assert _matching_sources_match_current(
        persisted,
        current,
        ignored_source_kinds=("matching_package",),
    )
    drifted = tuple(
        {**item, "version": 3} if item["source_kind"] == "orders_terms" else item
        for item in persisted
    )
    assert not _matching_sources_match_current(
        drifted,
        current,
        ignored_source_kinds=("matching_package",),
    )


def test_exact_matching_package_segments_bind_current_plan_without_legacy_plan_fields():
    service_dates = (date(2026, 9, 1), date(2026, 9, 2))
    plan = {"id": 7}
    segments = (
        {
            "id": 8,
            "segment_order": 1,
            "staff_id": 9,
            "assigned_start_date": service_dates[0],
            "assigned_end_date": service_dates[-1],
        },
    )

    _validate_exact_plan_segments(
        {
            "segments": [
                {
                    "sequence": 1,
                    "staff_id": 9,
                    "service_dates": [item.isoformat() for item in service_dates],
                }
            ]
        },
        "CASE-1",
        plan,
        segments,
        service_dates,
        "matching_reply",
    )

    with pytest.raises(
        ServiceBeforeReplacementSourceUnavailable,
        match="replacement_matching_reply_binding_drift",
    ):
        _validate_exact_plan_segments(
            {
                "segments": [
                    {
                        "sequence": 1,
                        "staff_id": 10,
                        "service_dates": [item.isoformat() for item in service_dates],
                    }
                ]
            },
            "CASE-1",
            plan,
            segments,
            service_dates,
            "matching_reply",
        )


def test_recipient_delivery_identity_accepts_line_or_canonical_manual_proof():
    assert _recipient_delivery_identity_present(
        {"recipient_line_user_id": "U-fixture"},
        {},
    )
    assert _recipient_delivery_identity_present(
        {"recipient_line_user_id": None},
        {"manual_preparation": {"actor": "development-bypass", "reason": "phone"}},
    )
    assert not _recipient_delivery_identity_present(
        {"recipient_line_user_id": None},
        {"manual_preparation": {"actor": "", "reason": "phone"}},
    )


def test_r07_successor_must_match_current_generation_and_event_versions():
    class Loader(MySqlServiceBeforeReplacementLoader):
        def __init__(self, row):
            super().__init__(object(), object())
            self.row = row

        def _one(self, sql, params, for_update):
            return self.row

    row = {
        "successor_round_identity": "round:CASE-1:9",
        "replacement_generation_id": 99,
        "event_generation_id": 99,
        "scenario": "R-07",
        "replacement_generation_identity": "replacement-generation:CASE-1:9",
        "replacement_event_identity": "replacement-event:CASE-1:9",
        "resulting_generation_version": 9,
        "resulting_event_version": 12,
        "candidate_count": 0,
        "zero_candidate_disposition": "blocked_no_candidate",
    }
    with pytest.raises(
        ServiceBeforeReplacementSourceUnavailable,
        match="replacement_successor_current_binding_drift",
    ):
        Loader(row)._successor_round(
            "CASE-1",
            base={"generation_id": 100, "generation_number": 9, "event_version": 12},
            for_update=True,
        )


def test_r07_loader_requires_exact_matching_owner_receipt_and_assignment_intent():
    from domains.scheduling.matching_coordination import (
        MatchingPackage,
        MatchingPackageMode,
        MatchingPackageState,
        MatchingSourceVersion,
        SOURCE_KINDS,
    )

    versions = tuple(
        MatchingSourceVersion(kind, f"{kind}:CASE-1", 1, "a" * 64)
        for kind in SOURCE_KINDS
    )
    package = MatchingPackage(
        package_id="matching:CASE-1:no-candidate:proof",
        version=3,
        mode=MatchingPackageMode.SINGLE,
        segments=(),
        required_service_dates=(date(2026, 9, 1),),
        candidate_results=(),
        criteria_snapshot_id="snapshot:1",
        source_versions=versions,
        state=MatchingPackageState.NO_CANDIDATE,
        blockers=("no_legal_candidate",),
    )
    package_payload = {
        "package_id": package.package_id,
        "version": package.version,
        "state": package.state.value,
        "fingerprint": package.fingerprint.value,
    }

    class Loader(MySqlServiceBeforeReplacementLoader):
        def load_matching_source(self, request, *, for_update):
            return {
                "case_no": "CASE-1",
                "snapshot_id": "snapshot:1",
                "parent_package": package,
                "source_event_identity": "matching:event:zero-candidate",
                "source_event_version": 3,
                "source_event_type": "package_proposed",
                "source_event_fingerprint": "e" * 64,
                "matching_package_lineage_id": 41,
                "matching_event_id": 51,
            }

        def _all(self, sql, params, for_update):
            return (
                {
                    "receipt_id": "matching:zero:receipt",
                    "command_name": "ApplyZeroCandidateConfirmation",
                    "outcome_state": "applied",
                    "result_snapshot": {
                        "result_state": "zero_candidate_confirmed",
                        "resulting_package": package_payload,
                    },
                    "event_id": 51,
                    "package_lineage_id": 41,
                    "reference_id": "matching:zero:assignment",
                    "intent_type": "rematch_requested",
                    "target_owner": "assignment_workflow",
                    "intent_payload": {"resulting_package": package_payload},
                },
            )

    proof = Loader(object(), object())._matching_zero_candidate_proof(
        SimpleNamespace(case_no="CASE-1", scenario=ReplacementScenario.R07),
        for_update=True,
    )

    assert proof.package_identity == package.package_id
    assert proof.event_identity == "matching:event:zero-candidate"
    assert proof.receipt_identity == "matching:zero:receipt"
    assert proof.assignment_intent_identity == "matching:zero:assignment"


def test_malformed_schedule_row_is_source_unavailable_instead_of_ignored():
    loader = MySqlServiceBeforeReplacementLoader(
        object(), object(), FixedBusinessClock(datetime(2026, 8, 28, 9, tzinfo=timezone.utc))
    )
    with pytest.raises(
        ServiceBeforeReplacementSourceUnavailable,
        match="replacement_official_schedule_malformed",
    ):
        loader._started_service_dates(
            {"service_start_time": time(8)},
            ({"work_date": "2026-08-27"},),
        )


def test_matching_parent_source_accepts_package_proposed_event():
    snapshot = SimpleNamespace(snapshot_id="snapshot:1")
    package = SimpleNamespace(package_id="package:1")
    _validate_matching_event_binding(
        {
            "case_no": "CASE-1",
            "event_type": "package_proposed",
            "event_id": "matching:event:1",
            "criteria_snapshot_id": 7,
            "package_lineage_id": 8,
            "expected_snapshot_row_id": 7,
            "expected_snapshot_id": "snapshot:1",
            "expected_package_row_id": 8,
            "expected_package_id": "package:1",
            "resulting_version": 2,
            "event_payload": {"package_id": "package:1"},
            "package_snapshot": {
                "package_id": "package:1",
                "criteria_snapshot_id": "snapshot:1",
            },
        },
        "CASE-1",
        snapshot,
        package,
    )


def test_scheduling_base_rejects_malformed_rebuild_predecessor():
    class Loader(MySqlServiceBeforeReplacementLoader):
        def _one(self, sql, params, for_update):
            return {
                "case_no": "CASE-1",
                "aggregate_case_no": "CASE-1",
                "generation_case_no": "CASE-1",
                "status": "effective",
                "effective_marker": 1,
                "generation_id": 10,
                "generation_number": 2,
                "aggregate_version": 2,
                "generation_counter": 2,
                "rebuild_event_id": 20,
                "rebuild_case_no": "CASE-1",
                "new_generation_id": 10,
                "previous_generation_id": None,
                "expected_scheduling_version": 1,
                "resulting_scheduling_version": 2,
                "latest_replacement_identity": None,
            }

        def _all(self, sql, params, for_update):
            return ()

    with pytest.raises(
        ServiceBeforeReplacementSourceUnavailable,
        match="replacement_rebuild_predecessor_binding_drift",
    ):
        Loader(object(), object())._scheduling_base("CASE-1", for_update=False)


def test_scheduling_base_reports_initial_missing_rebuild_predecessor():
    class Loader(MySqlServiceBeforeReplacementLoader):
        def _one(self, sql, params, for_update):
            return {
                "case_no": "CASE-1", "aggregate_case_no": "CASE-1",
                "generation_case_no": "CASE-1", "status": "effective", "effective_marker": 1,
                "generation_id": 10, "generation_number": 1,
                "aggregate_version": 1, "generation_counter": 1,
                "rebuild_event_id": None, "latest_replacement_identity": None,
            }

    with pytest.raises(
        ServiceBeforeReplacementSourceUnavailable,
        match="replacement_prior_event_unavailable",
    ):
        Loader(object(), object())._scheduling_base("CASE-1", for_update=False)


def test_scheduling_base_uses_latest_replacement_without_rebuild_row():
    class Loader(MySqlServiceBeforeReplacementLoader):
        def _one(self, sql, params, for_update):
            return {
                "case_no": "CASE-1", "aggregate_case_no": "CASE-1",
                "generation_case_no": "CASE-1", "status": "effective", "effective_marker": 1,
                "generation_id": 10, "generation_number": 9,
                "aggregate_version": 9, "generation_counter": 9,
                "rebuild_event_id": None,
                "latest_replacement_identity": "replacement-event:CASE-1:14",
                "latest_replacement_generation_id": 10,
                "latest_replacement_generation_version": 9,
                "latest_replacement_aggregate_version": 9,
                "latest_replacement_version": 14,
            }

        def _all(self, sql, params, for_update):
            return ()

    base, schedules = Loader(object(), object())._scheduling_base("CASE-1", for_update=False)

    assert base["prior_event_identity"] == "replacement-event:CASE-1:14"
    assert base["event_version"] == 14
    assert schedules == ()


def test_scheduling_base_rejects_latest_replacement_generation_drift_without_rebuild_row():
    class Loader(MySqlServiceBeforeReplacementLoader):
        def _one(self, sql, params, for_update):
            return {
                "case_no": "CASE-1", "aggregate_case_no": "CASE-1",
                "generation_case_no": "CASE-1", "status": "effective", "effective_marker": 1,
                "generation_id": 10, "generation_number": 9,
                "aggregate_version": 9, "generation_counter": 9,
                "rebuild_event_id": None,
                "latest_replacement_identity": "replacement-event:CASE-1:14",
                "latest_replacement_generation_id": 11,
                "latest_replacement_generation_version": 9,
                "latest_replacement_aggregate_version": 9,
                "latest_replacement_version": 14,
            }

    with pytest.raises(
        ServiceBeforeReplacementSourceUnavailable,
        match="replacement_prior_event_generation_drift",
    ):
        Loader(object(), object())._scheduling_base("CASE-1", for_update=False)


def test_external_signback_requires_exact_source_receipt_and_session_lineage():
    row = _external_signback_row()
    _validate_signback_row(
        row,
        "CASE-1",
        11,
        21,
        external=True,
        session_database_id=31,
        session_identity="ces_" + "1" * 32,
    )

    stale = dict(row, receipt_session_id=99)
    with pytest.raises(
        ServiceBeforeReplacementSourceUnavailable,
        match="replacement_signback_lineage_invalid",
    ):
        _validate_signback_row(
            stale,
            "CASE-1",
            11,
            21,
            external=True,
            session_database_id=31,
            session_identity="ces_" + "1" * 32,
        )


def test_legacy_signback_query_projects_document_segment_owner_identity():
    class Loader(MySqlServiceBeforeReplacementLoader):
        def _all(self, sql, params, for_update):
            if "contract_external_signing_sessions" in sql:
                return ()
            assert "document.matching_segment_id AS document_segment_id" in sql
            return ({
                "document_id": 41,
                "document_case_no": "CASE-1",
                "document_plan_id": 11,
                "document_segment_id": 21,
                "document_scope": "staff_segment",
                "document_role": "signed_return",
                "version_number": 2,
                "sha256": "a" * 64,
                "event_id": 51,
                "event_case_no": "CASE-1",
                "event_plan_id": 11,
                "event_segment_id": 21,
                "event_key": "signback:51",
                "payload": {"command": "manual_attestation"},
                "receipt_id": 61,
                "receipt_case_no": "CASE-1",
                "receipt_document_id": 41,
                "receipt_event_id": 51,
                "idempotency_key": "signback:51",
                "result_snapshot": {"document_version_id": 41},
            },)

    rows = Loader(object(), object())._signback(
        "CASE-1",
        11,
        ({"id": 21},),
        False,
    )

    assert rows[0]["document_segment_id"] == 21


def _external_signback_row():
    session_identity = "ces_" + "1" * 32
    report_identity = "cer_" + "2" * 32
    return {
        "document_id": 41,
        "document_case_no": "CASE-1",
        "document_plan_id": 11,
        "matching_segment_id": 21,
        "document_segment_id": 21,
        "document_scope": "staff_segment",
        "document_role": "signed_return",
        "version_number": 1,
        "sha256": "a" * 64,
        "source_event_identity": "line:event:1",
        "source_payload_sha256": "b" * 64,
        "report_identity": report_identity,
        "report_id": 51,
        "receipt_id": 61,
        "report_case_no": "CASE-1",
        "report_session_id": 31,
        "receipt_session_id": 31,
        "receipt_report_id": 51,
        "receipt_identity": "cesr_" + "3" * 32,
        "outcome_state": "recorded",
        "resulting_status_version": 1,
        "source_kind": "verified_line",
        "line_inbox_event_id": 71,
        "verified_line_user_id": "U1",
        "inbox_id": 71,
        "inbox_event_identity": "line:event:1",
        "inbox_payload_fingerprint": "b" * 64,
        "inbox_source_user_id": "U1",
        "result_snapshot": {
            "session_id": session_identity,
            "scope": "staff",
            "matching_segment_id": 21,
            "report_id": report_identity,
            "resulting_status_version": 1,
            "command_type": "record_external_staff_signing_report",
        },
    }
