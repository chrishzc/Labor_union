"""
File: command_application.py
Description: 協調 Durable Job canonical enqueue 的唯一 outer transaction，回傳 accepted／replayed 結果。
"""

from __future__ import annotations

from dataclasses import dataclass

from shared_kernel.durable_job_queue import DurableJobCommand
from subsystems.jobs.ports import CanonicalDurableJobRepository, DurableJobTransaction


@dataclass(frozen=True, slots=True)
class DurableJobAcceptance:
    job_id: str
    replayed: bool


class DurableJobCommandApplication:
    def __init__(
        self,
        repository: CanonicalDurableJobRepository,
        transaction: DurableJobTransaction,
    ) -> None:
        self._repository = repository
        self._transaction = transaction

    def enqueue(self, command: DurableJobCommand) -> DurableJobAcceptance:
        """Persist or replay a canonical command under one explicit transaction."""
        self._transaction.begin()
        try:
            job_id = self._repository.enqueue_canonical_command(command)
            self._transaction.commit()
        except Exception:
            self._transaction.rollback()
            raise
        return DurableJobAcceptance(job_id, replayed=job_id != command.job_id)


class DurableJobCancellationApplication:
    def __init__(
        self,
        repository: CanonicalDurableJobRepository,
        transaction: DurableJobTransaction,
    ) -> None:
        self._repository = repository
        self._transaction = transaction

    def cancel_queued(self, job_id: str) -> None:
        self._transaction.begin()
        try:
            self._repository.cancel_queued_canonical_job(job_id)
            self._transaction.commit()
        except Exception:
            self._transaction.rollback()
            raise
