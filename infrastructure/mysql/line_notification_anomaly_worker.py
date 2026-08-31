"""
File: line_notification_anomaly_worker.py
Description: 掃描 LINE-006 logical groups，提交既有 bounded anomaly.recheck intent。
"""

from __future__ import annotations

from typing import Callable

from infrastructure.mysql.line_unit_of_work import LineMySqlUnitOfWork
from subsystems.line.notification_failure_current_fact import (
    LineNotificationFailureCurrentFactQuery,
    append_line_notification_failure_rechecks,
)


class MySqlLineNotificationAnomalyWorker:
    def __init__(self, connection_factory: Callable[[], object]) -> None:
        self._connection_factory = connection_factory

    def run_once(self, *, limit: int = 100) -> int:
        connection = self._connection_factory()
        try:
            with LineMySqlUnitOfWork(connection) as unit_of_work:
                targets = unit_of_work.notification_rules.list_line006_recheck_targets(
                    limit=limit
                )
                for target in targets:
                    readback = unit_of_work.notification_rules.current_failure_fact(
                        LineNotificationFailureCurrentFactQuery(
                            target.case_no, target.notification_reason
                        )
                    )
                    append_line_notification_failure_rechecks(
                        unit_of_work,
                        (target,),
                        cause_identity=f"line006-scan:{readback.owner_snapshot_token}",
                    )
                unit_of_work.commit()
        finally:
            connection.close()
        return len(targets)


__all__ = ["MySqlLineNotificationAnomalyWorker"]
