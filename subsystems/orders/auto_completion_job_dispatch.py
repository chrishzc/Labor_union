"""
File: auto_completion_job_dispatch.py
Description: 掃描到期 Orders 並透過 canonical Durable Job Bridge 持久化自動完成命令。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
import hashlib
from typing import Protocol
from uuid import uuid4

from shared_kernel.clock import TAIPEI_TIME_ZONE
from shared_kernel.durable_job_queue import DurableJobCommand
from subsystems.jobs.command_application import DurableJobAcceptance


_COMMAND_TYPE = "orders_auto_completion_apply"
_SYSTEM_ACTOR = "system:orders-auto-completion"
_REASON = "scheduled service completion instant reached"


@dataclass(frozen=True, slots=True)
class DueOrderAutoCompletion:
    case_no: str
    lifecycle_version: int
    completion_instant: datetime

    def __post_init__(self) -> None:
        if not self.case_no or self.case_no != self.case_no.strip():
            raise ValueError("case_no must be a canonical string")
        if self.lifecycle_version < 0:
            raise ValueError("lifecycle_version must be non-negative")
        if self.completion_instant.tzinfo is None:
            raise ValueError("completion_instant must be timezone-aware")
        object.__setattr__(self, "completion_instant", self.completion_instant.astimezone(TAIPEI_TIME_ZONE))


@dataclass(frozen=True, slots=True)
class AutoCompletionDispatchReceipt:
    scanned_count: int
    enqueued_count: int
    duplicate_count: int


class DueOrderAutoCompletionReader(Protocol):
    def find_due_orders(
        self,
        evaluation_at: datetime,
        after_case_no: str | None,
        limit: int,
    ) -> Sequence[DueOrderAutoCompletion]: ...


class DurableCommandEnqueuer(Protocol):
    def enqueue(self, command: DurableJobCommand) -> DurableJobAcceptance: ...


class AutoCompletionJobDispatcher:
    """Pages stable candidate keys; the canonical workflow remains the final authority."""

    def __init__(
        self,
        due_order_reader: DueOrderAutoCompletionReader,
        job_enqueuer: DurableCommandEnqueuer,
    ) -> None:
        self._due_order_reader = due_order_reader
        self._job_enqueuer = job_enqueuer

    def dispatch_due_orders(
        self,
        evaluation_at: datetime,
        page_size: int = 100,
    ) -> AutoCompletionDispatchReceipt:
        normalized_evaluation = _taipei_instant(evaluation_at)
        if page_size < 1 or page_size > 200:
            raise ValueError("page_size must be between 1 and 200")
        return self._dispatch_pages(normalized_evaluation, page_size)

    def _dispatch_pages(
        self,
        evaluation_at: datetime,
        page_size: int,
    ) -> AutoCompletionDispatchReceipt:
        after_case_no: str | None = None
        counts = [0, 0, 0]
        while True:
            page = tuple(self._due_order_reader.find_due_orders(evaluation_at, after_case_no, page_size))
            if not page:
                return AutoCompletionDispatchReceipt(*counts)
            _validate_page(page, after_case_no, page_size)
            for due_order in page:
                counts[0] += 1
                if self._enqueue_due_order(due_order):
                    counts[1] += 1
                else:
                    counts[2] += 1
            after_case_no = page[-1].case_no

    def _enqueue_due_order(self, due_order: DueOrderAutoCompletion) -> bool:
        acceptance = self._job_enqueuer.enqueue(build_auto_completion_job_command(due_order))
        return not acceptance.replayed


def build_auto_completion_job_command(due_order: DueOrderAutoCompletion) -> DurableJobCommand:
    identity = _command_identity(due_order)
    payload = {
        "actor": _SYSTEM_ACTOR,
        "case_no": due_order.case_no,
        "correlation_id": identity,
        "evaluation_at": due_order.completion_instant.isoformat(),
        "expected_order_version": due_order.lifecycle_version,
        "idempotency_key": identity,
        "reason": _REASON,
    }
    return DurableJobCommand(
        job_id=str(uuid4()),
        command_identity=identity,
        command_type=_COMMAND_TYPE,
        command_version=1,
        payload=payload,
        submitted_by=_SYSTEM_ACTOR,
        correlation_id=identity,
    )


def _command_identity(due_order: DueOrderAutoCompletion) -> str:
    instant = due_order.completion_instant.strftime("%Y%m%dT%H%M%S%z")
    source = f"{due_order.case_no}\0{due_order.lifecycle_version}\0{instant}"
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return f"orders-auto-completion:{digest}"


def _taipei_instant(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("evaluation_at must be timezone-aware")
    return value.astimezone(TAIPEI_TIME_ZONE)


def _validate_page(
    page: tuple[DueOrderAutoCompletion, ...],
    after_case_no: str | None,
    page_size: int,
) -> None:
    if len(page) > page_size:
        raise ValueError("due-order reader exceeded page size")
    case_numbers = tuple(item.case_no for item in page)
    if case_numbers != tuple(sorted(set(case_numbers))):
        raise ValueError("due-order reader must return sorted unique case numbers")
    if after_case_no is not None and case_numbers[0] <= after_case_no:
        raise ValueError("due-order reader did not advance its cursor")


__all__ = [
    "AutoCompletionDispatchReceipt",
    "AutoCompletionJobDispatcher",
    "DueOrderAutoCompletion",
    "build_auto_completion_job_command",
]
