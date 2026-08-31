"""
File: outbox_worker.py
Description: 背景投遞各 Domain 已提交的 canonical anomaly outbox事件。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time

from subsystems.case_import.beclass_import_outbox_consumer import consume_beclass_import_review_events
from subsystems.anomalies.hcm_import_review_outbox_consumer import consume_hcm_import_review_events
from subsystems.case_import.hcm_resubmission_outbox_consumer import consume_hcm_resubmission_outbox
from subsystems.orders.historical_order_adoption_outbox_consumer import (
    consume_historical_order_adoption_review_events,
)
from subsystems.orders.historical_order_review_remediation_outbox_consumer import (
    consume_historical_order_review_remediation_events,
)
from subsystems.finance_import.finance_import_anomaly_consumer import consume_finance_import_anomaly_events
from subsystems.anomalies.ports import AnomalyRuntime, require_runtime
from subsystems.government_subsidy.subsidy_advance_outbox_consumer import (
    consume_government_subsidy_advance_events,
)
from subsystems.orders.client_finance_outbox_consumer import (
    consume_client_finance_orders_events,
)
from subsystems.access.security_alert_outbox import consume_security_alert_outbox
from subsystems.anomalies.system_alert_projection import upsert_system_alert

_POLL_INTERVAL_SECONDS = 2.0
_SOURCE_SCAN_INTERVAL_SECONDS = 60.0
_SOURCE_SCAN_PAGE_SIZE = 25
_worker_task: asyncio.Task[None] | None = None
_wakeup_event = asyncio.Event()


@dataclass(frozen=True, slots=True)
class ArchitectureDeliveryResult:
    delivered_count: int
    failed_count: int


@dataclass(slots=True)
class ArchitectureSourceScanState:
    scheduling_after_source_identity: str | None
    scheduling_exhausted: bool
    government_subsidy_after_row_id: int
    government_subsidy_exhausted: bool
    government_subsidy_reversal_after_row_id: int
    government_subsidy_reversal_exhausted: bool
    process_reminder_exhausted: bool
    beclass_review_after_row_id: int
    beclass_review_exhausted: bool
    next_cycle_at: float

    @classmethod
    def start(cls):
        return cls(None, True, 0, True, 0, True, True, 0, True, 0.0)

    def cycle_complete(self) -> bool:
        return True


class BorrowedAnomalyUnitOfWork:
    def __enter__(self): return self
    def __exit__(self, exception_type, exception, traceback): return False
    def commit(self): return None
    def rollback(self): return None


def wake_architecture_outbox_worker() -> None:
    _wakeup_event.set()


def _consume_once(source_scan_state: ArchitectureSourceScanState | None = None, runtime: AnomalyRuntime | None = None):
    runtime = require_runtime(runtime)
    connection = runtime.connection()
    try:
        finance = consume_finance_import_anomaly_events(connection, runtime=runtime)
        beclass = consume_beclass_import_review_events(connection, runtime=runtime)
        hcm = consume_hcm_import_review_events(connection, runtime=runtime)
        hcm_resubmission_delivered = consume_hcm_resubmission_outbox(connection, runtime=runtime)
        historical_order = consume_historical_order_adoption_review_events(
            connection, runtime=runtime
        )
        historical_order_remediation = (
            consume_historical_order_review_remediation_events(
                connection, runtime=runtime
            )
        )
        subsidy_advance_delivered, subsidy_advance_failed = (
            consume_government_subsidy_advance_events(
                connection,
                runtime.subsidy_advance_recovery_repository,
            )
        )
        deposit_delivered, deposit_failed = consume_client_finance_orders_events(
            connection
        )
        access_control = consume_security_alert_outbox(
            connection,
            project_alert=upsert_system_alert,
        )
        source_delivered, source_failed = _consume_sources_if_due(connection, source_scan_state, runtime)
        return ArchitectureDeliveryResult(
            finance.delivered_count + beclass.delivered_count + hcm.delivered_count + hcm_resubmission_delivered + historical_order.delivered_count + historical_order_remediation.delivered_count + subsidy_advance_delivered + deposit_delivered + access_control.delivered_count + source_delivered,
            finance.failed_count + beclass.failed_count + hcm.failed_count + historical_order.failed_count + historical_order_remediation.failed_count + subsidy_advance_failed + deposit_failed + access_control.failed_count + source_failed,
        )
    finally:
        connection.close()


def consume_architecture_outbox_once(
    source_scan_state: ArchitectureSourceScanState | None = None,
    *,
    runtime: AnomalyRuntime | None = None,
) -> ArchitectureDeliveryResult:
    """Run one complete API-owned delivery cycle without starting a background thread."""
    return _consume_once(source_scan_state, runtime)


def _consume_sources_if_due(connection, state, runtime: AnomalyRuntime):
    if state is None:
        return 0, 0
    now = time.monotonic()
    if now < state.next_cycle_at:
        return 0, 0
    # The former periodic producers are retired. Keep the bounded scheduler
    # state so callers retain a stable worker contract, but do no source I/O.
    state.next_cycle_at = now + _SOURCE_SCAN_INTERVAL_SECONDS
    return 0, 0


def _consume_source_pages(connection, state, runtime):
    # Current Anomalies are refreshed by typed ``anomaly.recheck`` jobs after
    # an owner commit.  Periodic source scans are deliberately not a producer
    # path for retired anomaly definitions.
    del connection, state, runtime
    return ()


async def architecture_outbox_worker_loop(runtime: AnomalyRuntime) -> None:
    state = ArchitectureSourceScanState.start()
    while True:
        try:
            result = await asyncio.to_thread(_consume_once, state, runtime)
            if result.delivered_count: continue
            _wakeup_event.clear()
            try: await asyncio.wait_for(_wakeup_event.wait(), timeout=_POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError: pass
        except asyncio.CancelledError: raise
        except Exception as error:
            print(f"[Architecture Outbox] worker error: {error}")
            await asyncio.sleep(5)


def start_architecture_outbox_worker(runtime: AnomalyRuntime) -> asyncio.Task[None]:
    global _worker_task
    _worker_task = asyncio.create_task(architecture_outbox_worker_loop(runtime), name="architecture-outbox-worker")
    return _worker_task


async def stop_architecture_outbox_worker(task: asyncio.Task[None]) -> None:
    global _worker_task
    task.cancel()
    try: await task
    except asyncio.CancelledError: pass
    finally:
        if _worker_task is task: _worker_task = None


__all__ = [
    "ArchitectureDeliveryResult",
    "ArchitectureSourceScanState",
    "consume_architecture_outbox_once",
    "start_architecture_outbox_worker",
    "stop_architecture_outbox_worker",
    "wake_architecture_outbox_worker",
]
