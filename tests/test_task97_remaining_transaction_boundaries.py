"""Focused Task 97 regressions for the remaining transaction boundaries."""

from __future__ import annotations

from pathlib import Path

from infrastructure.mysql.accounts_payable_export_sources import MySqlReadOnlySnapshot
from infrastructure.mysql.line_notification_reconciliation_worker import (
    MySqlLineNotificationReconciliationWorker,
)
from infrastructure.mysql import process_reminder_anomaly_source as process_reminder
from subsystems.anomalies import outbox_worker


ROOT = Path(__file__).resolve().parents[1]


def test_process_reminder_source_requires_caller_uow_and_has_no_raw_transaction_calls():
    source = (ROOT / "infrastructure/mysql/process_reminder_anomaly_source.py").read_text(
        encoding="utf-8"
    )

    assert "owns_transaction" not in source
    assert ".begin(" not in source
    assert ".commit(" not in source
    assert ".rollback(" not in source


def test_process_reminder_source_failure_is_rolled_back_by_outbox_application():
    class Connection:
        def __init__(self):
            self.begins = 0
            self.commits = 0
            self.rollbacks = 0

        def begin(self):
            self.begins += 1

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

    connection = Connection()
    state = outbox_worker.ArchitectureSourceScanState.start()

    class UnitOfWork:
        def __enter__(self):
            connection.begin()
            return self

        def __exit__(self, exception_type, exception, traceback):
            if connection.commits == 0:
                connection.rollback()
            return False

        def commit(self):
            connection.commit()

    class Runtime:
        @staticmethod
        def failure_unit_of_work(_connection):
            return UnitOfWork()

        @staticmethod
        def consume_process_reminder_anomaly_sources(*_args, **_kwargs):
            return process_reminder.ProcessReminderConsumeResult(0, 0, error=object())

    assert outbox_worker._consume_process_reminder_source(
        connection, state, Runtime()
    ) == (0, 1)
    assert (connection.begins, connection.commits, connection.rollbacks) == (1, 0, 1)
    assert state.process_reminder_exhausted is True


def test_line_reconciliation_infrastructure_borrows_repository_without_transaction_calls():
    class Repository:
        def list_sources_without_decisions(self, *, limit=100):
            return ()

        def register_and_project(self, event):
            raise AssertionError("no events expected")

    assert MySqlLineNotificationReconciliationWorker(lambda: Repository()).run_once() == 0
    source = (ROOT / "infrastructure/mysql/line_notification_reconciliation_worker.py").read_text(
        encoding="utf-8"
    )
    assert ".begin(" not in source
    assert ".commit(" not in source
    assert ".rollback(" not in source


def test_read_only_snapshot_does_not_finalize_the_caller_transaction():
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, statement):
            assert statement

    class Connection:
        def __init__(self):
            self.rollbacks = 0

        def cursor(self):
            return Cursor()

        def rollback(self):
            self.rollbacks += 1

    connection = Connection()
    snapshot = MySqlReadOnlySnapshot(connection)
    snapshot.__enter__()
    snapshot.__exit__(None, None, None)
    assert connection.rollbacks == 0
