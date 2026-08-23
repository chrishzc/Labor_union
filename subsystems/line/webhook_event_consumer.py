"""
File: webhook_event_consumer.py
Description: 以獨立交易隔離 LINE webhook 業務處理與失敗完成紀錄。
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from domains.line.webhook import LineWebhookProcessingStatus
from subsystems.line.event_dispatcher import (
    LineEventDispatchStatus,
    LineEventDispatcher,
)
from subsystems.line.ports import LineUnitOfWorkPort
from subsystems.line.webhook_contracts import (
    ClaimLineWebhookEventsQuery,
    CompleteLineWebhookEventCommand,
)


class RetryableLineEventError(RuntimeError):
    pass


class TerminalLineEventError(RuntimeError):
    pass


class LineWebhookEventConsumer:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], LineUnitOfWorkPort],
        dispatcher: LineEventDispatcher,
        worker_identity: str,
        now: Callable[[], datetime],
        batch_size: int = 25,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._dispatcher = dispatcher
        self._worker_identity = worker_identity
        self._now = now
        self._batch_size = batch_size

    def run_once(self) -> int:
        claimed = self._claim()
        for event in claimed:
            self._consume(event)
        return len(claimed)

    def _claim(self):
        query = ClaimLineWebhookEventsQuery(
            self._worker_identity,
            self._now(),
            self._batch_size,
        )
        with self._unit_of_work_factory() as unit_of_work:
            claimed = unit_of_work.webhook_inbox.claim(query)
            unit_of_work.commit()
        return claimed

    def _consume(self, event) -> None:
        if event.lease is None:
            raise RuntimeError("claimed LINE webhook event has no lease")
        try:
            with self._unit_of_work_factory() as unit_of_work:
                result = self._dispatcher.dispatch(event, unit_of_work)
                status = (
                    "ignored"
                    if result.status is LineEventDispatchStatus.IGNORED
                    else "processed"
                )
                unit_of_work.webhook_inbox.complete(
                    _completion(event, self._now(), status)
                )
                unit_of_work.commit()
        except TerminalLineEventError as error:
            self._record_failure(event, "terminal_failed", error)
        except Exception as error:
            self._record_failure(event, "retryable_failed", error)

    def _record_failure(self, event, status: str, error: Exception) -> None:
        """Persist only failure completion after the business UoW has rolled back."""

        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.webhook_inbox.complete(
                _completion(event, self._now(), status, error)
            )
            unit_of_work.commit()


def _completion(event, completed_at, status: str, error: Exception | None = None):
    if status == "retryable_failed" and event.attempt_count >= event.max_attempts:
        status = "terminal_failed"
    return CompleteLineWebhookEventCommand(
        event,
        event.lease,
        LineWebhookProcessingStatus(status),
        completed_at,
        error_code=type(error).__name__ if error else None,
        error_message=str(error)[:1000] if error else None,
        retry_after_seconds=15 if status == "retryable_failed" else None,
    )


__all__ = [
    "LineWebhookEventConsumer",
    "RetryableLineEventError",
    "TerminalLineEventError",
]
