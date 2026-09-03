from __future__ import annotations

from dataclasses import fields

import pytest

from infrastructure.mysql.staff_case_preference_summary_query_repository import (
    MySqlStaffCasePreferenceSummaryQueryRepository,
)
from subsystems.staff.case_preference_summary_query import (
    PreferenceTopicFacts,
    StaffCasePreferenceFacts,
    StaffCasePreferenceSummaryContractError,
    StaffCasePreferenceSummaryQueryApplication,
)
from subsystems.staff.summary_query import StaffSummary


class _StubRepository:
    def __init__(self, facts: StaffCasePreferenceFacts | None) -> None:
        self.facts = facts
        self.calls: list[int] = []

    def fetch(self, staff_id: int) -> StaffCasePreferenceFacts | None:
        self.calls.append(staff_id)
        return self.facts


class _ScriptedCursor:
    def __init__(self, responses: list[list[dict[str, object]]]) -> None:
        self._responses = iter(responses)
        self._current: list[dict[str, object]] = []
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.executed.append((" ".join(sql.split()), params))
        self._current = next(self._responses)

    def fetchone(self):
        return None if not self._current else self._current[0]

    def fetchall(self):
        return tuple(self._current)


class _FakeConnection:
    def __init__(self, responses: list[list[dict[str, object]]]) -> None:
        self.cursor_instance = _ScriptedCursor(responses)

    def cursor(self):
        return self.cursor_instance


def _facts(
    *,
    staff_id: int = 531,
    service_regions: PreferenceTopicFacts = PreferenceTopicFacts(),
    service_periods: PreferenceTopicFacts = PreferenceTopicFacts(),
    rest_schedule: PreferenceTopicFacts = PreferenceTopicFacts(),
    baby_counts: PreferenceTopicFacts = PreferenceTopicFacts(),
    holiday_availability: PreferenceTopicFacts = PreferenceTopicFacts(),
    transportation: PreferenceTopicFacts = PreferenceTopicFacts(),
) -> StaffCasePreferenceFacts:
    return StaffCasePreferenceFacts(
        staff_id=staff_id,
        service_regions=service_regions,
        service_periods=service_periods,
        rest_schedule=rest_schedule,
        baby_counts=baby_counts,
        holiday_availability=holiday_availability,
        transportation=transportation,
    )


def test_query_projects_six_topics_with_owner_order_and_fallbacks() -> None:
    repository = _StubRepository(
        _facts(
            service_regions=PreferenceTopicFacts(
                ("苗栗縣", "北區", "AA", "北區", "其他", "ZZ"),
                ("偏遠地區需先確認交通", "偏遠地區需先確認交通"),
            ),
            service_periods=PreferenceTopicFacts(
                ("24小時", "4小時(上午8:30-12:30)"),
            ),
            rest_schedule=PreferenceTopicFacts(
                ("其他",),
                ("週三固定排休",),
            ),
            holiday_availability=PreferenceTopicFacts(("中秋節", "端午節")),
            transportation=PreferenceTopicFacts(
                ("轎車", "腳踏車", "機車", "機車"),
                ("不得顯示的未就緒來源",),
            ),
        )
    )

    result = StaffCasePreferenceSummaryQueryApplication(repository).get(531)

    assert result is not None
    assert result.staff_id == 531
    assert result.service_regions.values == ("北區", "苗栗縣", "AA", "ZZ")
    assert result.service_regions.other_detail == "偏遠地區需先確認交通"
    assert result.service_regions.other_detail_status == "ready"
    assert result.service_periods.values == ("4小時(上午8:30-12:30)", "24小時")
    assert result.service_periods.other_detail_status == "not_recorded"
    assert result.rest_schedule.values == ()
    assert result.rest_schedule.other_detail == "週三固定排休"
    assert result.rest_schedule.other_detail_status == "ready"
    assert result.baby_counts.values == ()
    assert result.baby_counts.other_detail is None
    assert result.baby_counts.other_detail_status == "not_recorded"
    assert result.holiday_availability.values == ("端午節", "中秋節")
    assert result.transportation.values == ("機車", "轎車", "腳踏車")
    assert result.transportation.other_detail is None
    assert result.transportation.other_detail_status == "source_not_ready"


