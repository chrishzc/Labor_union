import os
import uuid
from argparse import Namespace

import pytest

from infrastructure.mysql.background_job_repository import BackgroundJobRepository
from infrastructure.mysql.mysql_adapter import get_connection
from scripts.bootstrap_disposable_mysql_schema import bootstrap
from shared_kernel.durable_job_queue import DurableJobCommand


pytestmark = pytest.mark.integration


def _require_disposable_database() -> None:
    database = os.environ.get("DB_DATABASE", "")
    if not database.startswith("lu_test_"):
        pytest.skip("requires an explicitly configured disposable MySQL database")


def _bootstrap_disposable_database() -> None:
    _require_disposable_database()
    bootstrap(
        Namespace(
            host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
            port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
            user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
            password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
            database=os.environ["LABOR_UNION_TEST_MYSQL_DATABASE"],
            confirm_database=os.environ["LABOR_UNION_TEST_MYSQL_DATABASE"],
        )
    )


def _command(job_id: str, identity: str) -> DurableJobCommand:
    return DurableJobCommand(
        job_id,
        identity,
        "test.durable.command",
        1,
        {"job_id": job_id},
        "test-admin",
        "test-correlation",
        max_attempts=2,
    )


def test_mysql_queue_retries_the_same_identity_and_completes_once():
    _bootstrap_disposable_database()
    job_id = "test-durable-" + uuid.uuid4().hex
    identity = "test-durable-identity-" + uuid.uuid4().hex
    connection = get_connection()
    repository = BackgroundJobRepository(connection)
    try:
        assert repository.enqueue_command(_command(job_id, identity)) == job_id
        first_lease = repository.claim_next_command("worker-a", 60)
        assert first_lease is not None
        assert first_lease.command.command_identity == identity
        assert first_lease.attempt_count == 1

        repository.fail_claimed_job(
            first_lease,
            {"error": {"code": "database_busy"}},
            retry_after_seconds=0,
        )
        second_lease = repository.claim_next_command("worker-b", 60)
        assert second_lease is not None
        assert second_lease.command.command_identity == identity
        assert second_lease.attempt_count == 2
        assert second_lease.lease_token != first_lease.lease_token

        repository.complete_claimed_job(
            second_lease,
            {"result": "ok"},
            "test-result-reference",
        )
        stored = repository.get_job(job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempt_count == 2
        assert stored.receipt_payload == {"result": "ok"}
        assert stored.result_reference == "test-result-reference"
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM background_jobs WHERE job_id = %s", (job_id,))
        connection.commit()
        connection.close()


def test_mysql_queue_recovers_an_expired_lease_without_changing_command_identity():
    _bootstrap_disposable_database()
    job_id = "test-durable-expired-" + uuid.uuid4().hex
    identity = "test-durable-expired-identity-" + uuid.uuid4().hex
    connection = get_connection()
    repository = BackgroundJobRepository(connection)
    try:
        repository.enqueue_command(_command(job_id, identity))
        first_lease = repository.claim_next_command("worker-a", 60)
        assert first_lease is not None
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE background_jobs SET lease_expires_at = DATE_SUB(CURRENT_TIMESTAMP(6), INTERVAL 1 SECOND) "
                "WHERE job_id = %s",
                (job_id,),
            )
        connection.commit()

        assert repository.requeue_expired_leases(0) == 1
        recovered_lease = repository.claim_next_command("worker-b", 60)
        assert recovered_lease is not None
        assert recovered_lease.command.command_identity == identity
        assert recovered_lease.attempt_count == 2
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM background_jobs WHERE job_id = %s", (job_id,))
        connection.commit()
        connection.close()
