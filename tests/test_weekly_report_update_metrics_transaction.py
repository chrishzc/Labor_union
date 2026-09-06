"""Focused disposable-MySQL checks for weekly metric-update transaction semantics."""

from __future__ import annotations

from argparse import Namespace
from datetime import datetime
import os

import pytest

import api.dependencies.operations_reports as operations_report_dependencies
from infrastructure.mysql.mysql_adapter import get_connection
from scripts.bootstrap_disposable_mysql_schema import bootstrap
from scripts.migrate_weekly_report_batches import DDL_SQL
from scripts.reset_fake_database import split_sql
from subsystems.reporting.weekly_report_batch_service import WeeklyReportBatchService


@pytest.fixture(scope="module")
def update_metrics_database():
    database = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE", "").strip()
    if not database:
        pytest.fail("update-metrics transaction checks require explicit disposable MySQL configuration")
    if not database.startswith("lu_test_"):
        pytest.fail("update-metrics transaction checks require a lu_test_* database")

    bootstrap(
        Namespace(
            host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
            port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
            user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
            password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
            database=database,
            confirm_database=database,
        )
    )
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            for statement in split_sql(DDL_SQL):
                cursor.execute(statement)
        connection.commit()
    finally:
        connection.close()


def _seed_batch(*, year: int, week_code: str, promotion: int, inquiry: int, notes: str | None = None) -> int:
    connection = get_connection()
    try:
        service = WeeklyReportBatchService(connection)
        batch = service.close_batch(
            year=year,
            week_code=week_code,
            promotion_count=promotion,
            inquiry_count=inquiry,
            notes=notes,
            case_nos=[],
            cutoff_at=datetime(year, 1, 10, 10, 0),
        )
        return batch.id
    finally:
        connection.close()


def _read_batch(batch_id: int):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, year, week_code, promotion_count, inquiry_count, notes FROM weekly_report_batches WHERE id = %s",
                (batch_id,),
            )
            return cursor.fetchone()
    finally:
        connection.close()


class _CountingConnection:
    def __init__(self, connection) -> None:
        self._connection = connection
        self.commit_count = 0
        self.closed = False

    def cursor(self, *args, **kwargs):
        return self._connection.cursor(*args, **kwargs)

    def commit(self) -> None:
        self.commit_count += 1
        self._connection.commit()

    def close(self) -> None:
        self.closed = True
        self._connection.close()


class _FailAfterUpdateCursor:
    def __init__(self, cursor) -> None:
        self._cursor = cursor
        self._updated = False

    def __enter__(self):
        self._cursor.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        return self._cursor.__exit__(exc_type, exc, traceback)

    def execute(self, sql, params=None):
        normalized = " ".join(str(sql).split()).lower()
        result = self._cursor.execute(sql, params)
        if normalized.startswith("update weekly_report_batches set"):
            self._updated = True
            return result
        if self._updated and normalized.startswith("select year from weekly_report_batches"):
            raise RuntimeError("forced update-metrics pre-commit failure")
        return result

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _FailAfterUpdateConnection(_CountingConnection):
    def cursor(self, *args, **kwargs):
        return _FailAfterUpdateCursor(self._connection.cursor(*args, **kwargs))


class _PostCommitReadbackCursor:
    def __init__(self, cursor, connection: "_PostCommitReadbackConnection") -> None:
        self._cursor = cursor
        self._connection = connection

    def __enter__(self):
        self._cursor.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        return self._cursor.__exit__(exc_type, exc, traceback)

    def execute(self, sql, params=None):
        normalized = " ".join(str(sql).split()).lower()
        if self._connection.commit_count and normalized.startswith("select b.id, b.year"):
            raise RuntimeError("forced update-metrics post-commit readback failure")
        return self._cursor.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _PostCommitReadbackConnection(_CountingConnection):
    def cursor(self, *args, **kwargs):
        return _PostCommitReadbackCursor(self._connection.cursor(*args, **kwargs), self)


