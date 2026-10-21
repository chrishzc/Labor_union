"""Matching consumes the same canonical relations that the Staff writer saves."""

from copy import deepcopy
from decimal import Decimal

import pytest

from domains.scheduling.staff_matching_preferences import service_hours_matches, service_mode_matches
from domains.staff.case_preference_manual import RELATION_KEYS, RELATION_SPECS, RelationValue
from infrastructure.mysql.segmented_availability_repository import MySqlSegmentedAvailabilityFactsRepository
from infrastructure.mysql.staff_case_preference_manual_repository import MySqlStaffCasePreferenceManualRepository
from subsystems.scheduling.segmented_availability_query import (
    search_candidate_inquiry_availability, search_segmented_caregiver_availability,
)


class CanonicalStore:
    """Small SQL boundary double shared by the unchanged writer and query adapter."""

    def __init__(self):
        self.tables = {spec[0]: [] for spec in RELATION_SPECS.values()}
        self.tables["staff_time_slots"] = [{"staff_id": 3, "slot_name": "8小時", "custom_slot_detail": None}]
        self.tables["staff_weekly_rest"] = [{"staff_id": 3, "rest_type": "週休二日", "custom_rest_detail": None}]
        self.order = {
            "case_no": "CAPABILITY-1", "status": "洽談中", "start_date": "2026-10-26",
            "end_date": "2026-10-27", "service_days": 2, "service_hours_per_day": Decimal("8.0"),
            "service_type": "周休二日", "requires_cooking": None, "scheduling_version": 1,
        }
        self.rows = []
        self.statements = []
        self.numeric_preferences = True

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def close(self):
        pass

    def execute(self, sql, params=None):
        self.statements.append(sql)
        if "FROM orders o" in sql:
            assert "c.service_type" in sql
            self.rows = [deepcopy(self.order)]
        elif "FROM staff s" in sql:
            assert "s.union_no" in sql
            self.rows = [{"id": 3, "name": "測試月嫂", "union_no": "A003"}]
        elif "FROM staff_matching_preference_values" in sql:
            assert "d.preference_key NOT IN ('preferred_service_days','daily_service_hours')" in sql
            # An upstream port retaining conflicting legacy facts cannot override
            # the canonical capabilities either; the DB query excludes them.
            self.rows = [
                {"staff_id": 3, "preference_key": "preferred_service_days", "order_fact_key": "service_days",
                 "comparison_operator": "range_with_tolerance", "value_json": {"minimum": 99, "maximum": 99}},
                {"staff_id": 3, "preference_key": "daily_service_hours", "order_fact_key": "service_hours_per_day",
                 "comparison_operator": "contains_integer", "value_json": {"values": [24]}},
            ] if self.numeric_preferences else []
        elif sql.startswith("CALL `lu_nas_remove_"):
            table = sql.split("lu_nas_remove_", 1)[1].split("_v1", 1)[0]
            value_column, detail_column = next((spec[1], spec[2]) for spec in RELATION_SPECS.values() if spec[0] == table)
            self.tables[table] = [row for row in self.tables[table]
                                  if (row["staff_id"], row[value_column], row.get(detail_column)) != tuple(params)]
            self.rows = []
        else:
            table = sql.split("FROM ")[1].split()[0]
            if sql.startswith("DELETE"):
                column = sql.split(" AND ")[1].split("=")[0] if " AND " in sql else None
                self.tables[table] = [row for row in self.tables[table] if row["staff_id"] != params[0] or (column and row[column] != params[1])]
            self.rows = deepcopy(self.tables[table])

    def nextset(self):
        return None

    def executemany(self, sql, values):
        table = sql.split("INSERT INTO ")[1].split()[0]
        columns = sql.split("(")[1].split(")")[0].split(",")
        self.tables[table].extend(dict(zip(columns, row)) for row in values)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows

    def load_case_facts(self, case_no):
        adapter = MySqlSegmentedAvailabilityFactsRepository(lambda: self)
        return {
            "order": adapter._load_order(self, case_no), "staff_rows": adapter._load_active_staff(self),
            "confirmed_service_dates": [{"service_date": "2026-10-26"}, {"service_date": "2026-10-27"}],
            **{key: [] for key in ("assignments", "schedule_rows", "legacy_schedule_rows", "buffer_rows",
                                  "active_lock_rows", "waiting_buffer_rows", "staff_unavailability_rows")},
        }


