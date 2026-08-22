"""
File: test_durable_job_payload_equality_disposable_mysql_e2e.py
Description: 以唯一 lu_test DB 證明 JSON typed equality、Unicode、null、物件排序、陣列排序與 Key/key collation。
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pymysql
import pytest

from infrastructure.mysql.background_job_repository import BackgroundJobRepository
from shared_kernel.durable_job_queue import DurableJobCommand
from subsystems.jobs.contracts import DurableJobCommandConflict


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
def equality_database():
    required = (
        "LABOR_UNION_TEST_MYSQL_HOST",
        "LABOR_UNION_TEST_MYSQL_PORT",
        "LABOR_UNION_TEST_MYSQL_USER",
        "LABOR_UNION_TEST_MYSQL_PASSWORD",
    )
    missing = [name for name in required if os.environ.get(name) is None]
    assert not missing, "BLOCKED_ENGINE_EVIDENCE: missing " + ",".join(missing)
    database = "lu_test_durable_equality_" + uuid.uuid4().hex[:12]
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


def _command(key: str, payload: dict, job_id: str | None = None) -> DurableJobCommand:
    return DurableJobCommand(
        job_id or "job-" + uuid.uuid4().hex,
        key,
        "test.payload.equality",
        1,
        payload,
        "system:durable-equality-test",
        "corr-" + uuid.uuid4().hex,
        2,
    )


def test_mysql_round_trip_treats_object_order_as_equal_and_preserves_unicode_null(
    equality_database,
) -> None:
    connection = _connect_queue_database(equality_database)
    repository = BackgroundJobRepository(connection)
    key = "job.equality." + uuid.uuid4().hex
    first = _command(key, {"z": None, "items": [1, 1.0, "台灣"], "object": {"b": 2, "a": 1}})
    try:
        connection.begin()
        repository.enqueue_canonical_command(first)
        connection.commit()
        connection.begin()
        replayed_id = repository.enqueue_canonical_command(
            _command(key, {"object": {"a": 1, "b": 2}, "items": [1, 1.0, "台灣"], "z": None})
        )
        connection.commit()
        assert replayed_id == first.job_id
        stored = repository.read_canonical_command_by_identity(key)
        assert stored is not None
        assert stored.payload == {"items": [1, 1.0, "台灣"], "object": {"a": 1, "b": 2}, "z": None}
    finally:
        connection.close()


@pytest.mark.parametrize(
    "baseline,mismatch",
    [
        ({"value": 1}, {"value": 1.0}),
        ({"items": [1, 2]}, {"items": [2, 1]}),
        ({"value": None}, {"value": "null"}),
    ],
)
def test_mysql_round_trip_rejects_typed_or_array_order_mismatch(
    equality_database,
    baseline,
    mismatch,
) -> None:
    connection = _connect_queue_database(equality_database)
    repository = BackgroundJobRepository(connection)
    key = "job.typed." + uuid.uuid4().hex
    try:
        connection.begin()
        repository.enqueue_canonical_command(_command(key, baseline))
        connection.commit()
        connection.begin()
        with pytest.raises(DurableJobCommandConflict) as raised:
            repository.enqueue_canonical_command(_command(key, mismatch))
        connection.rollback()
        assert raised.value.mismatched_fields == ("canonical_payload",)
    finally:
        connection.close()
