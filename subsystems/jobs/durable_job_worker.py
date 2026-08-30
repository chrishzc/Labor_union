"""
File: durable_job_worker.py
Description: 編排 Durable Job recovery、claim、handler 與 terminal transition 的獨立 outer transactions。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from shared_kernel.durable_job_queue import (
    DurableJobLease,
    RetryableDurableJobError,
    TerminalDurableJobError,
)
from subsystems.jobs.contracts import DurableJobFailureOutcome, DurableJobSuccessOutcome
from subsystems.jobs.ports import CanonicalDurableJobRepository, DurableJobTransaction

JobHandler = Callable[[dict[str, Any]], tuple[dict[str, Any], str]]


class DurableJobWorker:
    def __init__(
        self,
        repository: CanonicalDurableJobRepository,
        transaction: DurableJobTransaction,
        handlers: dict[str, JobHandler],
        worker_id: str,
        lease_seconds: int = 60,
        retry_delay_seconds: int = 15,
    ):
        self._repository = repository
        self._transaction = transaction
        self._handlers = handlers
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._retry_delay_seconds = retry_delay_seconds

    def recover_and_run_once(self) -> bool:
        self._in_transaction(
            lambda: self._repository.recover_expired_canonical_leases(
                self._retry_delay_seconds
            )
        )
        lease = self._in_transaction(
            lambda: self._repository.claim_next_canonical_command(
                self._worker_id,
                self._lease_seconds,
            )
        )
        if lease is None:
            return False
        self._execute_lease(lease)
        return True

    def _execute_lease(self, lease: DurableJobLease) -> None:
        handler = self._handlers.get(lease.command.command_type)
        if handler is None:
            self._fail_unknown_command(lease)
            return
        try:
            _private_receipt, reference = handler(lease.command.payload)
        except TerminalDurableJobError as error:
            outcome = DurableJobFailureOutcome.from_typed_error(error.error)
            self._in_transaction(
                lambda: self._repository.fail_canonical_claim(lease, outcome)
            )
        except RetryableDurableJobError as error:
            outcome = DurableJobFailureOutcome(
                "unavailable",
                error.code,
                error.message,
                retryable=True,
            )
            self._in_transaction(
                lambda: self._repository.fail_canonical_claim(
                    lease,
                    outcome,
                    self._retry_delay_seconds,
                )
            )
        except Exception:
            outcome = DurableJobFailureOutcome(
                "internal",
                "durable_job_execution_failed",
                "Durable job execution failed.",
            )
            self._in_transaction(
                lambda: self._repository.fail_canonical_claim(lease, outcome)
            )
        else:
            outcome = DurableJobSuccessOutcome(reference)
            self._in_transaction(
                lambda: self._repository.complete_canonical_claim(lease, outcome)
            )

    def _fail_unknown_command(self, lease: DurableJobLease) -> None:
        outcome = DurableJobFailureOutcome(
            "internal",
            "durable_job_handler_not_registered",
            "No durable worker handler is registered for this command.",
        )
        self._in_transaction(
            lambda: self._repository.fail_canonical_claim(lease, outcome)
        )

    def _in_transaction(self, operation):
        self._transaction.begin()
        try:
            result = operation()
            self._transaction.commit()
            return result
        except Exception:
            self._transaction.rollback()
            raise