def inquiry(store, *, mode=True, hours=True):
    return search_candidate_inquiry_availability(
        "CAPABILITY-1", [], "2026-10-13", store,
        filter_policy={"region": False, "cooking": False,
                       "preferred_service_days": mode, "daily_service_hours": hours,
                       "enabled_preference_keys": ["preferred_service_days", "daily_service_hours"]},
    )["candidate_options"]


def test_roster_save_updates_hints_and_preserves_imported_relations():
    store = CanonicalStore()
    store.tables["staff_regions"] = [{"staff_id": 3, "region_name": "桃園市", "custom_region_detail": "原登錄說明"}]
    store.tables["staff_cooking_skills"] = [{"staff_id": 3, "skill_name": "其他", "custom_skill_detail": "原下廚資訊"}]
    store.tables["staff_holiday_availability"] = [{"staff_id": 3, "holiday_name": "端午節", "custom_holiday_detail": None}]
    store.tables["staff_baby_types"] = [{"staff_id": 3, "baby_type": "單胞胎", "custom_baby_detail": None}]
    store.order.update(city="新竹市", service_type="週休一日")
    before = deepcopy(store.tables)
    option = inquiry(store)[0]
    assert option["staff_union_no"] == "A003"
    assert option["matching_conditions"]["preferred_service_days"] == {
        "status": "not_matched", "required_value": "週休一日", "staff_values": ["週休二日"],
    }
    assert option["matching_conditions"]["region"]["status"] == "not_matched"
    assert option["matching_conditions"]["region"]["staff_values"] == ["桃園市"]
    assert store.tables == before

    writer = MySqlStaffCasePreferenceManualRepository(store)
    relations = writer.load_relations(3, for_update=False)
    relations = {**relations, "rest_schedule": (RelationValue("週休1日"),)}
    writer.replace_relations(3, relations, before=writer.load_relations(3, for_update=False))
    assert inquiry(store)[0]["matching_conditions"]["preferred_service_days"]["status"] == "matched"
    for table in ("staff_time_slots", "staff_cooking_skills", "staff_holiday_availability", "staff_baby_types"):
        assert store.tables[table] == before[table]


def test_only_region_and_weekly_service_are_hints_for_inquiry_and_formal_queries():
    store = CanonicalStore()
    store.order.update(service_type="週休一日", requires_cooking=True, service_hours_per_day=Decimal("12"), city="新竹市")
    store.tables["staff_regions"] = [{"staff_id": 3, "region_name": "桃園市", "custom_region_detail": None}]
    for search in (
        lambda: search_candidate_inquiry_availability("CAPABILITY-1", [], "2026-10-21", store, filter_policy={
            "region": True, "cooking": True, "preferred_service_days": True, "daily_service_hours": True,
            "enabled_preference_keys": ["preferred_service_days", "daily_service_hours", "custom_preference"],
        }),
        lambda: search_segmented_caregiver_availability("CAPABILITY-1", 1, [], "2026-10-21", store),
    ):
        option = search()["candidate_options"][0]
        assert set(option["matching_conditions"]) == {"region", "preferred_service_days"}
        assert option["filter_results"] == {"region": False, "preferred_service_days": False}
    assert not any(table in sql for sql in store.statements for table in (
        "staff_time_slots", "staff_cooking_skills", "staff_matching_preference_values",
        "staff_holiday_availability", "staff_baby_types",
    ))


