"""
File: test_durable_job_worker.py
Description: 驗證 Durable Job worker 的獨立交易、封閉 outcome、retry、exhaustion 與例外去敏。
"""

import pytest

from shared_kernel.durable_job_queue import (
    DurableJobCommand,
    DurableJobLease,
    RetryableDurableJobError,
    TerminalDurableJobError,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId
from infrastructure.mysql.background_job_repository import BackgroundJob
from subsystems.jobs.durable_job_worker import DurableJobWorker


class FakeRepository:
    def __init__(self, lease):
        self.lease = lease
        self.recovered = []
        self.completed = []
        self.failed = []

    def recover_expired_canonical_leases(self, delay):
        self.recovered.append(delay)
        return 0

    def claim_next_canonical_command(self, worker_id, lease_seconds):
        self.claim = (worker_id, lease_seconds)
        lease, self.lease = self.lease, None
        return lease

    def complete_canonical_claim(self, lease, outcome):
        self.completed.append((lease, outcome))

    def fail_canonical_claim(self, lease, outcome, retry_after_seconds=None):
        self.failed.append((lease, outcome, retry_after_seconds))


class FakeTransaction:
    def __init__(self):
        self.calls = []

    def begin(self):
        self.calls.append("begin")

    def commit(self):
        self.calls.append("commit")

    def rollback(self):
        self.calls.append("rollback")


def _lease(command_type="test.command"):
    command = DurableJobCommand(
        "job-1", "command-1", command_type, 1, {"item": "value"}, "admin_user_id:1", "corr-1"
    )
    return DurableJobLease("job-1", "lease-1", command, 1)


def test_worker_completes_only_the_claimed_lease():
    repository = FakeRepository(_lease())
    transaction = FakeTransaction()
    worker = DurableJobWorker(
        repository,
        transaction,
        {"test.command": lambda payload: ({"payload": payload}, "receipt-1")},
        "worker-1",
    )

    assert worker.recover_and_run_once() is True
    assert repository.claim == ("worker-1", 60)
    assert repository.completed[0][0] == _lease()
    assert repository.completed[0][1].to_payload() == {
        "kind": "success",
        "result_reference": "receipt-1",
        "schema_version": 1,
    }
    assert repository.failed == []
    assert transaction.calls == ["begin", "commit"] * 3


def test_retryable_failure_returns_the_same_command_to_queue():
    repository = FakeRepository(_lease())
    transaction = FakeTransaction()

    def retrying_handler(_):
        raise RetryableDurableJobError("database_busy", "database is busy")

    worker = DurableJobWorker(repository, transaction, {"test.command": retrying_handler}, "worker-1")

    assert worker.recover_and_run_once() is True
    assert repository.completed == []
    assert repository.failed[0][1].to_payload()["error"]["code"] == "database_busy"
    assert repository.failed[0][2] == 15


def test_unknown_command_is_terminal_and_does_not_run_a_domain_handler():
    repository = FakeRepository(_lease("unknown.command"))
    worker = DurableJobWorker(repository, FakeTransaction(), {}, "worker-1")

    assert worker.recover_and_run_once() is True
    assert repository.failed[0][1].to_payload()["error"]["code"] == "durable_job_handler_not_registered"
    assert repository.failed[0][2] is None


def test_terminal_domain_error_is_preserved_as_queryable_job_error():
    repository = FakeRepository(_lease())
    transaction = FakeTransaction()
    typed_error = TypedError(
        ErrorCategory.DOMAIN_BLOCKED,
        "auto_completion_blocked",
        "Order service completion is blocked.",
        CorrelationId("job-1"),
        domain_blockers=("auto_complete.human_hold_active",),
    )
    def blocked_handler(_payload):
        raise TerminalDurableJobError(typed_error)

    worker = DurableJobWorker(repository, transaction, {"test.command": blocked_handler}, "worker-1")

    assert worker.recover_and_run_once() is True
    error = repository.failed[0][1].to_payload()["error"]
    assert error["category"] == "domain_blocked"
    assert error["code"] == "auto_completion_blocked"
    assert error["domain_blockers"] == ["auto_complete.human_hold_active"]
    assert repository.failed[0][2] is None


def test_unexpected_handler_error_is_redacted_and_never_persists_str_error():
    repository = FakeRepository(_lease())

    def leaking_handler(_payload):
        raise RuntimeError("secret-token-must-not-escape")

    worker = DurableJobWorker(
        repository,
        FakeTransaction(),
        {"test.command": leaking_handler},
        "worker-1",
    )

    assert worker.recover_and_run_once() is True
    payload = repository.failed[0][1].to_payload()
    assert payload["schema_version"] == 1
    assert payload["error"]["message"] == "Durable job execution failed."
    assert "secret-token" not in str(payload)


def test_terminal_transition_failure_is_not_reclassified_as_handler_failure():
    repository = FakeRepository(_lease())

    def fail_transition(_lease, _outcome):
        raise RuntimeError("terminal write unavailable")

    repository.complete_canonical_claim = fail_transition
    transaction = FakeTransaction()
    worker = DurableJobWorker(
        repository,
        transaction,
        {"test.command": lambda _payload: ({"raw": "ignored"}, "result:1")},
        "worker-1",
    )

    with pytest.raises(RuntimeError, match="terminal write unavailable"):
        worker.recover_and_run_once()
    assert repository.failed == []
    assert transaction.calls[-2:] == ["begin", "rollback"]


def test_job_status_view_exposes_closed_durable_outcome():
    from api.routes.jobs import get_job_status

    class StatusRepository:
        def get_job(self, job_id):
            return BackgroundJob(
                job_id, "command-1", "succeeded",
                {"kind": "success", "schema_version": 1, "result_reference": "receipt-1"}, None,
                "finance_import_batch_apply", 2, 3, "receipt-1",
            )

    response = get_job_status("job-1", principal=None, repository=StatusRepository())

    assert response.data.command_type == "finance_import_batch_apply"
    assert response.data.attempt_count == 2
    assert response.data.outcome.result_reference == "receipt-1"
