"""File: test_service_day_checkpoint_workflow.py
Description: 驗證每日服務時段結束後才建立一次 Scheduling checkpoint。"""

from datetime import datetime, time, timezone

from infrastructure.mysql.service_day_checkpoint_repository import _candidate as repository_candidate

from subsystems.scheduling.service_day_checkpoint_workflow import (
    ServiceDayCheckpointCandidate,
    ServiceDayCheckpointWorker,
)


def checkpoint_candidate() -> ServiceDayCheckpointCandidate:
    return ServiceDayCheckpointCandidate(
        assignment_id=7,
        schedule_id=11,
        case_no="CASE-7",
        staff_id=3,
        service_date="2026-08-16",
        service_ends_at_utc=datetime(2026, 8, 16, 10, tzinfo=timezone.utc),
        requires_cooking=True,
    )


def test_checkpoint_worker_commits_only_when_new_checkpoint_is_created() -> None:
    calls = {"commits": 0}

    class Repository:
        def due_candidates(self, _now, _limit):
            return (checkpoint_candidate(),)

        def append_checkpoint(self, candidate):
            assert candidate.service_ends_at_utc.hour == 10
            return True

    result = ServiceDayCheckpointWorker(
        Repository,
        lambda: calls.__setitem__("commits", calls["commits"] + 1),
        lambda: datetime(2026, 8, 16, 10, tzinfo=timezone.utc),
    ).run_once()

    assert result == 1
    assert calls["commits"] == 1


def test_checkpoint_worker_does_not_commit_replayed_checkpoint() -> None:
    calls = {"commits": 0}

    class Repository:
        def due_candidates(self, _now, _limit):
            return (checkpoint_candidate(),)

        def append_checkpoint(self, _candidate):
            return False

    result = ServiceDayCheckpointWorker(
        Repository,
        lambda: calls.__setitem__("commits", calls["commits"] + 1),
        lambda: datetime(2026, 8, 16, 10, tzinfo=timezone.utc),
    ).run_once()

    assert result == 0
    assert calls["commits"] == 0


def test_checkpoint_candidate_uses_official_service_end_time_not_midnight() -> None:
    candidate = repository_candidate(
        {
            "id": 11,
            "assignment_id": 7,
            "case_no": "CASE-7",
            "staff_id": 3,
            "work_date": datetime(2026, 8, 16),
            "service_start_time": time(8, 0),
            "service_end_time": time(18, 30),
            "service_end_day_offset": 0,
            "requires_cooking": 1,
        }
    )

    assert candidate is not None
    assert candidate.service_ends_at_utc == datetime(2026, 8, 16, 10, 30, tzinfo=timezone.utc)
