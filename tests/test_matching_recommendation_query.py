from datetime import date

from subsystems.scheduling.matching_recommendation_query import RecommendationFilters, RecommendationRequest, StaffCandidate, recommend_staff
from subsystems.scheduling.matching_recommendation_application import _recommendation_request


def test_time_filter_excludes_staff_without_the_required_slot() -> None:
    request = RecommendationRequest((date(2026, 8, 1),), "東區", False, "24小時", RecommendationFilters())
    candidates = (StaffCandidate(1, "甲", None, None, ("東區",), 1, ("8小時",), frozenset()), StaffCandidate(2, "乙", None, None, ("東區",), 1, ("24小時",), frozenset()))
    assert [item.staff_id for item in recommend_staff(request, candidates)] == [2]


def test_schedule_filter_excludes_canonical_occupied_dates() -> None:
    request = RecommendationRequest((date(2026, 8, 1),), "", False, "", RecommendationFilters())
    candidate = StaffCandidate(1, "甲", None, None, (), 1, (), frozenset({date(2026, 8, 1)}))
    assert recommend_staff(request, (candidate,)) == ()


def test_multiple_birth_preference_never_infers_requirement_from_client_free_text() -> None:
    request = _recommendation_request(
        {
            "planned_start_date": date(2026, 8, 1),
            "planned_end_date": date(2026, 8, 1),
            "city": "東區",
            "address": "測試路 1 號",
            "baby_info": "雙胞胎",
            "service_time": "24小時",
        },
        True,
        True,
        True,
        True,
    )

    assert request.requires_twins is False
