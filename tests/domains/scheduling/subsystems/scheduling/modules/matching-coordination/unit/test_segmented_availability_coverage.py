"""
File: test_segmented_availability_coverage.py
Description: 驗證媒合候選覆蓋率使用已確認服務日與後端日期區間。
"""

from dataclasses import replace
from datetime import date, time, timedelta

import pytest
from domains.orders.terms import ServiceTimeTerms

from domains.scheduling.matching_communication import (
    CaregiverWillingness, CustomerMatchingDecision, MatchingDecisionNotReadyError, MatchingPlanReference,
)
from subsystems.scheduling.matching_notification_application import (
    MatchingPlanDateMismatchError, _availability_blocker, _validate_availability,
)
from subsystems.scheduling.matching_notification_contracts import MatchingContactState, MatchingSegmentContact
from subsystems.scheduling.segmented_availability_query import (
    search_candidate_inquiry_availability,
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
                "service_time": ServiceTimeTerms(time(8), time(12), 0),
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


@pytest.mark.parametrize("has_historical_reservation", [False, True])
def test_candidate_coverage_uses_confirmed_service_dates_and_backend_ranges(has_historical_reservation):
    class Facts(_Facts):
        def load_case_facts(self, case_no):
            facts = super().load_case_facts(case_no)
            if has_historical_reservation:
                facts["historical_reservation_rows"] = [
                    {"case_no": "HIS-1", "staff_id": 7,
                     "start_date": date(2026, 8, 2), "end_date": date(2026, 8, 2)},
                ]
            return facts

    result = search_segmented_caregiver_availability(
        "CASE-68",
        1,
        [{"start_date": "2026-08-02", "end_date": "2026-08-04",
          **({"staff_id": 7} if has_historical_reservation else {})}],
        "2026-08-01",
        Facts(),
        filter_policy={
            "region": False,
            "preferred_service_days": False,
            "cooking": False,
            "daily_service_hours": False,
        },
    )

    if has_historical_reservation:
        assert any(item["reason_code"] == "historical_reservation" for item in result["conflicts"])
        assert result["feasibility"] == "complete"

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


@pytest.mark.parametrize("source,row,period", [
    ("schedule_rows", {"assignment_id": 90, "staff_id": 7, "work_date": "2026-12-01",
                       "service_time": ServiceTimeTerms(time(21), time(9), 1)},
     "服務班次）2026-12-01 21:00 至 2026-12-02 09:00"),
    ("active_lock_rows", {"staff_id": 7, "lock_date": "2026-12-02", "active_marker": 1,
                          "service_time": ServiceTimeTerms(time(11), time(15), 0)},
     "其他案件保留）2026-12-02 11:00 至 2026-12-02 15:00"),
    ("staff_unavailability_rows", {"id": 90, "staff_id": 7, "start_date": "2026-12-02", "end_date": None},
     "不可服務期間）2026-12-02 至 未定"),
    ("historical_reservation_rows", {"case_no": "OTHER", "staff_id": 7,
                                     "start_date": "2026-12-02", "end_date": "2026-12-06"},
     "歷史預定）2026-12-02 至 2026-12-06"),
])
def test_actual_occupancy_after_original_inquiry_end_names_caregiver_and_period(source, row, period):
    facts = _ExtendedDates()
    facts.facts[source] = [row]
    if source in {"historical_reservation_rows", "active_lock_rows"}:
        _validate_availability(_recommendation(), facts)
        return
    with pytest.raises(MatchingDecisionNotReadyError) as caught:
        _validate_availability(_recommendation(), facts)
    message = _availability_blocker(caught.value)
    assert "檔期已有衝突" in message
    assert f"測試月嫂（{period}" in message


def test_disjoint_same_day_shift_and_reservation_keep_recommendation_available():
    facts = _ExtendedDates()
    afternoon = ServiceTimeTerms(time(13), time(17), 0)
    facts.facts["schedule_rows"] = [{"assignment_id": 90, "staff_id": 7, "work_date": "2026-12-02", "service_time": afternoon}]
    facts.facts["active_lock_rows"] = [{"staff_id": 7, "lock_date": "2026-12-03", "active_marker": 1, "service_time": afternoon}]
    _validate_availability(_recommendation(), facts)
    facts.facts["assignments"] = [{"id": 90, "staff_id": 7, "assigned_start_date": "2026-12-02", "assigned_end_date": "2026-12-02"}]
    with pytest.raises(ValueError, match="時段待確認"):
        _validate_availability(_recommendation(), facts)


def test_buffer_is_advisory_but_unowned_schedule_is_not_reported_as_proven_occupancy():
    facts = _ExtendedDates()
    facts.facts["buffer_rows"] = [{"assignment_id": 90, "staff_id": 7, "buffer_date": "2026-12-02"}]
    _validate_availability(_recommendation(), facts)
    facts.facts["legacy_schedule_rows"] = [{"staff_id": 7, "work_date": "2026-12-02"}]
    with pytest.raises(ValueError) as caught:
        _validate_availability(_recommendation(), facts)
    assert not isinstance(caught.value, MatchingDecisionNotReadyError)
    assert "時段待確認" in _availability_blocker(caught.value)
    assert "檔期已有衝突" not in _availability_blocker(caught.value)


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
    with pytest.raises(ValueError, match="current confirmed service dates mismatch") as caught:
        _validate_availability(_recommendation(), facts)
    assert "服務日期與分段" in _availability_blocker(caught.value)


@pytest.mark.parametrize("current_actual,other_actual,blocked", [
    (None, None, False), (None, "2026-08-02", False),
    ("2026-08-02", None, False), ("2026-08-02", "2026-08-02", True),
])
def test_only_two_actual_start_cases_block_matching_and_retain_source_shift(current_actual, other_actual, blocked):
    from subsystems.scheduling.matching_plan_workflow import (
        MatchingPlanAvailabilityConflict, _validate_current_availability,
    )
    class Facts(_Facts):
        def load_case_facts(self, case_no):
            facts = super().load_case_facts(case_no)
            facts["order"]["actual_start_date"] = current_actual
            facts["schedule_rows"] = [{"assignment_id": 90, "case_no": "OTHER", "staff_id": 7,
                "work_date": "2026-08-02", "actual_start_date": other_actual,
                "assigned_start_date": date(2026, 7, 30), "assigned_end_date": date(2026, 8, 7),
                "service_time": ServiceTimeTerms(time(8), time(12), 0)}]
            return facts
    facts = Facts()
    result = search_segmented_caregiver_availability("CASE-68", 1, [{"staff_id": 7}], "2026-08-01", facts)
    conflict = next(item for item in result["conflicts"] if item.get("case_no") == "OTHER")
    assert conflict["reason_code"] == ("schedule" if blocked else "historical_reservation")
    assert conflict["actual_start_date"] == other_actual
    assert conflict["service_start_at"] == "2026-08-02T08:00:00+08:00"
    assert conflict["service_end_at"] == "2026-08-02T12:00:00+08:00"
    assert "assignment_start_date" not in conflict
    assert "assignment_end_date" not in conflict
    assert result["feasibility"] == ("partial" if blocked else "complete")
    inquiry = search_candidate_inquiry_availability(
        "CASE-68", [{"staff_id": 7}], "2026-08-01", facts, include_assignment_dates=True,
    )
    assert inquiry["candidate_options"][0]["full_case_coverage"] is (not blocked)
    inquiry_conflict, = [item for item in inquiry["conflicts"] if item.get("case_no") == "OTHER"]
    assert inquiry_conflict["work_date"] == "2026-08-02"
    assert inquiry_conflict["reason_code"] == ("schedule" if blocked else "historical_reservation")
    if blocked:
        assert inquiry_conflict["assignment_start_date"] == "2026-07-30"
        assert inquiry_conflict["assignment_end_date"] == "2026-08-07"
    else:
        assert "assignment_start_date" not in inquiry_conflict
        assert "assignment_end_date" not in inquiry_conflict
    segments = [{"staff_id": 7, "assigned_start_date": "2026-08-02", "assigned_end_date": "2026-08-04"}]
    if blocked:
        with pytest.raises(MatchingPlanAvailabilityConflict) as captured:
            _validate_current_availability("CASE-68", segments, "2026-08-01", facts, False)
        assert any(item.case_no == "OTHER" and item.service_end_at == conflict["service_end_at"]
                   for item in captured.value.conflicts)
    else:
        _validate_current_availability("CASE-68", segments, "2026-08-01", facts, False)


@pytest.mark.parametrize("source", ["unknown_source_time", "unknown_requested_time", "assignment_without_shift"])
def test_schedule_review_retains_known_case_and_shift_evidence(source):
    class Facts(_Facts):
        def load_case_facts(self, case_no):
            facts = super().load_case_facts(case_no)
            facts["order"]["actual_start_date"] = "2026-08-02"
            other = {"case_no": "OTHER", "staff_id": 7, "actual_start_date": "2026-08-01"}
            if source == "assignment_without_shift":
                facts["assignments"] = [{
                    **other, "id": 90, "owner_case_no": "OTHER",
                    "assigned_start_date": "2026-08-02", "assigned_end_date": "2026-08-02",
                }]
            else:
                if source == "unknown_requested_time":
                    facts["order"]["service_time"] = None
                facts["schedule_rows"] = [{
                    **other, "assignment_id": 90, "work_date": "2026-08-02",
                    "service_time": ServiceTimeTerms(time(8), time(12), 0)
                    if source == "unknown_requested_time" else None,
                }]
            return facts

    result = search_segmented_caregiver_availability("CASE-68", 1, [{"staff_id": 7}], "2026-08-01", Facts())
    assert result["feasibility"] == "partial"
    conflict, = [item for item in result["conflicts"] if item["reason_code"] == "requires_review"]
    assert conflict["case_no"] == "OTHER"
    assert conflict["actual_start_date"] == "2026-08-01"
    if source == "unknown_requested_time":
        assert conflict["service_start_at"] == "2026-08-02T08:00:00+08:00"
        assert conflict["service_end_at"] == "2026-08-02T12:00:00+08:00"
    else:
        assert conflict["service_start_at"] is None
        assert conflict["service_end_at"] is None


@pytest.mark.parametrize("current_actual,other_actual", [(None, None), ("2026-08-02", None), (None, "2026-08-02"), ("2026-08-02", "2026-08-02")])
@pytest.mark.parametrize("known_time", [False, True])
def test_waiting_deposit_is_visible_advisory_for_all_actual_start_states(current_actual, other_actual, known_time):
    from subsystems.scheduling.matching_plan_workflow import _validate_current_availability
    class Facts(_Facts):
        def load_case_facts(self, case_no):
            facts = super().load_case_facts(case_no)
            facts["order"]["actual_start_date"] = current_actual
            facts["active_lock_rows"] = [{"staff_id": 7, "case_no": "WAITING", "lock_date": "2026-08-02",
                "active_marker": 1, "actual_start_date": other_actual,
                "service_time": ServiceTimeTerms(time(8), time(12), 0) if known_time else None}]
            return facts
    facts = Facts()
    result = search_segmented_caregiver_availability("CASE-68", 1, [{"staff_id": 7}], "2026-08-01", facts)
    assert result["feasibility"] == "complete"
    conflict, = result["conflicts"]
    assert conflict["reason_code"] == "active_lock" and conflict["case_no"] == "WAITING"
    assert conflict["actual_start_date"] == other_actual
    assert conflict["service_start_at"] == ("2026-08-02T08:00:00+08:00" if known_time else None)
    _validate_current_availability("CASE-68", [{"staff_id": 7, "assigned_start_date": "2026-08-02", "assigned_end_date": "2026-08-04"}], "2026-08-01", facts, False)


def test_unknown_historical_candidate_time_is_not_fabricated():
    class Facts(_Facts):
        def load_case_facts(self, case_no):
            facts = super().load_case_facts(case_no)
            facts["historical_reservation_rows"] = [{"staff_id": 7, "case_no": "HISTORY", "start_date": "2026-08-02", "end_date": "2026-08-02"}]
            return facts
    result = search_segmented_caregiver_availability("CASE-68", 1, [{"staff_id": 7}], "2026-08-01", Facts())
    conflict, = result["conflicts"]
    assert conflict["service_start_at"] is None and conflict["service_end_at"] is None
