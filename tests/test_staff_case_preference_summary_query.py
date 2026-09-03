from __future__ import annotations

import pytest

from subsystems.staff.case_preference_summary_query import (
    StaffCasePreferenceSummaryContractError,
    StaffCasePreferenceSummaryNotFoundError,
    StaffCasePreferenceSummaryQueryRequest,
    StaffCasePreferenceSummaryQueryService,
)


def topic(*rows):
    return tuple({"value": value, "other_detail": detail} for value, detail in rows)


def canonical_topics():
    return {
        "service_regions": topic(("苗栗縣", None), ("北區", None), ("北區", None), ("其他", "新竹市")),
        "service_periods": topic(("8小時", None)),
        "rest_schedule": topic(("週休1日", None)),
        "baby_counts": topic(("雙胞胎", None), ("單胞胎", None)),
        "holiday_availability": topic(("中秋節", None)),
        "transportation": topic(("轎車", None), ("機車", None), ("其他", None)),
    }


class FakeRepository:
    def __init__(self, rows):
        self.rows = rows
        self.staff_id = None

    def fetch_topics(self, *, staff_id):
        self.staff_id = staff_id
        return self.rows


def test_projects_six_topics_with_owner_order_and_topic_local_other_detail():
    repository = FakeRepository(canonical_topics())
    service = StaffCasePreferenceSummaryQueryService(repository)

    result = service.query(StaffCasePreferenceSummaryQueryRequest(staff_id=11))

    assert repository.staff_id == 11
    assert result.service_regions.values == ("北區", "苗栗縣")
    assert result.service_regions.other_detail == "新竹市"
    assert result.service_regions.other_detail_status == "ready"
    assert result.baby_counts.values == ("單胞胎", "雙胞胎")
    assert result.transportation.values == ("機車", "轎車")
    assert result.transportation.other_detail is None
    assert result.transportation.other_detail_status == "source_not_ready"


def test_other_marker_without_detail_is_not_recorded_and_not_a_value():
    rows = canonical_topics()
    rows["service_regions"] = topic(("其他", None))
    result = StaffCasePreferenceSummaryQueryService(FakeRepository(rows)).query(
        StaffCasePreferenceSummaryQueryRequest(staff_id=11)
    )
    assert result.service_regions.values == ()
    assert result.service_regions.other_detail is None
    assert result.service_regions.other_detail_status == "not_recorded"


def test_empty_topic_is_not_recorded_without_guessing_values():
    rows = canonical_topics()
    rows["rest_schedule"] = ()
    result = StaffCasePreferenceSummaryQueryService(FakeRepository(rows)).query(
        StaffCasePreferenceSummaryQueryRequest(staff_id=11)
    )
    assert result.rest_schedule.values == ()
    assert result.rest_schedule.other_detail_status == "not_recorded"


def test_unknown_relation_fact_is_stably_appended_after_owner_order():
    rows = canonical_topics()
    rows["service_regions"] = topic(("Z區", None), ("北區", None), ("A區", None))
    result = StaffCasePreferenceSummaryQueryService(FakeRepository(rows)).query(
        StaffCasePreferenceSummaryQueryRequest(staff_id=11)
    )
    assert result.service_regions.values == ("北區", "A區", "Z區")


def test_conflicting_same_topic_other_details_fail_closed():
    rows = canonical_topics()
    rows["service_regions"] = topic(("其他", "新竹市"), ("其他", "竹北市"))
    with pytest.raises(StaffCasePreferenceSummaryContractError, match="conflicting other_detail"):
        StaffCasePreferenceSummaryQueryService(FakeRepository(rows)).query(
            StaffCasePreferenceSummaryQueryRequest(staff_id=11)
        )


def test_non_other_value_cannot_carry_other_detail():
    rows = canonical_topics()
    rows["service_regions"] = topic(("北區", "不得掛在一般值"))
    with pytest.raises(StaffCasePreferenceSummaryContractError, match="non-other"):
        StaffCasePreferenceSummaryQueryService(FakeRepository(rows)).query(
            StaffCasePreferenceSummaryQueryRequest(staff_id=11)
        )


def test_missing_staff_has_explicit_not_found_semantics():
    with pytest.raises(StaffCasePreferenceSummaryNotFoundError):
        StaffCasePreferenceSummaryQueryService(FakeRepository(None)).query(
            StaffCasePreferenceSummaryQueryRequest(staff_id=404)
        )