def _service_from_request_dependency(monkeypatch, connection):
    monkeypatch.setattr(operations_report_dependencies, "get_connection", lambda: connection)
    dependency = operations_report_dependencies.get_weekly_report_batch_service()
    return dependency, next(dependency)


@pytest.mark.integration
def test_update_metrics_success_commits_once_and_dependency_closes_connection(
    update_metrics_database,
    monkeypatch,
):
    del update_metrics_database
    batch_id = _seed_batch(year=2032, week_code="230-success", promotion=2, inquiry=1, notes="before")
    connection = _CountingConnection(get_connection())
    dependency, service = _service_from_request_dependency(monkeypatch, connection)

    try:
        result = service.update_batch_metrics(
            batch_id,
            promotion_count=8,
            inquiry_count=5,
            week_code="230-success-updated",
            notes="after",
        )
        assert result.promotion_count == 8
        assert result.inquiry_count == 5
        assert result.week_code == "230-success-updated"
        assert result.notes == "after"
        assert connection.commit_count == 1
    finally:
        dependency.close()

    assert connection.closed is True
    persisted = _read_batch(batch_id)
    assert persisted["promotion_count"] == 8
    assert persisted["inquiry_count"] == 5
    assert persisted["week_code"] == "230-success-updated"
    assert persisted["notes"] == "after"


@pytest.mark.integration
def test_update_metrics_precommit_failure_preserves_original_values_after_dependency_close(
    update_metrics_database,
    monkeypatch,
):
    del update_metrics_database
    batch_id = _seed_batch(year=2032, week_code="230-precommit", promotion=3, inquiry=2, notes="original")
    connection = _FailAfterUpdateConnection(get_connection())
    dependency, service = _service_from_request_dependency(monkeypatch, connection)

    try:
        with pytest.raises(RuntimeError, match="forced update-metrics pre-commit failure"):
            service.update_batch_metrics(
                batch_id,
                promotion_count=99,
                inquiry_count=88,
                week_code="230-mutated",
                notes="mutated",
            )
        assert connection.commit_count == 0
    finally:
        dependency.close()

    assert connection.closed is True
    persisted = _read_batch(batch_id)
    assert persisted["promotion_count"] == 3
    assert persisted["inquiry_count"] == 2
    assert persisted["week_code"] == "230-precommit"
    assert persisted["notes"] == "original"


@pytest.mark.integration
def test_update_metrics_missing_batch_commits_nothing_and_creates_nothing(
    update_metrics_database,
    monkeypatch,
):
    del update_metrics_database
    missing_id = 987654321
    connection = _CountingConnection(get_connection())
    dependency, service = _service_from_request_dependency(monkeypatch, connection)

    try:
        with pytest.raises(ValueError, match="batch_not_found"):
            service.update_batch_metrics(missing_id, promotion_count=1, inquiry_count=1)
        assert connection.commit_count == 0
    finally:
        dependency.close()

    assert connection.closed is True
    assert _read_batch(missing_id) is None


@pytest.mark.integration
def test_update_metrics_postcommit_readback_failure_keeps_committed_values(
    update_metrics_database,
    monkeypatch,
):
    del update_metrics_database
    batch_id = _seed_batch(year=2032, week_code="230-postcommit", promotion=4, inquiry=3, notes="before")
    connection = _PostCommitReadbackConnection(get_connection())
    dependency, service = _service_from_request_dependency(monkeypatch, connection)

    try:
        with pytest.raises(RuntimeError, match="forced update-metrics post-commit readback failure"):
            service.update_batch_metrics(
                batch_id,
                promotion_count=12,
                inquiry_count=7,
                notes="committed",
            )
        assert connection.commit_count == 1
    finally:
        dependency.close()

    assert connection.closed is True
    persisted = _read_batch(batch_id)
    assert persisted["promotion_count"] == 12
    assert persisted["inquiry_count"] == 7
    assert persisted["week_code"] == "230-postcommit"
    assert persisted["notes"] == "committed"
