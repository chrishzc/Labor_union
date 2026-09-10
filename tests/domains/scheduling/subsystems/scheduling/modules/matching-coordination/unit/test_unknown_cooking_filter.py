"""Unknown cooking is not false; explicitly disabling that filter remains usable."""
from copy import deepcopy

import pytest

from subsystems.scheduling.segmented_availability_query import search_segmented_caregiver_availability, search_candidate_inquiry_availability


class Facts:
    def __init__(self, *, occupied=False):
        self.data = {
            "order": {"case_no": "INQUIRY-1", "status": "洽談中", "requires_cooking": None,
                      "start_date": "2026-10-05", "end_date": "2026-10-05", "scheduling_version": 1},
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
    assert result["candidate_options"][0]["filter_results"]["cooking"] is False
    assert facts.data == before


def test_enabled_cooking_filter_still_requires_known_requirement():
    with pytest.raises(ValueError, match="matching_preference_source_not_ready"):
        query(Facts(), cooking=True)


def test_disabling_cooking_does_not_override_unavailability():
    result = query(Facts(occupied=True), cooking=False)
    assert not any(item["full_case_coverage"] for item in result["candidate_options"])


def test_initial_inquiry_without_beclass_or_official_dates_preserves_source():
    facts = Facts()
    facts.data["confirmed_service_dates"] = []
    before = deepcopy(facts.data)
    result = search_candidate_inquiry_availability("INQUIRY-1", [], "2026-10-01", facts)
    assert result["candidate_options"][0]["full_case_coverage"] is True
    assert result["candidate_options"][0]["required_service_dates"] == ["2026-10-05"]
    assert facts.data == before
    with pytest.raises(ValueError, match="official_service_dates_incomplete"):
        query(facts, cooking=False)


def test_initial_inquiry_still_rejects_occupied_planned_days():
    facts = Facts(occupied=True)
    facts.data["confirmed_service_dates"] = []
    result = search_candidate_inquiry_availability("INQUIRY-1", [], "2026-10-01", facts)
    assert not any(item["full_case_coverage"] for item in result["candidate_options"])


def test_initial_inquiry_keeps_known_cooking_filter():
    facts = Facts()
    facts.data["confirmed_service_dates"] = []
    facts.data["order"]["requires_cooking"] = True
    result = search_candidate_inquiry_availability("INQUIRY-1", [], "2026-10-01", facts)
    assert result["candidate_options"] == []


def test_candidate_pool_fresh_check_uses_inquiry_not_official_dates(monkeypatch):
    from subsystems.scheduling import candidate_contact_pool_workflow as pool
    facts = Facts()
    facts.data["confirmed_service_dates"] = []
    monkeypatch.setattr(pool, "segmented_facts_port", facts)
    assert pool._require_full_coverage("INQUIRY-1", 3, "2026-10-05", "2026-10-05")["staff_id"] == 3
    facts.data["staff_unavailability_rows"] = Facts(occupied=True).data["staff_unavailability_rows"]
    with pytest.raises(ValueError, match="candidate_no_longer_fully_available"):
        pool._require_full_coverage("INQUIRY-1", 3, "2026-10-05", "2026-10-05")
