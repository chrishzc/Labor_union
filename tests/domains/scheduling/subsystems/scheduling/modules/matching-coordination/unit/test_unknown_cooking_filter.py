"""Legacy preference flags preserve intake facts and cannot exclude candidates."""
from copy import deepcopy
from decimal import Decimal

import pytest

from subsystems.scheduling.segmented_availability_query import search_segmented_caregiver_availability, search_candidate_inquiry_availability


class Facts:
    def __init__(self, *, occupied=False):
        self.data = {
            "order": {"case_no": "INQUIRY-1", "status": "洽談中", "requires_cooking": None,
                      "start_date": "2026-10-05", "end_date": "2026-10-05", "scheduling_version": 1, "service_days": 1},
            "staff_rows": [{"id": 3, "name": "測試月嫂"}],
            "confirmed_service_dates": [{"service_date": "2026-10-05"}],
            "assignments": [], "schedule_rows": [], "legacy_schedule_rows": [],
            "buffer_rows": [], "active_lock_rows": [], "waiting_buffer_rows": [],
            "staff_unavailability_rows": ([{"id": 1, "staff_id": 3, "start_date": "2026-10-05", "end_date": "2026-10-05"}] if occupied else []),
        }

    def load_case_facts(self, _case_no):
        return self.data


def query(facts, *, cooking):
    return search_segmented_caregiver_availability(
        case_no="INQUIRY-1", segment_count=1, segment_drafts=[], as_of="2026-10-01", facts_port=facts,
        filter_policy={"cooking": cooking, "region": False, "preferred_service_days": False, "daily_service_hours": False},
    )


def test_unknown_cooking_can_be_explicitly_excluded_without_changing_source():
    facts = Facts()
    before = deepcopy(facts.data)
    result = query(facts, cooking=False)
    assert result["candidate_options"][0]["staff_id"] == 3
    conditions = result["candidate_options"][0]["matching_conditions"]
    assert set(conditions) == {"region", "preferred_service_days"}
    assert {item["status"] for item in conditions.values()} == {"pending"}
    assert facts.data == before


def test_legacy_enabled_cooking_flag_does_not_block_unknown_requirement():
    facts = Facts()
    before = deepcopy(facts.data)
    assert query(facts, cooking=True)["candidate_options"][0]["staff_id"] == 3
    assert facts.data == before


def test_disabling_cooking_does_not_override_unavailability():
    result = query(Facts(occupied=True), cooking=False)
    assert not any(item["full_case_coverage"] for item in result["candidate_options"])


def test_initial_inquiry_without_beclass_or_official_dates_preserves_source():
    facts = Facts()
    facts.data["confirmed_service_dates"] = []
    before = deepcopy(facts.data)
    result = search_candidate_inquiry_availability(
        "INQUIRY-1", [], "2026-10-01", facts,
        filter_policy={"preferred_service_days": False, "daily_service_hours": False},
    )
    assert result["candidate_options"][0]["full_case_coverage"] is True
    assert result["candidate_options"][0]["required_service_dates"] == ["2026-10-05"]
    assert facts.data == before
    with pytest.raises(ValueError, match="official_service_dates_incomplete"):
        query(facts, cooking=False)


def test_initial_inquiry_still_rejects_occupied_planned_days():
    facts = Facts(occupied=True)
    facts.data["confirmed_service_dates"] = []
    result = search_candidate_inquiry_availability(
        "INQUIRY-1", [], "2026-10-01", facts,
        filter_policy={"preferred_service_days": False, "daily_service_hours": False},
    )
    assert len(result["candidate_options"]) == 1
    assert result["candidate_options"][0]["full_case_coverage"] is False


def test_initial_inquiry_preserves_known_cooking_without_excluding_candidates():
    facts = Facts()
    facts.data["confirmed_service_dates"] = []
    facts.data["order"]["requires_cooking"] = True
    result = search_candidate_inquiry_availability(
        "INQUIRY-1", [], "2026-10-01", facts,
        filter_policy={"preferred_service_days": False, "daily_service_hours": False},
    )
    assert [item["staff_id"] for item in result["candidate_options"]] == [3]
    assert facts.data["order"]["requires_cooking"] is True


def test_legacy_preference_flags_only_present_current_weekly_service_hints():
    facts = Facts()
    facts.data["order"].update({"service_days": 1, "service_type": "周休二日", "service_hours_per_day": Decimal("8.0")})

    def staff(staff_id, service_mode, hours):
        return {
            "id": staff_id,
            "name": f"月嫂{staff_id}",
            "rest_schedule": [(service_mode, None)],
            "service_periods": [(f"{hours}小時", None)],
        }

    facts.data["staff_rows"] = [
        staff(3, "週休2日", 8), staff(4, "週休1日", 8), staff(5, "週一至週五", 12),
        {"id": 6, "name": "未登錄偏好的月嫂"},
    ]

    def matching_ids(*, days, hours):
        result = search_candidate_inquiry_availability(
            "INQUIRY-1", [], "2026-10-01", facts,
            filter_policy={
                "region": False, "cooking": False,
                "preferred_service_days": days, "daily_service_hours": hours,
            },
        )
        return [item["staff_id"] for item in result["candidate_options"]]

    assert matching_ids(days=True, hours=True) == [3, 4, 5, 6]
    assert matching_ids(days=False, hours=True) == [3, 4, 5, 6]
    assert matching_ids(days=True, hours=False) == [3, 4, 5, 6]
    assert matching_ids(days=False, hours=False) == [3, 4, 5, 6]
    result = search_candidate_inquiry_availability("INQUIRY-1", [], "2026-10-01", facts)
    assert [(item["staff_id"], item["matching_conditions"]["preferred_service_days"]["status"])
            for item in result["candidate_options"]] == [
        (3, "matched"), (4, "not_matched"), (5, "matched"), (6, "pending"),
    ]

    facts.data["order"]["service_hours_per_day"] = None
    assert matching_ids(days=True, hours=True) == [3, 4, 5, 6]
    facts.data["order"]["service_type"] = None
    assert matching_ids(days=True, hours=True) == [3, 4, 5, 6]


def test_candidate_pool_fresh_check_uses_inquiry_not_official_dates(monkeypatch):
    from subsystems.scheduling import candidate_contact_pool_workflow as pool
    facts = Facts()
    facts.data["confirmed_service_dates"] = []
    monkeypatch.setattr(pool, "segmented_facts_port", facts)
    assert pool._require_current_candidate("INQUIRY-1", 3, "2026-10-05", "2026-10-05")["staff_id"] == 3
    facts.data["staff_unavailability_rows"] = Facts(occupied=True).data["staff_unavailability_rows"]
    candidate = pool._require_current_candidate("INQUIRY-1", 3, "2026-10-05", "2026-10-05")
    assert candidate["full_case_coverage"] is False
    assert candidate["supported_service_dates"] == []
    facts.data["staff_rows"] = []
    with pytest.raises(ValueError, match="not in candidate_staff_ids"):
        pool._require_current_candidate("INQUIRY-1", 3, "2026-10-05", "2026-10-05")


def test_assignment_and_waiting_buffers_are_advisory_for_selected_candidate():
    facts = Facts()
    facts.data["buffer_rows"] = [{"assignment_id": 9, "staff_id": 3, "buffer_date": "2026-10-05"}]
    result = query(facts, cooking=False)
    assert result["feasibility"] == "complete"
    assert result["candidate_options"][0]["full_case_coverage"] is True
    assert any(item["reason_code"] == "buffer" for item in result["conflicts"])
