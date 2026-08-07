from datetime import date

from subsystems.scheduling.matching_recommendation_query import RecommendationFilters, RecommendationRequest, StaffCandidate, recommend_staff


def test_time_filter_excludes_staff_without_the_required_slot() -> None:
    request = RecommendationRequest((date(2026, 8, 1),), "東區", False, "24小時", RecommendationFilters())
    candidates = (StaffCandidate(1, "甲", None, None, ("東區",), 1, ("8小時",), frozenset()), StaffCandidate(2, "乙", None, None, ("東區",), 1, ("24小時",), frozenset()))
    assert [item.staff_id for item in recommend_staff(request, candidates)] == [2]


def test_schedule_filter_excludes_canonical_occupied_dates() -> None:
    request = RecommendationRequest((date(2026, 8, 1),), "", False, "", RecommendationFilters())
    candidate = StaffCandidate(1, "甲", None, None, (), 1, (), frozenset({date(2026, 8, 1)}))
    assert recommend_staff(request, (candidate,)) == ()
