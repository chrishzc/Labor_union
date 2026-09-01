"""
File: process_reminder_anomaly_source.py
Description: 保留已退役流程提醒 anomaly entrypoint 的相容形狀；不再投影 anomaly。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from shared_kernel.errors import TypedError


@dataclass(frozen=True, slots=True)
class ProcessReminderConsumeResult:
    projected_count: int
    active_count: int
    error: TypedError | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None


def consume_process_reminder_anomaly_sources(
    connection: Any,
    *,
    as_of: date,
    unit_of_work_factory: Callable[[], object],
) -> ProcessReminderConsumeResult:
    """Keep the retired process-reminder anomaly entrypoint inert.

    Current Anomalies has one runtime issue (``LINE-006``), whose owner facts
    are refreshed through the dedicated LINE notification recheck path.  The
    former process-reminder scan produced owner work items and retired
    correctness codes, so it must not query or project them through the
    current anomaly registry.
    """
    del connection, as_of, unit_of_work_factory
    return ProcessReminderConsumeResult(0, 0)


def _scan_all(connection, as_of: date) -> tuple:
    del connection, as_of
    return ()


__all__ = [
    "ProcessReminderConsumeResult",
    "consume_process_reminder_anomaly_sources",
]