def test_query_rejects_distinct_other_details_in_one_topic() -> None:
    repository = _StubRepository(
        _facts(
            service_regions=PreferenceTopicFacts(
                ("其他", "其他"),
                ("偏遠地區 A", "偏遠地區 B"),
            )
        )
    )

    with pytest.raises(
        StaffCasePreferenceSummaryContractError,
        match="other detail is ambiguous",
    ):
        StaffCasePreferenceSummaryQueryApplication(repository).get(531)


@pytest.mark.parametrize("staff_id", [0, -1, True, "531"])
def test_query_rejects_invalid_staff_id(staff_id: object) -> None:
    repository = _StubRepository(_facts())

    with pytest.raises(ValueError, match="must be a positive integer"):
        StaffCasePreferenceSummaryQueryApplication(repository).get(staff_id)  # type: ignore[arg-type]

    assert repository.calls == []


def test_query_returns_none_when_staff_is_missing() -> None:
    repository = _StubRepository(None)

    assert StaffCasePreferenceSummaryQueryApplication(repository).get(531) is None
    assert repository.calls == [531]


def test_query_rejects_repository_staff_identity_mismatch() -> None:
    repository = _StubRepository(_facts(staff_id=999))

    with pytest.raises(
        StaffCasePreferenceSummaryContractError,
        match="does not match requested staff",
    ):
        StaffCasePreferenceSummaryQueryApplication(repository).get(531)


def test_mysql_projection_reads_only_staff_owned_case_preference_relations() -> None:
    connection = _FakeConnection(
        [
            [{"id": 531}],
            [
                {"region_name": "新竹縣", "custom_region_detail": None},
                {"region_name": "其他", "custom_region_detail": "偏遠地區"},
            ],
            [{"slot_name": "8小時", "custom_slot_detail": None}],
            [{"rest_type": "週休1日", "custom_rest_detail": None}],
            [{"baby_type": "雙胞胎", "custom_baby_detail": None}],
            [{"holiday_name": "中秋節", "custom_holiday_detail": None}],
            [{"vehicle_type": "機車"}],
        ]
    )

    result = MySqlStaffCasePreferenceSummaryQueryRepository(connection).fetch(531)

    assert result == _facts(
        service_regions=PreferenceTopicFacts(("新竹縣", "其他"), ("偏遠地區",)),
        service_periods=PreferenceTopicFacts(("8小時",)),
        rest_schedule=PreferenceTopicFacts(("週休1日",)),
        baby_counts=PreferenceTopicFacts(("雙胞胎",)),
        holiday_availability=PreferenceTopicFacts(("中秋節",)),
        transportation=PreferenceTopicFacts(("機車",)),
    )
    executed_sql = [sql for sql, _params in connection.cursor_instance.executed]
    assert executed_sql == [
        "SELECT id FROM staff WHERE id=%s LIMIT 1",
        "SELECT region_name,custom_region_detail FROM staff_regions WHERE staff_id=%s",
        "SELECT slot_name,custom_slot_detail FROM staff_time_slots WHERE staff_id=%s",
        "SELECT rest_type,custom_rest_detail FROM staff_weekly_rest WHERE staff_id=%s",
        "SELECT baby_type,custom_baby_detail FROM staff_baby_types WHERE staff_id=%s",
        "SELECT holiday_name,custom_holiday_detail FROM staff_holiday_availability WHERE staff_id=%s",
        "SELECT vehicle_type FROM staff_transportation WHERE staff_id=%s",
    ]
    assert all("staff_cooking_skills" not in sql for sql in executed_sql)
    assert all(params == (531,) for _sql, params in connection.cursor_instance.executed)


def test_mysql_projection_does_not_read_relations_for_missing_staff() -> None:
    connection = _FakeConnection([[]])

    result = MySqlStaffCasePreferenceSummaryQueryRepository(connection).fetch(531)

    assert result is None
    assert connection.cursor_instance.executed == [
        ("SELECT id FROM staff WHERE id=%s LIMIT 1", (531,))
    ]


def test_basic_staff_summary_contract_remains_bounded() -> None:
    assert tuple(field.name for field in fields(StaffSummary)) == (
        "id",
        "name",
        "phone",
        "education",
    )
