"""Independent canonical LINE worker orchestration and dynamic wake scheduling."""

from __future__ import annotations

import json
import os
import socket
import threading
from datetime import datetime, timezone
from typing import Callable, Mapping

from subsystems.line.delivery_worker import LineDeliveryWorker
from subsystems.line.ports import LineWakeupSubscriberPort
from subsystems.line.runtime_contracts import LineRuntimeMode, LineWorkerHeartbeat
from subsystems.line.webhook_event_consumer import LineWebhookEventConsumer


class CanonicalLineWorkerRuntime:
    def __init__(
        self,
        event_consumer: LineWebhookEventConsumer,
        delivery_worker: LineDeliveryWorker,
        wakeup_subscriber: LineWakeupSubscriberPort,
        next_due_at: Callable[[], datetime | None],
        heartbeat_writer: Callable[[LineWorkerHeartbeat], None],
        worker_identity: str,
        fallback_scan_seconds: float = 60.0,
        additional_workers: Mapping[str, object] | None = None,
    ) -> None:
        self._event_consumer = event_consumer
        self._delivery_worker = delivery_worker
        self._wakeup_subscriber = wakeup_subscriber
        self._next_due_at = next_due_at
        self._heartbeat_writer = heartbeat_writer
        self._worker_identity = worker_identity
        self._fallback_scan_seconds = fallback_scan_seconds
        self._additional_workers = dict(additional_workers or {})

    def run_once(self) -> dict[str, int]:
        counts = {
            "inbox_events": self._event_consumer.run_once(),
            "delivery_tasks": self._delivery_worker.run_once(),
        }
        for name, worker in self._additional_workers.items():
            counts[name] = worker.run_once()
        self._record_heartbeat(counts)
        return counts

    def run_forever(self, stop_event: threading.Event | None = None) -> None:
        stop_event = stop_event or threading.Event()
        while not stop_event.is_set():
            try:
                self.run_once()
                self._wait_for_work(stop_event)
            except Exception as error:
                try:
                    self._record_failure(error)
                except Exception as heartbeat_error:
                    print(f"[LINE Worker] Heartbeat unavailable: {heartbeat_error}")
                stop_event.wait(5.0)

    def _wait_for_work(self, stop_event: threading.Event) -> None:
        timeout = self._wait_seconds(datetime.now(timezone.utc))
        if stop_event.is_set():
            return
        self._wakeup_subscriber.wait(timeout)

    def _wait_seconds(self, now: datetime) -> float:
        next_due_at = self._next_due_at()
        if next_due_at is None:
            return self._fallback_scan_seconds
        normalized_due_at = next_due_at.astimezone(timezone.utc)
        due_in = max(0.0, (normalized_due_at - now).total_seconds())
        return min(self._fallback_scan_seconds, due_in)

    def _record_heartbeat(self, counts: dict[str, int]) -> None:
        now = datetime.now(timezone.utc)
        heartbeat = _heartbeat(self._worker_identity, now, counts)
        self._heartbeat_writer(heartbeat)

    def _record_failure(self, error: Exception) -> None:
        now = datetime.now(timezone.utc)
        heartbeat = _heartbeat(
            self._worker_identity,
            now,
            {
                "inbox_events": 0,
                "delivery_tasks": 0,
                **{name: 0 for name in self._additional_workers},
            },
            error,
        )
        self._heartbeat_writer(heartbeat)


def _heartbeat(worker_identity, now, counts, error: Exception | None = None):
    return LineWorkerHeartbeat(
        worker_identity,
        os.getpid(),
        socket.gethostname(),
        LineRuntimeMode.CANONICAL,
        json.dumps(counts, sort_keys=True, separators=(",", ":")),
        now,
        last_cycle_at=now,
        last_error_code=type(error).__name__ if error else None,
        last_error_message=str(error)[:1000] if error else None,
    )


__all__ = ["CanonicalLineWorkerRuntime"]
