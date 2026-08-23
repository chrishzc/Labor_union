"""
File: test_durable_job_disposable_mysql_e2e.py
Description: 以唯一 lu_test DB 驗證 claim 後 crash-resume 不虛構 success 且可安全完成 closed outcome。
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pymysql
import pytest

from infrastructure.mysql.background_job_repository import BackgroundJobRepository
from shared_kernel.durable_job_queue import DurableJobCommand
from subsystems.jobs.durable_job_worker import DurableJobWorker


pytestmark = pytest.mark.integration
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _create_queue_database(database: str) -> None:
    connection = pymysql.connect(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        charset="utf8mb4",
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cursor.execute(f"USE `{database}`")
            for relative_path in ("db/schema_parts/137_background_jobs.sql", "db/schema_parts/141_durable_background_job_queue.sql"):
                sql = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
                for statement in (part.strip() for part in sql.split(";") if part.strip()):
                    cursor.execute(statement)
        connection.commit()
    finally:
        connection.close()


def _connect_queue_database(database: str):
    return pymysql.connect(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


@pytest.fixture(scope="module")
def lifecycle_database():
    required = (
        "LABOR_UNION_TEST_MYSQL_HOST",
        "LABOR_UNION_TEST_MYSQL_PORT",
        "LABOR_UNION_TEST_MYSQL_USER",
        "LABOR_UNION_TEST_MYSQL_PASSWORD",
    )
    missing = [name for name in required if os.environ.get(name) is None]
    assert not missing, "BLOCKED_ENGINE_EVIDENCE: missing " + ",".join(missing)
    database = "lu_test_durable_lifecycle_" + uuid.uuid4().hex[:12]
    previous_database = os.environ.get("DB_DATABASE")
    os.environ["DB_DATABASE"] = database
    _create_queue_database(database)
    try:
        yield database
    finally:
        connection = pymysql.connect(
            host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
            port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
            user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
            password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
            charset="utf8mb4",
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE `{database}`")
            connection.commit()
        finally:
            connection.close()
        if previous_database is None:
            os.environ.pop("DB_DATABASE", None)
        else:
            os.environ["DB_DATABASE"] = previous_database


def test_claim_commit_then_crash_keeps_running_without_receipt_until_recovery(
    lifecycle_database,
) -> None:
    identity = "job.crash." + uuid.uuid4().hex
    command = DurableJobCommand(
        "job-" + uuid.uuid4().hex,
        identity,
        "test.crash.resume",
        1,
        {"case": "synthetic"},
        "system:durable-crash-test",
        "corr-" + uuid.uuid4().hex,
        2,
    )
    first_connection = _connect_queue_database(lifecycle_database)
    first_repository = BackgroundJobRepository(first_connection)
    try:
        first_connection.begin()
        first_repository.enqueue_canonical_command(command)
        first_connection.commit()
        first_connection.begin()
        lease = first_repository.claim_next_canonical_command("worker-before-crash", 60)
        first_connection.commit()
        assert lease is not None
        observed = first_repository.get_job(command.job_id)
        assert observed is not None
        assert observed.status == "running"
        assert observed.receipt_payload is None
        assert observed.error_payload is None
    finally:
        first_connection.close()

    recovery_connection = _connect_queue_database(lifecycle_database)
    recovery_repository = BackgroundJobRepository(recovery_connection)
    calls = []
    try:
        with recovery_connection.cursor() as cursor:
            cursor.execute(
                "UPDATE background_jobs SET lease_expires_at = DATE_SUB(CURRENT_TIMESTAMP(6), INTERVAL 1 SECOND) "
                "WHERE job_id = %s",
                (command.job_id,),
            )
        recovery_connection.commit()
        worker = DurableJobWorker(
            recovery_repository,
            recovery_connection,
            {"test.crash.resume": lambda payload: calls.append(payload) or ({"raw": "ignored"}, "result:recovered")},
            "worker-after-crash",
            retry_delay_seconds=0,
        )
        assert worker.recover_and_run_once() is True
        assert calls == [{"case": "synthetic"}]
        stored = recovery_repository.get_job(command.job_id)
        assert stored is not None and stored.status == "succeeded"
        assert stored.receipt_payload == {
            "kind": "success",
            "result_reference": "result:recovered",
            "schema_version": 1,
        }
        assert "raw" not in str(stored.receipt_payload)
    finally:
        recovery_connection.close()
