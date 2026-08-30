"""Focused Task 97 regressions for newly bounded Query projections."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from api.routes import match_records, matches
from api.schemas.matches import OrderMatchRecordView, StaffRecommendationView


def test_matching_recommendation_route_returns_closed_views(monkeypatch) -> None:
    monkeypatch.setattr(
        matches,
        "query_matching_recommendations",
        lambda **_kwargs: [
            {
                "staff_id": 7,
                "name": "測試月嫂",
                "phone": None,
                "line_user_id": None,
                "score": 100,
                "display_label": "測試月嫂 - 完全符合",
                "is_perfect": True,
                "reasons": ["符合區域", "檔期無衝突"],
                "reject_reasons": [],
            }
        ],
    )

    response = matches.recommend_staff("CASE-1", principal=object())

    assert isinstance(response.data[0], StaffRecommendationView)
    payload = response.data[0].model_dump()
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        StaffRecommendationView.model_validate(payload)


def test_match_record_route_returns_closed_views(monkeypatch) -> None:
    now = datetime(2026, 8, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(
        match_records.match_record_query,
        "get_order_match_records",
        lambda _case_no: [
            {
                "match_id": 9,
                "case_no": "CASE-1",
                "staff_id": 7,
                "caregiver_accepted": 1,
                "sent_info_1_at": now,
                "sent_info_2_at": None,
                "sent_resume_at": None,
                "staff_name": "測試月嫂",
                "staff_phone": None,
            }
        ],
    )

    response = match_records.get_order_matches("CASE-1", principal=object())

    assert isinstance(response.data[0], OrderMatchRecordView)
    assert response.data[0].caregiver_accepted == 1
