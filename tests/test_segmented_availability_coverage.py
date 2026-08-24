"""
File: test_segmented_availability_coverage.py
Description: 驗證媒合候選覆蓋率使用已確認服務日與後端日期區間。
"""

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
    }

    assert CaregiverCandidateOption.model_validate(candidate).coverage_day_count == 0
