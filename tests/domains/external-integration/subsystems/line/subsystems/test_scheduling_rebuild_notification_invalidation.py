"""
File: test_scheduling_rebuild_notification_invalidation.py
Description: 驗證排班替換只取消舊指派衍生的未送出服務日日誌提醒，失敗走既定重試且阻擋同 cycle 投遞。
"""

from datetime import datetime, timezone

import pytest

from infrastructure.mysql import scheduling_rebuild_notification_invalidation_worker as rebuild_worker_module
from infrastructure.mysql.scheduling_rebuild_notification_invalidation_worker import (
    MySqlSchedulingRebuildNotificationInvalidationWorker,
)
from subsystems.line.scheduling_rebuild_notification_invalidation import (
    SchedulingRebuildNotificationInvalidationError,
    SchedulingRebuildNotificationInvalidationProjector,
    SchedulingRebuildOutboxItem,
)


class _Outbox:
    def __init__(self) -> None:
        self.published: list[int] = []
        self.failed: list[int] = []

    def claim_due(self, _now, _limit):
        return (SchedulingRebuildOutboxItem(5, (12, 13)),)

    def mark_published(self, outbox_id: int) -> None:
        self.published.append(outbox_id)

    def mark_retry_or_failed(self, outbox_id: int, _now, _error: Exception) -> None:
        self.failed.append(outbox_id)


class _Notifications:
    def __init__(self, *, fail: bool = False) -> None:
        self.assignment_ids: list[tuple[int, ...]] = []
        self._fail = fail

    def cancel_service_day_log_reminders_for_assignments(
        self, assignment_ids: tuple[int, ...]
    ) -> int:
        self.assignment_ids.append(assignment_ids)
        if self._fail:
            raise RuntimeError("unexpected_projection_failure")
        return 2


def test_rebuild_cancels_only_explicitly_replaced_assignment_reminders() -> None:
    outbox = _Outbox()
    notifications = _Notifications()

    processed = SchedulingRebuildNotificationInvalidationProjector(
        outbox, notifications
    ).run_once(datetime(2026, 8, 16, tzinfo=timezone.utc))

    assert processed == 1
    assert notifications.assignment_ids == [(12, 13)]
    assert outbox.published == [5]
    assert outbox.failed == []


def test_rebuild_projection_failure_records_retry_then_signals_gate() -> None:
    outbox = _Outbox()
    notifications = _Notifications(fail=True)

    with pytest.raises(
        SchedulingRebuildNotificationInvalidationError,
        match="scheduling_rebuild_notification_invalidation_failed:RuntimeError",
    ) as failure:
        SchedulingRebuildNotificationInvalidationProjector(
            outbox, notifications
        ).run_once(datetime(2026, 8, 16, tzinfo=timezone.utc))

    assert failure.value.processed == 1
    assert failure.value.error_type == "RuntimeError"
    assert outbox.published == []
    assert outbox.failed == [5]


def test_rebuild_worker_declares_pre_delivery_gate() -> None:
    assert MySqlSchedulingRebuildNotificationInvalidationWorker.run_before_delivery is True


def test_rebuild_worker_commits_retry_before_propagating_gate_failure(monkeypatch) -> None:
    state = {"committed": 0, "closed": 0}

    class _Connection:
        def close(self):
            state["closed"] += 1

    class _UnitOfWork:
        def __init__(self, _connection):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def commit(self):
            state["committed"] += 1

    class _Projector:
        def __init__(self, *_args):
            pass

        def run_once(self, _now):
            raise SchedulingRebuildNotificationInvalidationError(
                1, RuntimeError("cancel unavailable")
            )

    monkeypatch.setattr(rebuild_worker_module, "MySqlUnitOfWork", _UnitOfWork)
    monkeypatch.setattr(
        rebuild_worker_module,
        "MySqlSchedulingRebuildNotificationInvalidationRepository",
        lambda _connection: object(),
    )
    monkeypatch.setattr(
        rebuild_worker_module,
        "MySqlLineNotificationRepository",
        lambda _connection: object(),
    )
    monkeypatch.setattr(
        rebuild_worker_module,
        "SchedulingRebuildNotificationInvalidationProjector",
        _Projector,
    )

    worker = MySqlSchedulingRebuildNotificationInvalidationWorker(
        _Connection,
        lambda: datetime(2026, 8, 16, tzinfo=timezone.utc),
    )

    with pytest.raises(SchedulingRebuildNotificationInvalidationError):
        worker.run_once()

    assert state == {"committed": 1, "closed": 1}
