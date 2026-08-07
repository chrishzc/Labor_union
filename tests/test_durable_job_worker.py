from shared_kernel.durable_job_queue import (
    DurableJobCommand,
    DurableJobLease,
    RetryableDurableJobError,
)
from infrastructure.mysql.background_job_repository import BackgroundJob
from subsystems.jobs.durable_job_worker import DurableJobWorker


class FakeRepository:
    def __init__(self, lease):
        self.lease = lease
        self.recovered = []
        self.completed = []
        self.failed = []

    def requeue_expired_leases(self, delay):
        self.recovered.append(delay)
        return 0

    def claim_next_command(self, worker_id, lease_seconds):
        self.claim = (worker_id, lease_seconds)
        lease, self.lease = self.lease, None
        return lease

    def complete_claimed_job(self, lease, receipt, reference):
        self.completed.append((lease, receipt, reference))

    def fail_claimed_job(self, lease, error, retry_after_seconds=None):
        self.failed.append((lease, error, retry_after_seconds))


def _lease(command_type="test.command"):
    command = DurableJobCommand(
        "job-1", "command-1", command_type, 1, {"item": "value"}, "admin", "corr-1"
    )
    return DurableJobLease("job-1", "lease-1", command, 1)


def test_worker_completes_only_the_claimed_lease():
    repository = FakeRepository(_lease())
    worker = DurableJobWorker(
        repository,
        {"test.command": lambda payload: ({"payload": payload}, "receipt-1")},
        "worker-1",
    )

    assert worker.recover_and_run_once() is True
    assert repository.claim == ("worker-1", 60)
    assert repository.completed == [(_lease(), {"payload": {"item": "value"}}, "receipt-1")]
    assert repository.failed == []


def test_retryable_failure_returns_the_same_command_to_queue():
    repository = FakeRepository(_lease())

    def retrying_handler(_):
        raise RetryableDurableJobError("database_busy", "database is busy")

    worker = DurableJobWorker(repository, {"test.command": retrying_handler}, "worker-1")

    assert worker.recover_and_run_once() is True
    assert repository.completed == []
    assert repository.failed[0][1]["error"]["code"] == "database_busy"
    assert repository.failed[0][2] == 15


def test_unknown_command_is_terminal_and_does_not_run_a_domain_handler():
    repository = FakeRepository(_lease("unknown.command"))
    worker = DurableJobWorker(repository, {}, "worker-1")

    assert worker.recover_and_run_once() is True
    assert repository.failed[0][1]["error"]["code"] == "durable_job_handler_not_registered"
    assert repository.failed[0][2] is None


def test_job_status_view_exposes_durable_attempt_and_receipt_fields():
    from api.routes.jobs import get_job_status

    class StatusRepository:
        def get_job(self, job_id):
            return BackgroundJob(
                job_id, "command-1", "succeeded", {"result": "ok"}, None,
                "finance_import_batch_apply", 2, 3, "receipt-1",
            )

    response = get_job_status("job-1", principal=None, repository=StatusRepository())

    assert response.data.command_type == "finance_import_batch_apply"
    assert response.data.attempt_count == 2
    assert response.data.result_reference == "receipt-1"
