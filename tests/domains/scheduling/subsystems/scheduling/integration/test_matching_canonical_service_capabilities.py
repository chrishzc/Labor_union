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
        else:
            table = sql.split("FROM ")[1].split()[0]
            if sql.startswith("DELETE"):
                column = sql.split(" AND ")[1].split("=")[0] if " AND " in sql else None
                self.tables[table] = [row for row in self.tables[table] if row["staff_id"] != params[0] or (column and row[column] != params[1])]
            self.rows = deepcopy(self.tables[table])

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


@pytest.mark.parametrize("numeric_preferences", [False, True])
def test_roster_save_changes_the_next_query_without_numeric_preference_sync(numeric_preferences):
    store = CanonicalStore()
    store.numeric_preferences = numeric_preferences
    before = deepcopy(store.tables)
    assert [item["staff_id"] for item in inquiry(store)] == [3]
    assert inquiry(store)[0]["staff_union_no"] == "A003"
    assert store.tables == before  # Query remains read-only.

    writer = MySqlStaffCasePreferenceManualRepository(store)
    relations = {key: () for key in RELATION_KEYS}
    relations.update({"service_periods": (RelationValue("12小時"),), "rest_schedule": (RelationValue("週休1日"),)})
    writer.replace_relations(3, relations, before=writer.load_relations(3, for_update=False))
    assert inquiry(store) == []
    assert inquiry(store, mode=False, hours=False)[0]["staff_id"] == 3
    store.order.update({"service_type": "休周日", "service_hours_per_day": Decimal("12.0")})
    assert [item["staff_id"] for item in inquiry(store)] == [3]
    assert not any("INSERT INTO staff_matching_preference" in sql for sql in store.statements)


def test_service_modes_do_not_use_total_day_count_and_formal_search_keeps_candidates():
    store = CanonicalStore()
    store.order["service_days"] = 60
    assert inquiry(store)[0]["filter_results"]["preferred_service_days"] is True
    store.order["service_type"] = "休周日"
    assert inquiry(store, hours=False) == []
    assert len(inquiry(store, mode=False)) == 1
    store.order["service_hours_per_day"] = Decimal("12.0")
    assert inquiry(store, mode=False) == []
    result = search_segmented_caregiver_availability(
        "CAPABILITY-1", 1, [], "2026-10-13", store,
        filter_policy={"region": False, "cooking": False},
    )
    assert result["candidate_options"][0]["filter_results"]["preferred_service_days"] is False
    assert result["candidate_options"][0]["filter_results"]["daily_service_hours"] is False


def test_validated_staff_clock_window_keeps_eight_service_hours_in_matching():
    store=CanonicalStore()
    store.tables['staff_time_slots']=[{'staff_id':3,'slot_name':'8小時(08:30-17:00)','custom_slot_detail':None}]
    assert [item['staff_id'] for item in inquiry(store)] == [3]
    store.order['service_hours_per_day']=Decimal('4.0')
    assert inquiry(store)==[]


@pytest.mark.parametrize("hours", [Decimal("8.5"), Decimal("NaN"), 0, True])
def test_inquiry_does_not_guess_non_integer_hours(hours):
    store = CanonicalStore()
    store.order["service_hours_per_day"] = hours
    assert inquiry(store) == []


def test_inquiry_keeps_missing_requirements_pending_but_rejects_unknown_modes():
    store = CanonicalStore()
    store.order.update({"service_type": None, "service_hours_per_day": None})
    store.tables["staff_time_slots"] = []
    store.tables["staff_weekly_rest"] = []
    assert len(inquiry(store)) == 1
    store.order["service_type"] = "依情況排休"
    assert inquiry(store) == []


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
