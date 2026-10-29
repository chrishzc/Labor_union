"""
File: test_segmented_availability_coverage.py
Description: 驗證媒合候選覆蓋率使用已確認服務日與後端日期區間。
"""

from dataclasses import replace
from datetime import date, timedelta

import pytest

from domains.scheduling.matching_communication import (
    CaregiverWillingness, CustomerMatchingDecision, MatchingDecisionNotReadyError, MatchingPlanReference,
)
from subsystems.scheduling.matching_notification_application import (
    MatchingPlanDateMismatchError, _availability_blocker, _validate_availability,
)
from subsystems.scheduling.matching_notification_contracts import MatchingContactState, MatchingSegmentContact
from subsystems.scheduling.segmented_availability_query import (
    search_segmented_caregiver_availability,
)
from api.routes.caregiver_segment_availability import CaregiverCandidateOption


class _Facts:
    def load_case_facts(self, _case_no):
        return {
            "order": {
                "case_no": "CASE-68",
                "status": "洽談中",
                "start_date": "2026-08-02",
                "end_date": "2026-08-04",
                "scheduling_version": 9,
                "service_days": 2,
                "requires_cooking": False,
            },
            "confirmed_service_dates": [
                {"service_date": "2026-08-02"},
                {"service_date": "2026-08-04"},
            ],
            "staff_rows": [{"id": 7, "name": "月嫂甲"}],
            "assignments": [],
            "schedule_rows": [],
            "legacy_schedule_rows": [],
            "buffer_rows": [],
            "active_lock_rows": [],
            "waiting_buffer_rows": [],
        }


def test_candidate_coverage_uses_confirmed_service_dates_and_backend_ranges():
    result = search_segmented_caregiver_availability(
        "CASE-68",
        1,
        [{"start_date": "2026-08-02", "end_date": "2026-08-04"}],
        "2026-08-01",
        _Facts(),
        filter_policy={
            "region": False,
            "preferred_service_days": False,
            "cooking": False,
            "daily_service_hours": False,
        },
    )

    candidate = result["candidate_options"][0]
    assert candidate["staff_name"] == "月嫂甲"
    assert candidate["coverage_day_count"] == 2
    assert candidate["required_service_dates"] == ["2026-08-02", "2026-08-04"]
    assert candidate["supported_ranges"] == [
        {"start_date": "2026-08-02", "end_date": "2026-08-02", "service_day_count": 1},
        {"start_date": "2026-08-04", "end_date": "2026-08-04", "service_day_count": 1},
    ]
    assert candidate["full_case_coverage"] is True
    assert candidate["full_selected_segment_coverage"] is True
    assert candidate["source_scheduling_version"] == 9
    assert CaregiverCandidateOption.model_validate(candidate).supported_day_count == 2


def test_candidate_option_accepts_zero_coverage_for_partial_search_diagnostics():
    candidate = {
        "segment_index": 0,
        "staff_id": 7,
        "staff_name": "月嫂甲",
        "coverage_day_count": 0,
        "available_ranges": [],
        "case_period_start": "2026-08-02",
        "case_period_end": "2026-08-04",
        "required_service_dates": ["2026-08-02"],
        "supported_service_dates": [],
        "supported_ranges": [],
        "supported_day_count": 0,
        "required_day_count": 1,
        "full_case_coverage": False,
        "selected_segment_start": "2026-08-02",
        "selected_segment_end": "2026-08-04",
        "full_selected_segment_coverage": False,
        "uncovered_segment_dates": ["2026-08-02"],
        "source_scheduling_version": 9,
        "filter_results": {"schedule": True},
        "matching_conditions": {
            "region": {"status": "pending", "required_value": None, "staff_values": []},
            "preferred_service_days": {"status": "pending", "required_value": None, "staff_values": []},
        },
    }

    assert CaregiverCandidateOption.model_validate(candidate).coverage_day_count == 0


