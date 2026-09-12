"""Formal plan selection uses willing-candidate facts and schedule eligibility."""

from datetime import date
from types import SimpleNamespace

import pytest

from subsystems.scheduling import matching_notification_application, matching_plan_workflow
from subsystems.scheduling.segmented_availability_query import _passes_enabled_filters


def test_matching_preferences_explain_but_do_not_exclude_candidate():
    policy = {
        "region": True,
        "cooking": True,
        "preferred_service_days": True,
        "daily_service_hours": True,
        "enabled_preference_keys": ("custom_preference",),
    }

    assert _passes_enabled_filters(
        {
            "region": True,
            "cooking": True,
            "preferred_service_days": False,
            "daily_service_hours": False,
            "custom_preference": False,
        },
        policy,
    )


def test_formal_single_plan_requires_matching_current_willing_candidate(monkeypatch):
    candidate = SimpleNamespace(
        status="active",
        willingness="willing",
        staff_id=1,
        service_start_date=date(2026, 12, 21),
        service_end_date=date(2027, 1, 9),
    )
    monkeypatch.setattr(
        matching_plan_workflow,
        "query_pool",
        lambda *_args, **_kwargs: SimpleNamespace(candidates=(candidate,)),
    )

    matching_plan_workflow._require_current_willing_candidate(
        object(),
        "M3-CUST-20260910-01",
        [
            {
                "staff_id": 1,
                "assigned_start_date": "2026-12-21",
                "assigned_end_date": "2027-01-09",
            }
        ],
    )


def test_formal_single_plan_rejects_non_willing_candidate(monkeypatch):
    monkeypatch.setattr(
        matching_plan_workflow,
        "query_pool",
        lambda *_args, **_kwargs: SimpleNamespace(candidates=()),
    )

    with pytest.raises(ValueError, match="current willing candidate is required"):
        matching_plan_workflow._require_current_willing_candidate(
            object(),
            "M3-CUST-20260910-01",
            [
                {
                    "staff_id": 1,
                    "assigned_start_date": "2026-12-21",
                    "assigned_end_date": "2027-01-09",
                }
            ],
        )


def test_willing_candidate_plan_uses_schedule_only_availability(monkeypatch):
    captured = {}
    segments = [
        {
            "staff_id": 1,
            "assigned_start_date": "2026-12-21",
            "assigned_end_date": "2027-01-09",
        }
    ]

    def fake_search(**kwargs):
        captured.update(kwargs)
        return {
            "feasibility": "complete",
            "conflicts": [],
            "complete_combinations": [
                [
                    {
                        "segment_index": 0,
                        "staff_id": 1,
                        "start_date": "2026-12-21",
                        "end_date": "2027-01-09",
                    }
                ]
            ],
        }

    monkeypatch.setattr(
        matching_plan_workflow,
        "search_segmented_caregiver_availability",
        fake_search,
    )
    monkeypatch.setattr(
        matching_plan_workflow,
        "_run_in_application_uow",
        lambda _operation: {"result": "created"},
    )

    matching_plan_workflow.create_matching_plan_version(
        "M3-CUST-20260910-01",
        segments,
        "admin",
        "2026-09-11",
        facts_port=object(),
        require_willing_candidate=True,
    )

    assert captured["filter_policy"] == {
        "region": False,
        "cooking": False,
        "preferred_service_days": False,
        "daily_service_hours": False,
    }
    assert captured["include_candidate_options"] is False


class _FormalPlanFacts:
    def __init__(self, *, occupied: bool = False):
        self._occupied = occupied

    def load_case_facts(self, case_no):
        return {
            "order": {
                "case_no": case_no,
                "status": "洽談中",
                "start_date": "2026-12-01",
                "end_date": "2026-12-20",
                "scheduling_version": 1,
            },
            # Stage 5 creates the formal plan before later service-date
            # confirmation. Its schedule revalidation must still be usable.
            "confirmed_service_dates": [],
            "staff_rows": [{"id": 1, "name": "測試月嫂"}],
            "assignments": [],
            "schedule_rows": [],
            "legacy_schedule_rows": [],
            "buffer_rows": [],
            "active_lock_rows": [],
            "waiting_buffer_rows": [],
            "staff_unavailability_rows": (
                [
                    {
                        "id": 1,
                        "staff_id": 1,
                        "start_date": "2026-12-10",
                        "end_date": "2026-12-10",
                    }
                ]
                if self._occupied
                else []
            ),
        }


def test_current_willing_candidate_creates_plan_without_candidate_display_dates(monkeypatch):
    candidate = SimpleNamespace(
        status="active",
        willingness="willing",
        staff_id=1,
        service_start_date=date(2026, 12, 1),
        service_end_date=date(2026, 12, 20),
    )
    segments = [
        {
            "staff_id": 1,
            "start_date": "2026-12-01",
            "end_date": "2026-12-20",
        }
    ]
    monkeypatch.setattr(
        matching_plan_workflow,
        "query_pool",
        lambda *_args, **_kwargs: SimpleNamespace(candidates=(candidate,)),
    )

    def persist(_connection, _cursor, case_no, normalized, _actor, _signature, requires_willing):
        assert requires_willing is True
        matching_plan_workflow._require_current_willing_candidate(
            object(), case_no, normalized
        )
        return {"result": "created"}

    monkeypatch.setattr(
        matching_plan_workflow,
        "_create_matching_plan_version_in_transaction",
        persist,
    )
    monkeypatch.setattr(
        matching_plan_workflow,
        "_run_in_application_uow",
        lambda operation: operation(object(), object()),
    )

    assert matching_plan_workflow.create_matching_plan_version(
        "CASE-2026-S05",
        segments,
        "operator",
        "2026-09-11",
        facts_port=_FormalPlanFacts(),
        require_willing_candidate=True,
    ) == {"result": "created"}


def test_formal_plan_still_rejects_current_schedule_conflict(monkeypatch):
    monkeypatch.setattr(
        matching_plan_workflow,
        "_run_in_application_uow",
        lambda _operation: pytest.fail("conflicted plan must not enter persistence"),
    )

    with pytest.raises(ValueError, match="submitted segments must match a complete combination"):
        matching_plan_workflow.create_matching_plan_version(
            "CASE-2026-S05",
            [
                {
                    "staff_id": 1,
                    "start_date": "2026-12-01",
                    "end_date": "2026-12-20",
                }
            ],
            "operator",
            "2026-09-11",
            facts_port=_FormalPlanFacts(occupied=True),
            require_willing_candidate=True,
        )


def test_formal_plan_notification_revalidates_schedule_without_candidate_preferences(monkeypatch):
    captured = {}
    state = SimpleNamespace(
        plan=SimpleNamespace(case_no="M3-CUST-20260910-01"),
        segments=(
            SimpleNamespace(
                staff_id=1,
                assigned_start_date=date(2026, 12, 21),
                assigned_end_date=date(2027, 1, 9),
            ),
        ),
    )

    def fake_search(**kwargs):
        captured.update(kwargs)
        return {"feasibility": "complete", "conflicts": []}

    monkeypatch.setattr(
        matching_notification_application,
        "search_segmented_caregiver_availability",
        fake_search,
    )

    matching_notification_application._validate_availability(state, object())

    assert captured["filter_policy"] == {
        "region": False,
        "cooking": False,
        "preferred_service_days": False,
        "daily_service_hours": False,
    }
    assert captured["include_candidate_options"] is False
