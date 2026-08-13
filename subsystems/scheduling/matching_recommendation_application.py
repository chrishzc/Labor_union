"""Application boundary for the canonical read-only matching query."""

from datetime import date, timedelta
from typing import Mapping

from infrastructure.mysql.matching_recommendation_repository import MySqlMatchingRecommendationRepository
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.scheduling.matching_recommendation_query import (
    RecommendationFilters,
    RecommendationRequest,
    recommend_staff,
)


def query_matching_recommendations(
    case_no: str,
    *,
    filter_region: bool,
    filter_schedule: bool,
    filter_babies: bool,
    filter_time: bool,
) -> list[dict[str, object]]:
    connection = get_connection()
    try:
        repository = MySqlMatchingRecommendationRepository(connection)
        facts = repository.load_request_facts(case_no)
        if facts is None:
            return []
        request = _recommendation_request(facts, filter_region, filter_schedule, filter_babies, filter_time)
        return [item.as_legacy_payload() for item in recommend_staff(request, repository.load_candidates(request.service_dates))]
    finally:
        connection.close()


def _recommendation_request(
    facts: Mapping[str, object],
    filter_region: bool,
    filter_schedule: bool,
    filter_babies: bool,
    filter_time: bool,
) -> RecommendationRequest:
    service_dates = _service_dates(facts)
    filters = RecommendationFilters(filter_region, filter_schedule, filter_babies, filter_time)
    return RecommendationRequest(
        service_dates,
        _district(facts.get("city"), facts.get("address")),
        _requires_multiple_birth_care(facts),
        str(facts.get("service_time") or ""),
        filters,
    )


def _service_dates(facts: Mapping[str, object]) -> tuple[date, ...]:
    start = facts.get("planned_start_date")
    end = facts.get("planned_end_date")
    if end is None and isinstance(start, date):
        end = start + timedelta(days=int(facts.get("service_days") or 0) - 1)
    if not isinstance(start, date) or not isinstance(end, date):
        return ()
    return tuple(start + timedelta(days=index) for index in range((end - start).days + 1))


def _district(city: object, address: object) -> str:
    text = f"{city or ''}{address or ''}"
    districts = (
        "香山區", "東區", "北區", "竹北市", "竹東鎮", "新埔鎮", "關西鎮",
        "湖口鄉", "新豐鄉", "芎林鄉", "橫山鄉", "北埔鄉", "寶山鄉", "峨眉鄉",
        "尖石鄉", "五峰鄉", "頭份市", "竹南鎮",
    )
    return next((item for item in districts if item in text), str(city or ""))


def _requires_multiple_birth_care(facts: Mapping[str, object]) -> bool:
    """Only a future canonical Orders term may enable the optional preference."""
    birth_count = facts.get("required_baby_count")
    return isinstance(birth_count, int) and not isinstance(birth_count, bool) and birth_count >= 2
