"""
File: test_durable_job_command_application.py
Description: 驗證 Durable Job Bridge 的單次提交、回滾、replay 與 typed conflict 傳遞。
"""

from __future__ import annotations

import pytest

from shared_kernel.durable_job_queue import DurableJobCommand
from subsystems.jobs.command_application import DurableJobCommandApplication
from subsystems.jobs.contracts import DurableJobCommandConflict


def _command(job_id: str = "job-new") -> DurableJobCommand:
    return DurableJobCommand(
        job_id=job_id,
        command_identity="bridge.command-1",
        command_type="bridge_test_apply",
        command_version=1,
        payload={"value": 1},
        submitted_by="admin_user_id:7",
        correlation_id="corr-1",
    )


class _Transaction:
    def __init__(self) -> None:
        self.begins = 0
        self.commits = 0
        self.rollbacks = 0

    def begin(self) -> None:
        self.begins += 1

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _Repository:
    def __init__(self, result: str = "job-new", error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.commands: list[DurableJobCommand] = []

    def enqueue_canonical_command(self, command: DurableJobCommand) -> str:
        self.commands.append(command)
        if self.error is not None:
            raise self.error
        return self.result

    def cancel_queued_canonical_job(self, job_id: str) -> None:
        if self.error is not None:
            raise self.error
        self.cancelled_job_id = job_id


def test_bridge_commits_once_and_reports_new_acceptance() -> None:
    transaction = _Transaction()
    repository = _Repository()
    command = _command()

    result = DurableJobCommandApplication(repository, transaction).enqueue(command)

    assert result.job_id == command.job_id
    assert result.replayed is False
    assert repository.commands == [command]
    assert (transaction.begins, transaction.commits, transaction.rollbacks) == (1, 1, 0)


def test_bridge_commits_replay_without_rewriting_identity() -> None:
    transaction = _Transaction()
    repository = _Repository(result="job-existing")

    result = DurableJobCommandApplication(repository, transaction).enqueue(_command())

    assert result.job_id == "job-existing"
    assert result.replayed is True
    assert (transaction.begins, transaction.commits, transaction.rollbacks) == (1, 1, 0)


def test_bridge_rolls_back_once_and_preserves_typed_conflict() -> None:
    conflict = DurableJobCommandConflict("job-existing", ("canonical_payload",))
    transaction = _Transaction()
    repository = _Repository(error=conflict)

    with pytest.raises(DurableJobCommandConflict) as raised:
        DurableJobCommandApplication(repository, transaction).enqueue(_command())

    assert raised.value is conflict
    assert (transaction.begins, transaction.commits, transaction.rollbacks) == (1, 0, 1)


def test_cancellation_bridge_owns_commit() -> None:
    from subsystems.jobs.command_application import DurableJobCancellationApplication

    transaction = _Transaction()
    repository = _Repository()

    DurableJobCancellationApplication(repository, transaction).cancel_queued("job-1")

    assert repository.cancelled_job_id == "job-1"
    assert (transaction.begins, transaction.commits, transaction.rollbacks) == (1, 1, 0)
