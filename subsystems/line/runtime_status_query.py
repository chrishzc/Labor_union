"""Read-only, bounded system status for the administrator LIFF workbench."""

from dataclasses import dataclass
from datetime import datetime, timezone
import os


@dataclass(frozen=True, slots=True)
class NotificationQueueCounts:
    pending: int
    failed: int


@dataclass(frozen=True, slots=True)
class SystemCheckView:
    label: str
    status: str
    checked_at: datetime


@dataclass(frozen=True, slots=True)
class SystemStatusView:
    status: str
    worker_status: str
    pending_count: int
    failed_count: int
    last_checked_at: datetime | None
    checks: tuple[SystemCheckView, ...]


_LABELS = {
    "line_worker": "LINE 訊息發送服務",
    "line_queues": "通知處理佇列",
    "matching_delivery": "媒合通知",
    "database": "資料庫",
    "redis": "訊息處理支援服務",
    "media_storage": "檔案儲存",
    "knowledge-retrieval-worker": "知識檢索服務",
}
_SEVERITY = {"healthy": 0, "maintenance": 1, "unknown": 2, "warning": 3, "critical": 4}


class RuntimeStatusQuery:
    def __init__(self, unit_of_work_factory, now=lambda: datetime.now(timezone.utc)):
        self._unit_of_work_factory = unit_of_work_factory
        self._now = now

    def query(self) -> SystemStatusView:
        with self._unit_of_work_factory() as unit:
            records = unit.runtime_monitor.list_status()
            counts = unit.runtime_monitor.notification_queue_counts()
        now = self._now()
        freshness = float(os.getenv("LINE_WORKER_STALE_SECONDS", "90"))
        checks = tuple(SystemCheckView(
            _LABELS[row.check_name],
            row.status if row.status in _SEVERITY and 0 <= (now - row.checked_at).total_seconds() <= freshness else "unknown",
            row.checked_at,
        ) for row in records if row.check_name in _LABELS)
        worker = next((check.status for check in checks if check.label == _LABELS["line_worker"]), "unknown")
        statuses = [check.status for check in checks] + [worker]
        if counts.failed:
            statuses.append("warning")
        return SystemStatusView(
            max(statuses, key=_SEVERITY.__getitem__), worker, counts.pending, counts.failed,
            max((check.checked_at for check in checks), default=None), checks,
        )
