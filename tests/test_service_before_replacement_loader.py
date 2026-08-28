"""
File: test_service_before_replacement_loader.py
Description: 驗證 RPRE production loader 的 BusinessClock、scenario 與 Matching source fail-closed 邊界。
"""

from datetime import date, datetime, time, timezone
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


def test_loader_rejects_request_without_explicit_scenario():
    with pytest.raises(
        ServiceBeforeReplacementSourceUnavailable,
        match="replacement_scenario_invalid",
    ):
        _Loader(datetime(2026, 8, 28, 9, tzinfo=timezone.utc)).load_facts(
            SimpleNamespace(case_no="CASE-1", scenario=None), for_update=False
        )


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
