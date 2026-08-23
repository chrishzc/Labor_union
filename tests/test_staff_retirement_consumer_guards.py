"""
File: test_staff_retirement_consumer_guards.py
Description: 驗證退休人員的排班保留邊界、媒合 consumer filter 與 schema release 契約。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from domains.scheduling.assignment_plan import (
    AssignmentPlanIntent,
    AssignmentPlanSegmentIntent,
    EffectiveAssignmentFact,
)
from infrastructure.mysql import assignment_plan_repository as assignment_repository


class _Cursor:
    def __init__(self, rows) -> None:
        self.rows = rows
        self.executed = []

    def execute(self, query, parameters) -> None:
        self.executed.append((query, parameters))

    def fetchall(self):
        return self.rows


def _intent(service_dates):
    return AssignmentPlanIntent(
        (AssignmentPlanSegmentIntent(7, service_dates[0], service_dates[-1], service_dates),)
    )


def _assignment(service_dates):
    return EffectiveAssignmentFact(
        assignment_id=11,
        staff_id=7,
        sequence=1,
        assigned_start_date=service_dates[0],
        assigned_end_date=service_dates[-1],
        official_service_dates=service_dates,
    )


def test_retired_staff_may_only_preserve_exact_effective_assignment(monkeypatch) -> None:
    dates = (date(2026, 8, 1), date(2026, 8, 2))
    cursor = _Cursor(({"id": 7, "status": "active", "lifecycle_state": "retired"},))
    monkeypatch.setattr(assignment_repository, "_effective_assignments", lambda _source: (_assignment(dates),))

    assignment_repository._require_retired_staff_assignment_preservation(
        cursor, object(), _intent(dates), lock=True
    )

    assert "FOR UPDATE" in cursor.executed[0][0]


def test_retired_staff_cannot_expand_or_move_effective_assignment(monkeypatch) -> None:
    preserved_dates = (date(2026, 8, 1), date(2026, 8, 2))
    proposed_dates = preserved_dates + (date(2026, 8, 3),)
    cursor = _Cursor(({"id": 7, "status": "active", "lifecycle_state": "retired"},))
    monkeypatch.setattr(assignment_repository, "_effective_assignments", lambda _source: (_assignment(preserved_dates),))

    with pytest.raises(ValueError, match="staff_retired_new_assignment_forbidden"):
        assignment_repository._require_retired_staff_assignment_preservation(
            cursor, object(), _intent(proposed_dates), lock=False
        )


def test_matching_consumers_all_filter_retired_staff() -> None:
    files = (
        "infrastructure/mysql/matching_recommendation_repository.py",
        "infrastructure/mysql/segmented_availability_repository.py",
        "infrastructure/mysql/matching_notification_repository.py",
        "infrastructure/mysql/matching_schedule_confirmation_repository.py",
    )

    for filename in files:
        source = Path(filename).read_text(encoding="utf-8")
        assert "staff_lifecycle_states" in source
        assert "lifecycle_state" in source


def test_retirement_consumer_guard_does_not_restore_old_matching_facts():
    source = Path(
        "infrastructure/mysql/matching_recommendation_repository.py"
    ).read_text(encoding="utf-8")

    assert "lifecycle_state" in source
    assert "retired" in source


def test_staff_retirement_release_is_schema_only_and_described() -> None:
    release = json.loads(
        Path("db/migration_releases/labor_union_2026_08_15_staff_retirement_v1.json").read_text(encoding="utf-8")
    )
    descriptor = json.loads(
        Path("db/migration_releases/labor_union_2026_08_15_staff_retirement_v1.descriptors.json").read_text(encoding="utf-8")
    )

    assert release["artifacts"][0]["name"] == "1000_staff_retirement.sql"
    assert release["artifacts"][0]["data_effect"] == "schema_only"
    assert release["backfills"] == []
    assert set(descriptor["descriptors"]["1000_staff_retirement.sql"]["tables"]) == {
        "staff_lifecycle_states",
        "staff_lifecycle_events",
        "staff_lifecycle_apply_receipts",
    }
