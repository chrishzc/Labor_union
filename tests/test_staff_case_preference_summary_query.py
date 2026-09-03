from __future__ import annotations

import pytest

from infrastructure.mysql.staff_case_preference_summary_query_repository import (
    MySqlStaffCasePreferenceSummaryQueryRepository,
)
from subsystems.staff.case_preference_summary_query import (
    StaffCasePreferenceSummaryContractError,
    StaffCasePreferenceSummaryNotFoundError,
    StaffCasePreferenceSummaryQueryApplication,
    StaffCasePreferenceSummaryQueryRequest,
)


def _topic(*rows):
    return tuple({"value": value, "other_detail": detail} for value, detail in rows)


def _canonical_topics():
    return {
        "service_regions": _topic(
            ("苗栗縣", None),
            ("北區", None),
            ("北區", None),
            ("其他", " 新竹市 "),
        ),
        "service_periods": _topic(("8小時", None)),
        "rest_schedule": (),
        "baby_counts": _topic(("雙胞胎", None), ("單胞胎", None)),
        "holiday_availability": _topic(("中秋節", None)),
        "transportation": _topic(("轎車", None), ("機車", None), ("其他", None)),
    }


class _Repository:
    def __init__(self, rows):
        self.rows = rows
        self.staff_id = None

    def fetch_topics(self, *, staff_id):
        self.staff_id = staff_id
        return self.rows


def test_application_projects_six_topics_with_owner_order_and_fallbacks():
    repository = _Repository(_canonical_topics())
    application = StaffCasePreferenceSummaryQueryApplication(repository)

    result = application.query(StaffCasePreferenceSummaryQueryRequest(staff_id=11))

    assert repository.staff_id == 11
    assert result.service_regions.values == ("北區", "苗栗縣")
    assert result.service_regions.other_detail == "新竹市"
    assert result.service_regions.other_detail_status == "ready"
    assert result.service_periods.values == ("8小時",)
    assert result.service_periods.other_detail_status == "not_recorded"
    assert result.rest_schedule.values == ()
    assert result.rest_schedule.other_detail_status == "not_recorded"
    assert result.baby_counts.values == ("單胞胎", "雙胞胎")
    assert result.transportation.values == ("機車", "轎車")
    assert result.transportation.other_detail is None
    assert result.transportation.other_detail_status == "source_not_ready"


def test_application_degrades_only_unavailable_topic():
    rows = _canonical_topics()
    rows["service_periods"] = None

    result = StaffCasePreferenceSummaryQueryApplication(_Repository(rows)).query(
        StaffCasePreferenceSummaryQueryRequest(staff_id=11)
    )

    assert result.service_periods.values == ()
    assert result.service_periods.other_detail is None
    assert result.service_periods.other_detail_status == "source_not_ready"
    assert result.service_regions.values == ("北區", "苗栗縣")
    assert result.baby_counts.values == ("單胞胎", "雙胞胎")


def test_application_keeps_other_detail_topic_local_even_without_other_marker():
    rows = _canonical_topics()
    rows["holiday_availability"] = _topic(("中秋節", "只屬節日母題"))

    result = StaffCasePreferenceSummaryQueryApplication(_Repository(rows)).query(
        StaffCasePreferenceSummaryQueryRequest(staff_id=11)
    )

    assert result.holiday_availability.values == ("中秋節",)
    assert result.holiday_availability.other_detail == "只屬節日母題"
    assert result.transportation.other_detail is None


def test_application_rejects_conflicting_same_topic_other_details():
    rows = _canonical_topics()
    rows["service_regions"] = _topic(
        ("其他", "新竹市"),
        ("北區", "竹北市"),
    )

    with pytest.raises(StaffCasePreferenceSummaryContractError, match="conflicting"):
        StaffCasePreferenceSummaryQueryApplication(_Repository(rows)).query(
            StaffCasePreferenceSummaryQueryRequest(staff_id=11)
        )


def test_application_rejects_generic_or_cross_topic_repository_fields():
    rows = _canonical_topics()
    rows["service_regions"] = (
        {"value": "北區", "other_detail": None, "other_note": "不得存在"},
    )

    with pytest.raises(StaffCasePreferenceSummaryContractError, match="not canonical"):
        StaffCasePreferenceSummaryQueryApplication(_Repository(rows)).query(
            StaffCasePreferenceSummaryQueryRequest(staff_id=11)
        )


def test_application_has_explicit_missing_staff_semantics():
    with pytest.raises(StaffCasePreferenceSummaryNotFoundError):
        StaffCasePreferenceSummaryQueryApplication(_Repository(None)).query(
            StaffCasePreferenceSummaryQueryRequest(staff_id=404)
        )


class _Cursor:
    def __init__(self, *, exists=True):
        self.exists = exists
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False

    def execute(self, sql, params):
        self.executions.append((sql, params))

    def fetchone(self):
        return {"id": 11} if self.exists else None

    def fetchall(self):
        return [
            {
                "topic": "service_regions",
                "value": "北區",
                "other_detail": None,
            },
            {
                "topic": "service_regions",
                "value": "其他",
                "other_detail": "新竹市",
            },
            {
                "topic": "transportation",
                "value": "機車",
                "other_detail": None,
            },
        ]


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def test_mysql_projection_reads_only_canonical_staff_relation_facts():
    cursor = _Cursor()
    repository = MySqlStaffCasePreferenceSummaryQueryRepository(_Connection(cursor))

    result = repository.fetch_topics(staff_id=11)

    assert result is not None
    assert result["service_regions"][1]["other_detail"] == "新竹市"
    assert len(cursor.executions) == 2
    sql, params = cursor.executions[1]
    assert params == (11, 11, 11, 11, 11, 11)
    for table in (
        "staff_regions",
        "staff_time_slots",
        "staff_weekly_rest",
        "staff_baby_types",
        "staff_holiday_availability",
        "staff_transportation",
    ):
        assert table in sql
    assert "staff_cooking_skills" not in sql
    assert "custom_region_detail" in sql
    assert "custom_slot_detail" in sql
    assert "custom_rest_detail" in sql
    assert "custom_baby_detail" in sql
    assert "custom_holiday_detail" in sql
    assert "transportation_other" not in sql
    assert "identity_card" not in sql
    assert "bank" not in sql.lower()
    assert "admin_notes" not in sql


def test_mysql_projection_missing_staff_does_not_read_relation_tables():
    cursor = _Cursor(exists=False)
    repository = MySqlStaffCasePreferenceSummaryQueryRepository(_Connection(cursor))

    assert repository.fetch_topics(staff_id=404) is None
    assert len(cursor.executions) == 1
