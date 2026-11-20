"""Regression coverage for inquiry versus official service-date windows."""

from datetime import date, timedelta

import pytest

from domains.scheduling.matching_communication import CandidateMatchingError
from infrastructure.mysql.segmented_availability_repository import (
    MySqlSegmentedAvailabilityFactsRepository,
)
from subsystems.scheduling import segmented_availability_query as query


def _repository_facts(monkeypatch, *, start_date="2026-09-01", end_date="2026-09-03", service_days=3,
                      service_type=None, rest_dates=None, candidate_inquiry=False):
    repository = MySqlSegmentedAvailabilityFactsRepository(lambda: None, candidate_inquiry=candidate_inquiry)
    loaded_windows = []
    monkeypatch.setattr(
        repository,
        "_load_confirmed_service_dates",
        lambda _cursor, _case_no: [{"service_date": "2026-08-01"}],
    )
    monkeypatch.setattr(
        repository,
        "_load_active_staff",
        lambda _cursor: [{"id": 12, "name": "月嫂甲"}],
    )

    def load_window(_cursor, window_start, window_end):
        loaded_windows.append((window_start, window_end))
        return []

    for name in (
        "_load_assignments",
        "_load_assignment_schedule_rows",
        "_load_legacy_schedule_rows",
        "_load_buffer_rows",
        "_load_active_lock_rows",
        "_load_waiting_buffer_rows",
        "_load_staff_unavailability_rows",
    ):
        monkeypatch.setattr(repository, name, load_window)

    monkeypatch.setattr(
        "infrastructure.mysql.segmented_availability_repository.load_historical_reservation_rows",
        lambda _cursor, **_kwargs: [],
    )

    order = {
        "case_no": "CASE-RECONTACT",
        "status": "洽談中",
        "start_date": start_date,
        "end_date": end_date,
        "service_days": service_days,
        "service_type": service_type,
        "custom_rest_dates": rest_dates,
        "scheduling_version": 4,
        "requires_cooking": None,
    }
    return repository._load_negotiation_facts(object(), order), loaded_windows


def test_inquiry_projects_missing_end_from_orders_terms_without_confirming_dates(monkeypatch):
    facts, loaded_windows = _repository_facts(monkeypatch, end_date=None)
    assert facts["order"]["end_date"] == date(2026, 9, 3)
    result = query.search_candidate_inquiry_availability(
        "CASE-RECONTACT", [], "2026-08-31",
        facts_port=type("Facts", (), {"load_case_facts": lambda _self, _case_no: facts})(),
        filter_policy={"preferred_service_days": False, "daily_service_hours": False},
    )
    assert result["planned_end_date"] == "2026-09-03"
    assert result["candidate_options"][0]["required_service_dates"] == [
        "2026-09-01", "2026-09-02", "2026-09-03",
    ]
    assert facts["confirmed_service_dates"] == [{"service_date": "2026-08-01"}]
    assert set(loaded_windows) == {
        ("2026-08-01", "2026-09-03"),
        ("2026-07-31", "2026-09-04"),
    }


def test_missing_planned_end_uses_the_same_rest_rules_as_contract_dates(monkeypatch):
    facts, _ = _repository_facts(monkeypatch, end_date=None, service_days=5,
                                 service_type="週休2日", rest_dates='["2026-09-02"]',
                                 candidate_inquiry=True)
    assert facts["order"]["end_date"] == date(2026, 9, 8)
    assert facts["confirmed_service_dates"] == [{"service_date": "2026-08-01"}]


@pytest.mark.parametrize(("start", "end", "code"), [
    (None, None, "candidate_inquiry_dates_missing"),
    ("0000-00-00", "2026-09-03", "candidate_inquiry_dates_invalid"),
    ("2026-09-01", "2026-02-29", "candidate_inquiry_dates_invalid"),
    ("2026-09-01", "2026-08-31", "candidate_inquiry_dates_invalid"),
    ("2026-09-01", "2026-10-31", "candidate_inquiry_dates_too_long"),
])
def test_candidate_inquiry_rejects_unusable_orders_planning_dates(monkeypatch, start, end, code):
    with pytest.raises(CandidateMatchingError, match=code):
        _repository_facts(monkeypatch, start_date=start, end_date=end, candidate_inquiry=True)


