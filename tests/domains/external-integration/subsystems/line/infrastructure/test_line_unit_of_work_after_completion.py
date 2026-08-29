"""
File: test_line_unit_of_work_after_completion.py
Description: 驗證 LINE outer UoW 在 commit/rollback 後執行一次 cleanup，且不遮蔽完成狀態。
"""

import pytest

from infrastructure.mysql.line_unit_of_work import LineMySqlUnitOfWork
from subsystems.line.runtime_alert_target_contracts import RuntimeAlertTargetError


class _Connection:
    def __init__(self):
        self.events = []

    def begin(self):
        self.events.append("begin")

    def commit(self):
        self.events.append("commit")

    def rollback(self):
        self.events.append("rollback")


def test_after_completion_runs_after_commit_once():
    connection = _Connection()
    uow = LineMySqlUnitOfWork(connection)
    uow.__enter__()
    uow.add_after_completion(lambda: connection.events.append("release"))
    uow.commit()
    uow.__exit__(None, None, None)
    assert connection.events == ["begin", "commit", "release"]


def test_release_unknown_after_commit_is_not_masked_by_rollback():
    connection = _Connection()
    uow = LineMySqlUnitOfWork(connection)
    uow.__enter__()

    def fail_release():
        raise RuntimeAlertTargetError(
            "unavailable", "line_alert_target_commit_outcome_unknown", "unknown", retryable=True
        )

    uow.add_after_completion(fail_release)
    with pytest.raises(RuntimeAlertTargetError) as error:
        uow.commit()
    uow.__exit__(type(error.value), error.value, error.value.__traceback__)
    assert error.value.code == "line_alert_target_commit_outcome_unknown"
    assert connection.events == ["begin", "commit"]


def test_after_completion_runs_after_rollback():
    connection = _Connection()
    uow = LineMySqlUnitOfWork(connection)
    uow.__enter__()
    uow.add_after_completion(lambda: connection.events.append("release"))
    uow.rollback()
    assert connection.events == ["begin", "rollback", "release"]
