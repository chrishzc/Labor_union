"""Regression coverage for inquiry versus official service-date windows."""

from infrastructure.mysql.segmented_availability_repository import (
    MySqlSegmentedAvailabilityFactsRepository,
)
from subsystems.scheduling import segmented_availability_query as query


def _repository_facts(monkeypatch):
    repository = MySqlSegmentedAvailabilityFactsRepository(lambda: None)
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

    order = {
        "case_no": "CASE-RECONTACT",
        "status": "洽談中",
        "start_date": "2026-09-01",
        "end_date": "2026-09-03",
        "scheduling_version": 4,
        "requires_cooking": None,
    }
    return repository._load_negotiation_facts(object(), order), loaded_windows


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
    )

    assert facts["order"]["start_date"] == "2026-09-01"
    assert facts["order"]["end_date"] == "2026-09-03"
    assert set(loaded_windows) == {("2026-08-01", "2026-09-03")}
    assert result["candidate_options"][0]["required_service_dates"] == [
        "2026-09-01",
        "2026-09-02",
        "2026-09-03",
    ]
    assert result["candidate_options"][0]["full_case_coverage"] is True


def test_official_search_still_projects_confirmed_dates_outside_order_window(monkeypatch):
    facts, _loaded_windows = _repository_facts(monkeypatch)
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
