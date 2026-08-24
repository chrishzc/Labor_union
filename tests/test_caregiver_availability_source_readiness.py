"""
File: test_caregiver_availability_source_readiness.py
Description: 驗證媒合查詢遇到下廚需求未知時 fail closed，並保留 true/false 篩選語意。
"""

from datetime import date

import pytest
from fastapi import HTTPException

from api.routes import caregiver_segment_availability as route
from subsystems.scheduling import segmented_availability_query as query


class _FactsPort:
    def __init__(self, requires_cooking, staff_rows, confirmed_service_dates=None):
        self.requires_cooking = requires_cooking
        self.staff_rows = staff_rows
        self.confirmed_service_dates = (
            [{"service_date": "2026-09-10"}]
            if confirmed_service_dates is None
            else confirmed_service_dates
        )

    def load_case_facts(self, case_no):
        return {
            "order": {
                "case_no": case_no,
                "status": "洽談中",
                "start_date": "2026-09-10",
                "end_date": "2026-09-10",
                "requires_cooking": self.requires_cooking,
            },
            "confirmed_service_dates": self.confirmed_service_dates,
            "staff_rows": self.staff_rows,
            "assignments": [],
            "schedule_rows": [],
            "legacy_schedule_rows": [],
            "buffer_rows": [],
            "active_lock_rows": [],
            "waiting_buffer_rows": [],
        }


def _search(monkeypatch, requires_cooking, staff_rows):
    captured = {}

    def fake_derive(**kwargs):
        captured["candidate_staff_ids"] = kwargs["candidate_staff_ids"]
        return {
            "validated_input": {
                "planned_start_date": kwargs["planned_start_date"],
                "planned_end_date": kwargs["planned_end_date"],
            },
            "complete_combinations": [],
            "segment_candidates": [],
            "conflicts": [],
        }

    monkeypatch.setattr(query, "derive_segment_availability", fake_derive)
    result = query.search_segmented_caregiver_availability(
        "116990823",
        1,
        [],
        date(2026, 9, 1),
        facts_port=_FactsPort(requires_cooking, staff_rows),
        filter_policy={
            "region": False,
            "preferred_service_days": False,
            "daily_service_hours": False,
        },
    )
    return result, captured


def test_unknown_cooking_requirement_is_not_reported_as_zero_candidates(monkeypatch):
    monkeypatch.setattr(
        query,
        "derive_segment_availability",
        lambda **_kwargs: pytest.fail("candidate calculation must not run"),
    )

    with pytest.raises(ValueError, match="^matching_preference_source_not_ready$"):
        query.search_segmented_caregiver_availability(
            "116990823",
            1,
            [],
            date(2026, 9, 1),
            facts_port=_FactsPort(None, [{"id": 531}]),
        )


def test_missing_exact_service_dates_fails_closed_instead_of_using_calendar_span(monkeypatch):
    monkeypatch.setattr(
        query,
        "derive_segment_availability",
        lambda **_kwargs: pytest.fail("candidate calculation must not run"),
    )

    with pytest.raises(ValueError, match="^official_service_dates_incomplete$"):
        query.search_segmented_caregiver_availability(
            "116990823",
            1,
            [],
            date(2026, 9, 1),
            facts_port=_FactsPort(False, [{"id": 531}], confirmed_service_dates=[]),
        )


@pytest.mark.parametrize(
    ("requires_cooking", "staff_rows", "expected_ids"),
    [
        (False, [{"id": 531, "cooking_skills": []}], [531]),
        (
            True,
            [
                {"id": 531, "cooking_skills": []},
                {"id": 532, "cooking_skills": ["家常菜"]},
            ],
            [532],
        ),
    ],
)
def test_known_cooking_requirement_keeps_existing_filter_semantics(
    monkeypatch, requires_cooking, staff_rows, expected_ids
):
    result, captured = _search(monkeypatch, requires_cooking, staff_rows)

    assert captured["candidate_staff_ids"] == expected_ids
    assert result["complete_combinations"] == []


def test_route_maps_unknown_cooking_requirement_to_typed_conflict(monkeypatch):
    monkeypatch.setattr(
        route,
        "search_segmented_caregiver_availability",
        lambda **_kwargs: (_ for _ in ()).throw(
            ValueError("matching_preference_source_not_ready")
        ),
    )
    request = route.CaregiverSegmentAvailabilitySearchRequest(
        segment_count=1,
        segment_drafts=[],
        as_of="2026-09-01",
    )

    with pytest.raises(HTTPException) as captured:
        route.search_caregiver_segment_availability(
            request=request,
            case_no="116990823",
            principal=None,
        )

    assert captured.value.status_code == 409
    assert captured.value.detail["error"]["category"] == "conflict"
    assert (
        captured.value.detail["error"]["code"]
        == "matching_preference_source_not_ready"
    )


def test_route_maps_missing_exact_service_dates_to_typed_conflict(monkeypatch):
    monkeypatch.setattr(
        route,
        "search_segmented_caregiver_availability",
        lambda **_kwargs: (_ for _ in ()).throw(
            ValueError("official_service_dates_incomplete")
        ),
    )
    request = route.CaregiverSegmentAvailabilitySearchRequest(
        segment_count=1,
        segment_drafts=[],
        as_of="2026-09-01",
    )

    with pytest.raises(HTTPException) as captured:
        route.search_caregiver_segment_availability(
            request=request,
            case_no="116990823",
            principal=None,
        )

    assert captured.value.status_code == 409
    assert captured.value.detail["error"]["category"] == "conflict"
    assert captured.value.detail["error"]["code"] == "official_service_dates_incomplete"
