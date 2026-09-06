"""Focused disposable-MySQL checks for weekly close-batch transaction semantics."""

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


@pytest.fixture(scope="module")
def close_batch_database():
    database = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE", "").strip()
    if not database:
        pytest.fail("close-batch transaction checks require explicit disposable MySQL configuration")
    if not database.startswith("lu_test_"):
        pytest.fail("close-batch transaction checks require a lu_test_* database")

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


class _FailingCursor:
    def __init__(self, cursor, *, fail_on_batch_case_insert: int) -> None:
        self._cursor = cursor
        self._fail_on_batch_case_insert = fail_on_batch_case_insert
        self._batch_case_insert_count = 0

    def __enter__(self):
        self._cursor.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        return self._cursor.__exit__(exc_type, exc, traceback)

    def execute(self, sql, params=None):
        normalized = " ".join(str(sql).split()).lower()
        if "insert into weekly_report_batch_cases" in normalized:
            self._batch_case_insert_count += 1
            if self._batch_case_insert_count == self._fail_on_batch_case_insert:
                raise RuntimeError("forced close-batch bind failure")
        return self._cursor.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _FailingConnection(_CountingConnection):
    def __init__(self, connection, *, fail_on_batch_case_insert: int) -> None:
        super().__init__(connection)
        self._fail_on_batch_case_insert = fail_on_batch_case_insert

    def cursor(self, *args, **kwargs):
        return _FailingCursor(
            self._connection.cursor(*args, **kwargs),
            fail_on_batch_case_insert=self._fail_on_batch_case_insert,
        )


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
            raise RuntimeError("forced close-batch post-commit readback failure")
        return self._cursor.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _PostCommitReadbackConnection(_CountingConnection):
    def cursor(self, *args, **kwargs):
        return _PostCommitReadbackCursor(
            self._connection.cursor(*args, **kwargs),
            self,
        )


def _seed_cases(*case_nos: str) -> None:
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            for index, case_no in enumerate(case_nos, start=1):
                cursor.execute(
                    """
                    INSERT INTO clients (case_no, name, created_at, identity_status)
                    VALUES (%s, %s, %s, '一般市民')
                    """,
                    (case_no, f"Issue229-{index}", datetime(2031, 1, index, 9, 0)),
                )
            cursor.execute(
                """
                INSERT INTO orders (case_no, client_id, status, created_at)
                SELECT case_no, id, '訂單成立', created_at
                FROM clients
                WHERE case_no IN %s
                """,
                (tuple(case_nos),),
            )
        connection.commit()
    finally:
        connection.close()


def _service_from_request_dependency(monkeypatch, connection):
    monkeypatch.setattr(operations_report_dependencies, "get_connection", lambda: connection)
    dependency = operations_report_dependencies.get_weekly_report_batch_service()
    return dependency, next(dependency)


def _read_batch_state(year: int, week_code: str, case_nos: tuple[str, ...]):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM weekly_report_batches WHERE year = %s AND week_code = %s",
                (year, week_code),
            )
            batch = cursor.fetchone()
            cursor.execute(
                "SELECT case_no FROM weekly_report_batch_cases WHERE case_no IN %s ORDER BY case_no",
                (case_nos,),
            )
            bound_cases = [row["case_no"] for row in cursor.fetchall()]
        return batch, bound_cases
    finally:
        connection.close()


@pytest.mark.integration
def test_close_batch_success_commits_once_and_dependency_closes_connection(
    close_batch_database,
    monkeypatch,
):
    del close_batch_database
    case_nos = ("TEST-229-S1", "TEST-229-S2")
    _seed_cases(*case_nos)
    connection = _CountingConnection(get_connection())
    dependency, service = _service_from_request_dependency(monkeypatch, connection)

    try:
        batch = service.close_batch(
            year=2031,
            week_code="229-success",
            promotion_count=7,
            inquiry_count=3,
            case_nos=list(case_nos),
            cutoff_at=datetime(2031, 1, 10, 10, 0),
        )
        assert batch.case_count == 2
        assert connection.commit_count == 1
    finally:
        dependency.close()

    assert connection.closed is True
    persisted_batch, persisted_cases = _read_batch_state(2031, "229-success", case_nos)
    assert persisted_batch is not None
    assert persisted_cases == sorted(case_nos)


@pytest.mark.integration
def test_close_batch_precommit_failure_rolls_back_on_dependency_close(
    close_batch_database,
    monkeypatch,
):
    del close_batch_database
    case_nos = ("TEST-229-F1", "TEST-229-F2")
    _seed_cases(*case_nos)
    connection = _FailingConnection(get_connection(), fail_on_batch_case_insert=2)
    dependency, service = _service_from_request_dependency(monkeypatch, connection)

    try:
        with pytest.raises(RuntimeError, match="forced close-batch bind failure"):
            service.close_batch(
                year=2031,
                week_code="229-precommit-failure",
                case_nos=list(case_nos),
                cutoff_at=datetime(2031, 1, 11, 10, 0),
            )
        assert connection.commit_count == 0
    finally:
        dependency.close()

    assert connection.closed is True
    persisted_batch, persisted_cases = _read_batch_state(
        2031,
        "229-precommit-failure",
        case_nos,
    )
    assert persisted_batch is None
    assert persisted_cases == []


@pytest.mark.integration
def test_close_batch_postcommit_readback_failure_does_not_rollback_committed_state(
    close_batch_database,
    monkeypatch,
):
    del close_batch_database
    case_nos = ("TEST-229-R1", "TEST-229-R2")
    _seed_cases(*case_nos)
    connection = _PostCommitReadbackConnection(get_connection())
    dependency, service = _service_from_request_dependency(monkeypatch, connection)

    try:
        with pytest.raises(RuntimeError, match="forced close-batch post-commit readback failure"):
            service.close_batch(
                year=2031,
                week_code="229-postcommit-failure",
                case_nos=list(case_nos),
                cutoff_at=datetime(2031, 1, 12, 10, 0),
            )
        assert connection.commit_count == 1
    finally:
        dependency.close()

    assert connection.closed is True
    persisted_batch, persisted_cases = _read_batch_state(
        2031,
        "229-postcommit-failure",
        case_nos,
    )
    assert persisted_batch is not None
    assert persisted_cases == sorted(case_nos)
