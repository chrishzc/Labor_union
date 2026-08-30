"""
File: outbox_worker.py
Description: 背景投遞各 Domain 已提交的 canonical anomaly outbox事件。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time

from shared_kernel.business_time import current_business_instant
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
from subsystems.anomalies.government_subsidy_anomaly_source import GovernmentSubsidyAnomalyScanRequest
from subsystems.anomalies.government_subsidy_assignment_drift_anomaly_source import GovernmentSubsidyAssignmentDriftScanRequest
from subsystems.anomalies.government_subsidy_integrity_anomaly_source import GovernmentSubsidyIntegrityScanRequest
from subsystems.anomalies.government_subsidy_reversal_anomaly_source import GovernmentSubsidyReversalScanRequest
from subsystems.anomalies.government_return_outbound_overage_anomaly_source import GovernmentReturnOutboundOverageScanRequest
from subsystems.anomalies.scheduling_coverage_anomaly_consumer import SchedulingCoverageScanRequest
from subsystems.anomalies.staff_payables_anomaly_source import StaffPayablesAnomalyScanCursors, consume_staff_payables_anomaly_sources
from subsystems.anomalies.ports import AnomalyRuntime, require_runtime
from subsystems.government_subsidy.subsidy_advance_outbox_consumer import (
    consume_government_subsidy_advance_events,
)
from subsystems.orders.client_finance_outbox_consumer import (
    consume_client_finance_orders_events,
)
from subsystems.access.security_alert_outbox import consume_security_alert_outbox

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
    staff_payables: StaffPayablesAnomalyScanCursors
    scheduling_after_source_identity: str | None
    scheduling_exhausted: bool
    government_subsidy_after_row_id: int
    government_subsidy_exhausted: bool
    government_subsidy_integrity_after_batch_id: int
    government_subsidy_integrity_exhausted: bool
    government_subsidy_reversal_after_row_id: int
    government_subsidy_reversal_exhausted: bool
    government_subsidy_assignment_drift_after_claim_item_id: int
    government_subsidy_assignment_drift_exhausted: bool
    government_return_outbound_overage_after_row_id: int
    government_return_outbound_overage_exhausted: bool
    process_reminder_exhausted: bool
    beclass_review_after_row_id: int
    beclass_review_exhausted: bool
    next_cycle_at: float

    @classmethod
    def start(cls):
        return cls(StaffPayablesAnomalyScanCursors.start(), None, False, 0, False, 0, False, 0, False, 0, False, 0, False, False, 0, False, 0.0)

    def cycle_complete(self) -> bool:
        staff_exhausted = all(cursor is None for cursor in (self.staff_payables.overdue_after_obligation_identity, self.staff_payables.late_change_after_event_id, self.staff_payables.bank_master_after_staff_id))
        return staff_exhausted and self.scheduling_exhausted and self.government_subsidy_exhausted and self.government_subsidy_integrity_exhausted and self.government_subsidy_reversal_exhausted and self.government_subsidy_assignment_drift_exhausted and self.government_return_outbound_overage_exhausted and self.process_reminder_exhausted and self.beclass_review_exhausted


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
        access_control = consume_security_alert_outbox(connection)
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
    if state is None: return 0, 0
    now = time.monotonic()
    if state.cycle_complete() and now < state.next_cycle_at: return 0, 0
    if state.cycle_complete(): _restart_source_cycle(state)
    results = _consume_source_pages(connection, state, runtime)
    if state.cycle_complete(): state.next_cycle_at = now + _SOURCE_SCAN_INTERVAL_SECONDS
    return tuple(sum(result[index] for result in results) for index in (0, 1))


def _consume_source_pages(connection, state, runtime):
    return (_consume_staff_source(connection, state, runtime), _consume_scheduling_source(connection, state, runtime), _consume_government_subsidy_source(connection, state, runtime), _consume_government_subsidy_integrity_source(connection, state, runtime), _consume_government_subsidy_reversal_source(connection, state, runtime), _consume_government_subsidy_assignment_drift_source(connection, state, runtime), _consume_government_return_outbound_overage_source(connection, state, runtime), _consume_process_reminder_source(connection, state, runtime), _consume_beclass_review_source(connection, state, runtime))


def _restart_source_cycle(state):
    state.staff_payables = StaffPayablesAnomalyScanCursors.start(); state.scheduling_after_source_identity = None; state.scheduling_exhausted = False
    state.government_subsidy_after_row_id = 0; state.government_subsidy_exhausted = False; state.government_subsidy_integrity_after_batch_id = 0; state.government_subsidy_integrity_exhausted = False
    state.government_subsidy_reversal_after_row_id = 0; state.government_subsidy_reversal_exhausted = False; state.government_subsidy_assignment_drift_after_claim_item_id = 0; state.government_subsidy_assignment_drift_exhausted = False; state.government_return_outbound_overage_after_row_id = 0; state.government_return_outbound_overage_exhausted = False
    state.process_reminder_exhausted = False
    state.beclass_review_after_row_id = 0; state.beclass_review_exhausted = False


def _consume_process_reminder_source(connection, state, runtime):
    if state.process_reminder_exhausted:
        return 0, 0
    try:
        with runtime.failure_unit_of_work(connection) as unit_of_work:
            result = runtime.consume_process_reminder_anomaly_sources(
                connection,
                as_of=current_business_instant().date(),
            )
            if not result.succeeded:
                state.process_reminder_exhausted = True
                return 0, 1
            unit_of_work.commit()
    except Exception:
        state.process_reminder_exhausted = True
        return 0, 1
    state.process_reminder_exhausted = True
    return result.projected_count, 0


def _consume_beclass_review_source(connection, state, runtime):
    if state.beclass_review_exhausted:
        return 0, 0
    try:
        result = runtime.project_beclass_import_review_page(
            connection,
            after_review_row_id=state.beclass_review_after_row_id,
            limit=_SOURCE_SCAN_PAGE_SIZE,
        )
    except Exception:
        state.beclass_review_exhausted = True
        return 0, 1
    state.beclass_review_after_row_id = result.next_review_row_id or 0
    state.beclass_review_exhausted = result.next_review_row_id is None
    return result.projected_count, 0


def _consume_staff_source(connection, state, runtime):
    result = runtime.consume_staff_payables_anomaly_sources(connection, as_of=current_business_instant().date(), maximum_items=_SOURCE_SCAN_PAGE_SIZE, cursors=state.staff_payables)
    if result.succeeded:
        state.staff_payables = result.cursors
        return result.projected_count, 0
    state.staff_payables = StaffPayablesAnomalyScanCursors(None, None, None, current_business_instant().date())
    return 0, 1


def _consume_scheduling_source(connection, state, runtime):
    if state.scheduling_exhausted: return 0, 0
    try:
        with runtime.failure_unit_of_work(connection) as unit_of_work:
            result = runtime.scheduling_coverage_consumer(connection).scan_page(SchedulingCoverageScanRequest(_SOURCE_SCAN_PAGE_SIZE, state.scheduling_after_source_identity))
            unit_of_work.commit()
    except Exception:
        state.scheduling_exhausted = True; return 0, 1
    state.scheduling_after_source_identity = result.next_source_identity; state.scheduling_exhausted = result.next_source_identity is None
    return len(result.projections), 0


def _consume_government_subsidy_source(connection, state, runtime): return _consume_bounded_source(connection, state, GovernmentSubsidyAnomalyScanRequest(_SOURCE_SCAN_PAGE_SIZE, state.government_subsidy_after_row_id), runtime.project_government_subsidy_anomaly_page, "next_finance_import_row_id", "government_subsidy_after_row_id", "government_subsidy_exhausted")
def _consume_government_subsidy_integrity_source(connection, state, runtime): return _consume_bounded_source(connection, state, GovernmentSubsidyIntegrityScanRequest(_SOURCE_SCAN_PAGE_SIZE, state.government_subsidy_integrity_after_batch_id), runtime.project_government_subsidy_integrity_page, "next_batch_id", "government_subsidy_integrity_after_batch_id", "government_subsidy_integrity_exhausted")
def _consume_government_subsidy_reversal_source(connection, state, runtime): return _consume_bounded_source(connection, state, GovernmentSubsidyReversalScanRequest(_SOURCE_SCAN_PAGE_SIZE, state.government_subsidy_reversal_after_row_id), runtime.project_government_subsidy_reversal_page, "next_finance_import_row_id", "government_subsidy_reversal_after_row_id", "government_subsidy_reversal_exhausted")
def _consume_government_subsidy_assignment_drift_source(connection, state, runtime): return _consume_bounded_source(connection, state, GovernmentSubsidyAssignmentDriftScanRequest(_SOURCE_SCAN_PAGE_SIZE, state.government_subsidy_assignment_drift_after_claim_item_id), runtime.project_government_subsidy_assignment_drift_page, "next_claim_item_id", "government_subsidy_assignment_drift_after_claim_item_id", "government_subsidy_assignment_drift_exhausted")
def _consume_government_return_outbound_overage_source(connection, state, runtime): return _consume_bounded_source(connection, state, GovernmentReturnOutboundOverageScanRequest(_SOURCE_SCAN_PAGE_SIZE, state.government_return_outbound_overage_after_row_id), runtime.project_government_return_outbound_overage_page, "next_finance_import_row_id", "government_return_outbound_overage_after_row_id", "government_return_outbound_overage_exhausted")


def _consume_bounded_source(connection, state, request, projector, next_cursor_field, state_cursor_field, exhausted_field):
    if getattr(state, exhausted_field): return 0, 0
    try: result = projector(connection, request)
    except Exception: setattr(state, exhausted_field, True); return 0, 1
    next_cursor = getattr(result, next_cursor_field); setattr(state, state_cursor_field, next_cursor or 0); setattr(state, exhausted_field, next_cursor is None)
    return len(result.projections), 0


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
