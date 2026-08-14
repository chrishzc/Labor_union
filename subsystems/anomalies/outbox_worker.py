"""
File: outbox_worker.py
Description: 背景投遞各 Domain 已提交的 canonical anomaly outbox事件。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time

from domains.anomalies.registry import default_anomaly_registry
from infrastructure.mysql.government_subsidy_anomaly_source import project_government_subsidy_anomaly_page
from infrastructure.mysql.government_subsidy_assignment_drift_anomaly_source import project_government_subsidy_assignment_drift_page
from infrastructure.mysql.government_subsidy_integrity_anomaly_source import project_government_subsidy_integrity_page
from infrastructure.mysql.government_subsidy_reversal_anomaly_source import project_government_subsidy_reversal_anomaly_page
from infrastructure.mysql.government_return_outbound_overage_anomaly_source import project_government_return_outbound_overage_page
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.anomaly_registry_repository import MySqlAnomalyRepository
from infrastructure.mysql.beclass_import_review_anomaly_source import project_beclass_import_review_page
from infrastructure.mysql.process_reminder_anomaly_source import consume_process_reminder_anomaly_sources
from infrastructure.mysql.scheduling_coverage_anomaly_source import MySqlSchedulingCoverageAnomalySource
from shared_kernel.business_time import current_business_instant
from subsystems.anomalies.alert_workflow import AnomalyApplication
from subsystems.anomalies.beclass_import_outbox_consumer import consume_beclass_import_review_events
from subsystems.anomalies.hcm_import_review_outbox_consumer import consume_hcm_import_review_events
from subsystems.anomalies.historical_order_adoption_outbox_consumer import (
    consume_historical_order_adoption_review_events,
)
from subsystems.anomalies.finance_import_anomaly_consumer import consume_finance_import_anomaly_events
from subsystems.anomalies.government_overpayment_anomaly_consumer import (
    consume_government_overpayment_anomaly_events,
)
from subsystems.anomalies.client_over_refund_recovery_anomaly_consumer import (
    consume_client_over_refund_recovery_anomaly_events,
)
from subsystems.anomalies.client_refund_underpayment_anomaly_consumer import (
    consume_client_refund_underpayment_anomaly_events,
)
from subsystems.anomalies.staff_overpayment_recovery_anomaly_consumer import (
    consume_staff_overpayment_recovery_anomaly_events,
)
from subsystems.anomalies.staff_payout_difference_anomaly_consumer import consume_staff_payout_difference_anomaly_events
from subsystems.anomalies.government_subsidy_anomaly_source import GovernmentSubsidyAnomalyScanRequest
from subsystems.anomalies.government_subsidy_assignment_drift_anomaly_source import GovernmentSubsidyAssignmentDriftScanRequest
from subsystems.anomalies.government_subsidy_integrity_anomaly_source import GovernmentSubsidyIntegrityScanRequest
from subsystems.anomalies.government_subsidy_reversal_anomaly_source import GovernmentSubsidyReversalScanRequest
from subsystems.anomalies.government_return_outbound_overage_anomaly_source import GovernmentReturnOutboundOverageScanRequest
from subsystems.anomalies.scheduling_coverage_anomaly_consumer import SchedulingCoverageAnomalyConsumer, SchedulingCoverageScanRequest
from subsystems.anomalies.staff_payables_anomaly_source import StaffPayablesAnomalyScanCursors, consume_staff_payables_anomaly_sources
from subsystems.client_finance.subsidy_advance_outbox_consumer import (
    consume_government_subsidy_advance_events,
)
from subsystems.orders.client_finance_outbox_consumer import (
    consume_client_finance_orders_events,
)

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


def _consume_once(source_scan_state: ArchitectureSourceScanState | None = None):
    connection = get_connection()
    try:
        finance = consume_finance_import_anomaly_events(connection)
        beclass = consume_beclass_import_review_events(connection)
        hcm = consume_hcm_import_review_events(connection)
        historical_order = consume_historical_order_adoption_review_events(connection)
        subsidy_advance_delivered, subsidy_advance_failed = (
            consume_government_subsidy_advance_events(connection)
        )
        overpayment_delivered, overpayment_failed = (
            consume_government_overpayment_anomaly_events(connection)
        )
        client_recovery_delivered, client_recovery_failed = (
            consume_client_over_refund_recovery_anomaly_events(connection)
        )
        client_underpayment_delivered, client_underpayment_failed = (
            consume_client_refund_underpayment_anomaly_events(connection)
        )
        staff_recovery_delivered, staff_recovery_failed = (
            consume_staff_overpayment_recovery_anomaly_events(connection)
        )
        staff_difference_delivered, staff_difference_failed = consume_staff_payout_difference_anomaly_events(connection)
        deposit_delivered, deposit_failed = consume_client_finance_orders_events(
            connection
        )
        source_delivered, source_failed = _consume_sources_if_due(connection, source_scan_state)
        return ArchitectureDeliveryResult(
            finance.delivered_count + beclass.delivered_count + hcm.delivered_count + historical_order.delivered_count + subsidy_advance_delivered + overpayment_delivered + client_recovery_delivered + client_underpayment_delivered + staff_recovery_delivered + staff_difference_delivered + deposit_delivered + source_delivered,
            finance.failed_count + beclass.failed_count + hcm.failed_count + historical_order.failed_count + subsidy_advance_failed + overpayment_failed + client_recovery_failed + client_underpayment_failed + staff_recovery_failed + staff_difference_failed + deposit_failed + source_failed,
        )
    finally:
        connection.close()


def _consume_sources_if_due(connection, state):
    if state is None: return 0, 0
    now = time.monotonic()
    if state.cycle_complete() and now < state.next_cycle_at: return 0, 0
    if state.cycle_complete(): _restart_source_cycle(state)
    results = _consume_source_pages(connection, state)
    if state.cycle_complete(): state.next_cycle_at = now + _SOURCE_SCAN_INTERVAL_SECONDS
    return tuple(sum(result[index] for result in results) for index in (0, 1))


def _consume_source_pages(connection, state):
    return (_consume_staff_source(connection, state), _consume_scheduling_source(connection, state), _consume_government_subsidy_source(connection, state), _consume_government_subsidy_integrity_source(connection, state), _consume_government_subsidy_reversal_source(connection, state), _consume_government_subsidy_assignment_drift_source(connection, state), _consume_government_return_outbound_overage_source(connection, state), _consume_process_reminder_source(connection, state), _consume_beclass_review_source(connection, state))


def _restart_source_cycle(state):
    state.staff_payables = StaffPayablesAnomalyScanCursors.start(); state.scheduling_after_source_identity = None; state.scheduling_exhausted = False
    state.government_subsidy_after_row_id = 0; state.government_subsidy_exhausted = False; state.government_subsidy_integrity_after_batch_id = 0; state.government_subsidy_integrity_exhausted = False
    state.government_subsidy_reversal_after_row_id = 0; state.government_subsidy_reversal_exhausted = False; state.government_subsidy_assignment_drift_after_claim_item_id = 0; state.government_subsidy_assignment_drift_exhausted = False; state.government_return_outbound_overage_after_row_id = 0; state.government_return_outbound_overage_exhausted = False
    state.process_reminder_exhausted = False
    state.beclass_review_after_row_id = 0; state.beclass_review_exhausted = False


def _consume_process_reminder_source(connection, state):
    if state.process_reminder_exhausted:
        return 0, 0
    result = consume_process_reminder_anomaly_sources(connection, as_of=current_business_instant().date())
    state.process_reminder_exhausted = True
    if result.succeeded:
        return result.projected_count, 0
    return 0, 1


def _consume_beclass_review_source(connection, state):
    if state.beclass_review_exhausted:
        return 0, 0
    try:
        result = project_beclass_import_review_page(
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


def _consume_staff_source(connection, state):
    result = consume_staff_payables_anomaly_sources(connection, as_of=current_business_instant().date(), maximum_items=_SOURCE_SCAN_PAGE_SIZE, cursors=state.staff_payables)
    if result.succeeded:
        state.staff_payables = result.cursors
        return result.projected_count, 0
    state.staff_payables = StaffPayablesAnomalyScanCursors(None, None, None, current_business_instant().date())
    return 0, 1


def _consume_scheduling_source(connection, state):
    if state.scheduling_exhausted: return 0, 0
    try:
        connection.begin(); result = _scheduling_consumer(connection).scan_page(SchedulingCoverageScanRequest(_SOURCE_SCAN_PAGE_SIZE, state.scheduling_after_source_identity)); connection.commit()
    except Exception:
        connection.rollback(); state.scheduling_exhausted = True; return 0, 1
    state.scheduling_after_source_identity = result.next_source_identity; state.scheduling_exhausted = result.next_source_identity is None
    return len(result.projections), 0


def _consume_government_subsidy_source(connection, state): return _consume_bounded_source(connection, state, GovernmentSubsidyAnomalyScanRequest(_SOURCE_SCAN_PAGE_SIZE, state.government_subsidy_after_row_id), project_government_subsidy_anomaly_page, "next_finance_import_row_id", "government_subsidy_after_row_id", "government_subsidy_exhausted")
def _consume_government_subsidy_integrity_source(connection, state): return _consume_bounded_source(connection, state, GovernmentSubsidyIntegrityScanRequest(_SOURCE_SCAN_PAGE_SIZE, state.government_subsidy_integrity_after_batch_id), project_government_subsidy_integrity_page, "next_batch_id", "government_subsidy_integrity_after_batch_id", "government_subsidy_integrity_exhausted")
def _consume_government_subsidy_reversal_source(connection, state): return _consume_bounded_source(connection, state, GovernmentSubsidyReversalScanRequest(_SOURCE_SCAN_PAGE_SIZE, state.government_subsidy_reversal_after_row_id), project_government_subsidy_reversal_anomaly_page, "next_finance_import_row_id", "government_subsidy_reversal_after_row_id", "government_subsidy_reversal_exhausted")
def _consume_government_subsidy_assignment_drift_source(connection, state): return _consume_bounded_source(connection, state, GovernmentSubsidyAssignmentDriftScanRequest(_SOURCE_SCAN_PAGE_SIZE, state.government_subsidy_assignment_drift_after_claim_item_id), project_government_subsidy_assignment_drift_page, "next_claim_item_id", "government_subsidy_assignment_drift_after_claim_item_id", "government_subsidy_assignment_drift_exhausted")
def _consume_government_return_outbound_overage_source(connection, state): return _consume_bounded_source(connection, state, GovernmentReturnOutboundOverageScanRequest(_SOURCE_SCAN_PAGE_SIZE, state.government_return_outbound_overage_after_row_id), project_government_return_outbound_overage_page, "next_finance_import_row_id", "government_return_outbound_overage_after_row_id", "government_return_outbound_overage_exhausted")


def _consume_bounded_source(connection, state, request, projector, next_cursor_field, state_cursor_field, exhausted_field):
    if getattr(state, exhausted_field): return 0, 0
    try: result = projector(connection, request)
    except Exception: setattr(state, exhausted_field, True); return 0, 1
    next_cursor = getattr(result, next_cursor_field); setattr(state, state_cursor_field, next_cursor or 0); setattr(state, exhausted_field, next_cursor is None)
    return len(result.projections), 0


def _scheduling_consumer(connection):
    return SchedulingCoverageAnomalyConsumer(MySqlSchedulingCoverageAnomalySource(connection), AnomalyApplication(default_anomaly_registry(), MySqlAnomalyRepository(connection), BorrowedAnomalyUnitOfWork))


async def architecture_outbox_worker_loop() -> None:
    state = ArchitectureSourceScanState.start()
    while True:
        try:
            result = await asyncio.to_thread(_consume_once, state)
            if result.delivered_count: continue
            _wakeup_event.clear()
            try: await asyncio.wait_for(_wakeup_event.wait(), timeout=_POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError: pass
        except asyncio.CancelledError: raise
        except Exception as error:
            print(f"[Architecture Outbox] worker error: {error}")
            await asyncio.sleep(5)


def start_architecture_outbox_worker() -> asyncio.Task[None]:
    global _worker_task
    _worker_task = asyncio.create_task(architecture_outbox_worker_loop(), name="architecture-outbox-worker")
    return _worker_task


async def stop_architecture_outbox_worker(task: asyncio.Task[None]) -> None:
    global _worker_task
    task.cancel()
    try: await task
    except asyncio.CancelledError: pass
    finally:
        if _worker_task is task: _worker_task = None


__all__ = ["ArchitectureSourceScanState", "start_architecture_outbox_worker", "stop_architecture_outbox_worker", "wake_architecture_outbox_worker"]
