"""
File: test_background_job_repository_mysql.py
Description: 以單一唯一 lu_test DB 驗證 canonical Durable Job replay、conflict、lifecycle 與 fail-closed reader。
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pymysql
import pytest

from infrastructure.mysql.background_job_repository import BackgroundJobRepository
from shared_kernel.durable_job_queue import DurableJobCommand
from subsystems.jobs.contracts import (
    DurableJobCommandConflict,
    DurableJobContractViolation,
    DurableJobFailureOutcome,
    DurableJobSuccessOutcome,
)


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
def disposable_database():
    required = (
        "LABOR_UNION_TEST_MYSQL_HOST",
        "LABOR_UNION_TEST_MYSQL_PORT",
        "LABOR_UNION_TEST_MYSQL_USER",
        "LABOR_UNION_TEST_MYSQL_PASSWORD",
    )
    missing = [name for name in required if os.environ.get(name) is None]
    assert not missing, "BLOCKED_ENGINE_EVIDENCE: missing " + ",".join(missing)
    database = "lu_test_durable_core_" + uuid.uuid4().hex[:12]
    assert database.startswith("lu_test_") and database != "union_db"
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


def _command(key: str, **overrides) -> DurableJobCommand:
    values = {
        "job_id": "job-" + uuid.uuid4().hex,
        "command_identity": key,
        "command_type": "test.durable.command",
        "command_version": 1,
        "payload": {"items": [1, 1.0, None, "台灣"], "object": {"b": 2, "a": 1}},
        "submitted_by": "admin_user_id:41",
        "correlation_id": "corr-" + uuid.uuid4().hex,
        "max_attempts": 2,
    }
    values.update(overrides)
    return DurableJobCommand(**values)


def _delete_keys(connection, *keys: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM background_jobs WHERE command_identity IN ("
            + ",".join(["%s"] * len(keys))
            + ")",
            keys,
        )
    connection.commit()


def test_same_key_same_equality_replays_identity_while_correlation_is_observation_only(
    disposable_database,
) -> None:
    connection = _connect_queue_database(disposable_database)
    repository = BackgroundJobRepository(connection)
    key = "job.replay." + uuid.uuid4().hex
    first = _command(key)
    try:
        connection.begin()
        assert repository.enqueue_canonical_command(first) == first.job_id
        connection.commit()
        replay = _command(
            key,
            command_type=first.command_type,
            command_version=first.command_version,
            payload=first.payload,
            submitted_by=first.submitted_by,
            correlation_id="corr-observation-changed",
        )
        connection.begin()
        assert repository.enqueue_canonical_command(replay) == first.job_id
        connection.commit()
    finally:
        _delete_keys(connection, key)
        connection.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("command_type", "test.other.command"),
        ("command_version", 2),
        ("payload", {"items": [1.0, 1, None, "台灣"], "object": {"a": 1, "b": 2}}),
        ("submitted_by", "admin_user_id:42"),
    ],
)
def test_same_key_mismatch_is_typed_conflict(disposable_database, field, value) -> None:
    connection = _connect_queue_database(disposable_database)
    repository = BackgroundJobRepository(connection)
    key = "job.conflict." + uuid.uuid4().hex
    first = _command(key)
    try:
        connection.begin()
        repository.enqueue_canonical_command(first)
        connection.commit()
        changed = {
            "command_type": first.command_type,
            "command_version": first.command_version,
            "payload": first.payload,
            "submitted_by": first.submitted_by,
        }
        changed[field] = value
        mismatch = _command(key, **changed)
        connection.begin()
        with pytest.raises(DurableJobCommandConflict) as raised:
            repository.enqueue_canonical_command(mismatch)
        connection.rollback()
        expected_field = "canonical_payload" if field == "payload" else field
        assert expected_field in raised.value.mismatched_fields
    finally:
        _delete_keys(connection, key)
        connection.close()


def test_key_case_collision_and_legacy_null_fail_closed(disposable_database) -> None:
    connection = _connect_queue_database(disposable_database)
    repository = BackgroundJobRepository(connection)
    suffix = uuid.uuid4().hex
    uppercase_key = "job.Case." + suffix
    lowercase_key = uppercase_key.lower()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO background_jobs "
                "(job_id,command_identity,command_type,command_version,command_payload,submitted_by,correlation_id,status,max_attempts) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'queued',%s)",
                ("legacy-case-" + suffix, uppercase_key, "test.durable.command", 1, "{}", "admin_user_id:41", "corr-case", 2),
            )
            cursor.execute(
                "INSERT INTO background_jobs (job_id,command_identity,status) VALUES (%s,%s,'queued')",
                ("legacy-null-" + suffix, "job.legacy." + suffix),
            )
        connection.commit()
        connection.begin()
        with pytest.raises(DurableJobCommandConflict) as raised:
            repository.enqueue_canonical_command(_command(lowercase_key))
        connection.rollback()
        assert "command_identity" in raised.value.mismatched_fields
        with pytest.raises(DurableJobContractViolation):
            repository.read_canonical_command_by_identity("job.legacy." + suffix)
    finally:
        _delete_keys(connection, uppercase_key, "job.legacy." + suffix)
        connection.close()


def test_canonical_retry_and_terminal_outcome_are_closed(disposable_database) -> None:
    connection = _connect_queue_database(disposable_database)
    repository = BackgroundJobRepository(connection)
    command = _command("job.lifecycle." + uuid.uuid4().hex)
    try:
        connection.begin()
        repository.enqueue_canonical_command(command)
        connection.commit()
        connection.begin()
        first = repository.claim_next_canonical_command("worker-a", 60)
        connection.commit()
        assert first is not None
        connection.begin()
        repository.fail_canonical_claim(
            first,
            DurableJobFailureOutcome("unavailable", "database_busy", "Retry later.", True),
            0,
        )
        connection.commit()
        connection.begin()
        second = repository.claim_next_canonical_command("worker-b", 60)
        connection.commit()
        assert second is not None and second.attempt_count == 2
        connection.begin()
        repository.complete_canonical_claim(second, DurableJobSuccessOutcome("result:safe"))
        connection.commit()
        stored = repository.get_job(command.job_id)
        assert stored is not None and stored.status == "succeeded"
        assert stored.receipt_payload == {
            "kind": "success",
            "result_reference": "result:safe",
            "schema_version": 1,
        }
        assert stored.result_reference == "result:safe"
    finally:
        _delete_keys(connection, command.command_identity)
        connection.close()
