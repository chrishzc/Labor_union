"""
File: notification_timeline_application.py
Description: 提供管理員唯讀查詢單一案件的 LINE 通知來源、決策、意圖與投遞狀態。
"""

from __future__ import annotations

from typing import Callable

from shared_kernel.identities import ActorContext
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.ports import LineUnitOfWorkPort


class LineNotificationTimelineApplication:
    def __init__(self, unit_of_work_factory: Callable[[], LineUnitOfWorkPort]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def list_case(self, case_no: str, actor: ActorContext) -> tuple[dict[str, object], ...]:
        require_line_capability(actor, LineCapability.CONFIG_READ)
        if not case_no.strip():
            raise ValueError("notification timeline case number is required")
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.notification_rules.list_case_timeline(case_no.strip())


__all__ = ["LineNotificationTimelineApplication"]