class _ExtendedDates:
    def __init__(self):
        self.facts = _Facts().load_case_facts("CASE-68")
        self.facts["order"].update(start_date="2026-11-09", end_date="2026-11-28", service_days=20)
        self.facts["confirmed_service_dates"] = [
            {"service_date": (date(2026, 11, 9) + timedelta(days=offset)).isoformat()}
            for offset in range(26) if (date(2026, 11, 9) + timedelta(days=offset)).weekday() < 5
        ]

    def load_case_facts(self, _case_no):
        return self.facts


def _recommendation():
    return MatchingContactState(
        MatchingPlanReference("CASE-68", 10, 0), "proposed", True, "洽談中", None,
        CustomerMatchingDecision.PENDING, None,
        (MatchingSegmentContact(20, 1, 7, "測試月嫂", None, "2026-11-09", "2026-11-28", CaregiverWillingness.WILLING),),
    )


def test_single_recommendation_uses_all_saved_dates_without_rewriting_inquiry():
    facts = _ExtendedDates()
    state = _recommendation()
    _validate_availability(state, facts)
    assert state.segments[0].assigned_end_date == "2026-11-28"
    result = search_segmented_caregiver_availability(
        "CASE-68", 1, [{"staff_id": 7}], "2026-10-29", facts, include_candidate_options=False,
    )
    assert result["feasibility"] == "complete"
    assert (result["planned_start_date"], result["planned_end_date"]) == ("2026-11-09", "2026-12-04")
    assert result["conflicts"] == []


@pytest.mark.parametrize("source,row", [
    ("assignments", {"id": 90, "staff_id": 7, "assigned_start_date": "2026-12-02", "assigned_end_date": "2026-12-02"}),
    ("schedule_rows", {"assignment_id": 90, "staff_id": 7, "work_date": "2026-12-02"}),
    ("active_lock_rows", {"staff_id": 7, "lock_date": "2026-12-02", "active_marker": 1}),
    ("staff_unavailability_rows", {"id": 90, "staff_id": 7, "start_date": "2026-12-02", "end_date": "2026-12-02"}),
])
def test_actual_occupancy_after_original_inquiry_end_still_blocks(source, row):
    facts = _ExtendedDates()
    facts.facts[source] = [row]
    with pytest.raises(MatchingDecisionNotReadyError) as caught:
        _validate_availability(_recommendation(), facts)
    assert "檔期已有衝突" in _availability_blocker(caught.value)


def test_buffer_is_advisory_but_unowned_schedule_is_not_reported_as_proven_occupancy():
    facts = _ExtendedDates()
    facts.facts["buffer_rows"] = [{"assignment_id": 90, "staff_id": 7, "buffer_date": "2026-12-02"}]
    _validate_availability(_recommendation(), facts)
    facts.facts["legacy_schedule_rows"] = [{"staff_id": 7, "work_date": "2026-12-02"}]
    with pytest.raises(ValueError) as caught:
        _validate_availability(_recommendation(), facts)
    assert not isinstance(caught.value, MatchingDecisionNotReadyError)
    assert "無法驗證" in _availability_blocker(caught.value)


def test_multiple_caregiver_date_gap_is_a_plan_problem_not_occupancy():
    facts = _ExtendedDates()
    facts.facts["staff_rows"].append({"id": 8, "name": "測試月嫂乙"})
    state = _recommendation()
    first = replace(state.segments[0], assigned_end_date="2026-11-18")
    second = replace(first, segment_id=21, segment_order=2, staff_id=8,
                     assigned_start_date="2026-11-19", assigned_end_date="2026-11-28")
    with pytest.raises(MatchingPlanDateMismatchError) as caught:
        _validate_availability(replace(state, segments=(first, second)), facts)
    assert "分段" in _availability_blocker(caught.value)
    assert "檔期已有衝突" not in _availability_blocker(caught.value)


def test_invalid_saved_date_count_fails_as_date_validation():
    facts = _ExtendedDates()
    facts.facts["confirmed_service_dates"].pop()
    with pytest.raises(ValueError, match="current confirmed service dates mismatch"):
        _validate_availability(_recommendation(), facts)
