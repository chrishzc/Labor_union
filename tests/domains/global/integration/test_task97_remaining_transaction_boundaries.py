"""Focused Task 97 regressions for the remaining transaction boundaries."""

from __future__ import annotations

from pathlib import Path

from infrastructure.mysql.accounts_payable_export_sources import MySqlReadOnlySnapshot
from infrastructure.mysql.line_notification_reconciliation_worker import (
    MySqlLineNotificationReconciliationWorker,
)


ROOT = Path(__file__).resolve().parents[4]


def test_process_reminder_source_requires_caller_uow_and_has_no_raw_transaction_calls():
    source = (ROOT / "infrastructure/mysql/process_reminder_anomaly_source.py").read_text(
        encoding="utf-8"
    )

    assert "owns_transaction" not in source
    assert ".begin(" not in source
    assert ".commit(" not in source
    assert ".rollback(" not in source


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
