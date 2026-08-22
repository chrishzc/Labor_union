"""
File: ports.py
Description: 定義 Durable Job worker 使用且禁止 hidden commit/rollback 的 canonical repository port。
"""

from __future__ import annotations

from typing import Protocol

from shared_kernel.durable_job_queue import DurableJobCommand, DurableJobLease
from subsystems.jobs.contracts import DurableJobFailureOutcome, DurableJobSuccessOutcome


class CanonicalDurableJobRepository(Protocol):
    def assert_durable_queue_schema(self) -> None: ...

    def enqueue_canonical_command(self, command: DurableJobCommand) -> str: ...

    def cancel_queued_canonical_job(self, job_id: str) -> None: ...

    def recover_expired_canonical_leases(self, retry_delay_seconds: int) -> int: ...

    def claim_next_canonical_command(
        self,
        worker_id: str,
        lease_seconds: int,
    ) -> DurableJobLease | None: ...

    def complete_canonical_claim(
        self,
        lease: DurableJobLease,
        outcome: DurableJobSuccessOutcome,
    ) -> None: ...

    def fail_canonical_claim(
        self,
        lease: DurableJobLease,
        outcome: DurableJobFailureOutcome,
        retry_after_seconds: int | None = None,
    ) -> None: ...


class DurableJobTransaction(Protocol):
    def begin(self) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