def test_candidate_inquiry_rejects_selected_person_missing_from_active_roster(monkeypatch):
    facts, _ = _repository_facts(monkeypatch, candidate_inquiry=True)
    facts_port = type("Facts", (), {"load_case_facts": lambda _self, _case_no: facts})()
    with pytest.raises(CandidateMatchingError, match="candidate_staff_not_active"):
        query.search_candidate_inquiry_availability(
            "CASE-RECONTACT", [{"staff_id": 19}], "2026-08-31", facts_port=facts_port,
        )


def test_candidate_inquiry_keeps_current_order_window_while_loading_old_conflicts(
    monkeypatch,
):
    facts, loaded_windows = _repository_facts(monkeypatch)

    result = query.search_candidate_inquiry_availability(
        "CASE-RECONTACT",
        [{"start_date": "2026-09-01", "end_date": "2026-09-03"}],
        "2026-08-31",
        facts_port=type(
            "Facts",
            (),
            {"load_case_facts": lambda _self, _case_no: facts},
        )(),
        filter_policy={"preferred_service_days": False, "daily_service_hours": False},
    )

    assert facts["order"]["start_date"] == "2026-09-01"
    assert facts["order"]["end_date"] == "2026-09-03"
    assert set(loaded_windows) == {
        ("2026-08-01", "2026-09-03"),
        ("2026-07-31", "2026-09-04"),
    }
    assert result["candidate_options"][0]["required_service_dates"] == [
        "2026-09-01",
        "2026-09-02",
        "2026-09-03",
    ]
    assert result["candidate_options"][0]["full_case_coverage"] is True


def test_official_search_still_projects_confirmed_dates_outside_order_window(monkeypatch):
    facts, _loaded_windows = _repository_facts(monkeypatch)
    facts["confirmed_service_dates"] = [
        {"service_date": "2026-08-01"},
        {"service_date": "2026-08-02"},
        {"service_date": "2026-09-03"},
    ]
    captured = {}

    def derive(**kwargs):
        captured.update(kwargs)
        return {
            "validated_input": {
                "planned_start_date": kwargs["planned_start_date"],
                "planned_end_date": kwargs["planned_end_date"],
            },
            "complete_combinations": [],
            "segment_candidates": [],
            "conflicts": [],
        }

    monkeypatch.setattr(query, "derive_segment_availability", derive)
    query.search_segmented_caregiver_availability(
        "CASE-RECONTACT",
        1,
        [],
        "2026-08-31",
        facts_port=type(
            "Facts",
            (),
            {"load_case_facts": lambda _self, _case_no: facts},
        )(),
        filter_policy={
            "region": False,
            "preferred_service_days": False,
            "cooking": False,
            "daily_service_hours": False,
        },
    )

    assert captured["planned_start_date"] == "2026-08-01"
    assert captured["planned_end_date"] == "2026-09-03"


def test_official_search_accepts_the_full_orders_selectable_range(monkeypatch):
    facts, _loaded_windows = _repository_facts(monkeypatch)
    facts["order"].update({
        "start_date": "2026-12-01",
        "end_date": "2026-12-20",
        "service_days": 20,
    })
    service_dates = tuple(
        date(2026, 12, 1) + timedelta(days=offset) for offset in range(19)
    ) + (date(2027, 2, 3),)
    facts["confirmed_service_dates"] = [
        {"service_date": value.isoformat()} for value in service_dates
    ]
    captured = {}

    def derive(**kwargs):
        captured.update(kwargs)
        return {
            "validated_input": {
                "planned_start_date": kwargs["planned_start_date"],
                "planned_end_date": kwargs["planned_end_date"],
            },
            "complete_combinations": [],
            "segment_candidates": [],
            "conflicts": [],
        }

    monkeypatch.setattr(query, "derive_segment_availability", derive)
    query.search_segmented_caregiver_availability(
        "CASE-RECONTACT",
        1,
        [],
        "2026-11-30",
        facts_port=type(
            "Facts",
            (),
            {"load_case_facts": lambda _self, _case_no: facts},
        )(),
        filter_policy={
            "region": False,
            "preferred_service_days": False,
            "cooking": False,
            "daily_service_hours": False,
        },
    )

    assert captured["planned_start_date"] == "2026-12-01"
    assert captured["planned_end_date"] == "2027-02-03"