@pytest.mark.parametrize("required,rows,status,values", [
    (None, [], "pending", []),
    (None, [("週休二日", None)], "pending", ["週休二日"]),
    ("週休一日", [], "pending", []),
    ("依情況排休", [("週休二日", None)], "pending", ["週休二日"]),
    ("每月排休六天", [("其他", "可協調排休")], "pending", ["其他（可協調排休）"]),
    ("週休一日", [("其他", "依情況")], "pending", ["其他（依情況）"]),
    ("週休一日", [("週休二日", None), ("其他", "依情況")], "pending", ["週休二日", "其他（依情況）"]),
    ("週休一日", [("週休二日", None)], "not_matched", ["週休二日"]),
    ("周休二日", [("週一至週五", None)], "matched", ["週一至週五"]),
])
def test_weekly_hint_preserves_original_values_and_never_excludes(required, rows, status, values):
    store = CanonicalStore()
    store.order["service_type"] = required
    store.tables["staff_weekly_rest"] = [{"staff_id": 3, "rest_type": value, "custom_rest_detail": detail} for value, detail in rows]
    condition = inquiry(store)[0]["matching_conditions"]["preferred_service_days"]
    assert condition["status"] == status
    assert condition["staff_values"] == values
    assert condition["required_value"] == required


def test_missing_region_is_pending_and_unknown_cooking_does_not_block_formal_query():
    store = CanonicalStore()
    result = search_segmented_caregiver_availability("CAPABILITY-1", 1, [], "2026-10-21", store)
    assert result["candidate_options"][0]["matching_conditions"]["region"] == {
        "status": "pending", "required_value": None, "staff_values": [],
    }


def test_condition_projection_round_trips_through_the_closed_http_schema():
    from api.routes.caregiver_segment_availability import CaregiverSegmentAvailabilityResponse
    from pydantic import ValidationError

    store = CanonicalStore()
    store.order["service_type"] = "週休一日"
    store.order.update(city="新竹市", address="東區測試路7號")
    result = search_candidate_inquiry_availability("CAPABILITY-1", [], "2026-10-21", store)
    response = CaregiverSegmentAvailabilityResponse.model_validate(result)
    condition = response.candidate_options[0].matching_conditions.preferred_service_days
    assert condition.status == "not_matched"
    assert condition.staff_values == ["週休二日"]
    assert response.candidate_options[0].matching_conditions.region.required_value == "新竹市"
    assert "測試路7號" not in response.model_dump_json()
    result["candidate_options"][0]["matching_conditions"]["region"]["status"] = "unknown-status"
    with pytest.raises(ValidationError):
        CaregiverSegmentAvailabilityResponse.model_validate(result)


@pytest.mark.parametrize("required,options,matched", [
    ("周休二日", [("週休2日", None)], True),
    ("週休2日", [("週一至週五", None)], True),
    ("休周日", [("週休一日", None)], True),
    ("連續服務", [("連續服務", None)], True),
    ("週休二日", [("其他", "周休二日")], True),
    ("休周六", [("休周日", None)], False),
    ("休周日", [("週一至週五", None)], False),
    ("週休2日", [], False),
    ("依情況排休", [("依情況排休", None)], False),
])
def test_service_mode_comparisons(required, options, matched):
    assert service_mode_matches(required, options) is matched


@pytest.mark.parametrize("required,options,matched", [
    (8, [("8小時", None)], True),
    (4, [("4小時_上午", None)], True),
    (4, [("4小時(下午13:00-17:00)", None)], True),
    (24, [("24小時", None)], True),
    (12, [("其他", "12小時")], True),
    (8, [("8小時", "不得改成12小時")], True),
    (12, [("8小時", None)], False),
    (8, [("其他", "8或12小時")], False),
    (8, [], False),
    (True, [("1小時", None)], False),
])
def test_service_hours_comparisons(required, options, matched):
    assert service_hours_matches(required, options) is matched
