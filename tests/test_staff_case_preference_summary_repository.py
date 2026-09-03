from infrastructure.mysql.staff_case_preference_summary_query_repository import (
    MySqlStaffCasePreferenceSummaryQueryRepository,
)


class FakeCursor:
    def __init__(self, exists=True):
        self.exists = exists
        self.executions = []
        self.last_sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params):
        self.last_sql = sql
        self.executions.append((sql, params))

    def fetchone(self):
        return {"id": 11} if self.exists else None

    def fetchall(self):
        return [
            {"topic": "service_regions", "value": "北區", "other_detail": None},
            {"topic": "service_regions", "value": "其他", "other_detail": "新竹市"},
            {"topic": "transportation", "value": "機車", "other_detail": None},
        ]


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def test_repository_batch_reads_only_six_staff_owner_relations():
    cursor = FakeCursor()
    result = MySqlStaffCasePreferenceSummaryQueryRepository(FakeConnection(cursor)).fetch_topics(staff_id=11)

    assert result is not None
    assert set(result) == {
        "service_regions", "service_periods", "rest_schedule", "baby_counts",
        "holiday_availability", "transportation",
    }
    assert result["service_regions"][1]["other_detail"] == "新竹市"
    assert len(cursor.executions) == 2
    batch_sql, params = cursor.executions[1]
    assert params == (11, 11, 11, 11, 11, 11)
    for table in (
        "staff_regions", "staff_time_slots", "staff_weekly_rest",
        "staff_baby_types", "staff_holiday_availability", "staff_transportation",
    ):
        assert table in batch_sql
    assert "staff_cooking_skills" not in batch_sql
    assert "custom_region_detail" in batch_sql
    assert "custom_slot_detail" in batch_sql
    assert "custom_rest_detail" in batch_sql
    assert "custom_baby_detail" in batch_sql
    assert "custom_holiday_detail" in batch_sql
    assert "transportation_other" not in batch_sql


def test_repository_returns_none_without_querying_relations_when_staff_missing():
    cursor = FakeCursor(exists=False)
    result = MySqlStaffCasePreferenceSummaryQueryRepository(FakeConnection(cursor)).fetch_topics(staff_id=404)
    assert result is None
    assert len(cursor.executions) == 1
