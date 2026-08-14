"""API-side composition of anomaly delivery and security retention cycles."""

from __future__ import annotations

import threading
import time

from api.dependencies.runtime_heartbeat import record_runtime_heartbeat
from api.schemas.private_operations import WorkerRuntimeIdentity
from subsystems.access.security_audit_retention_worker import (
    archive_due_security_audits_once,
)
from subsystems.anomalies.outbox_worker import (
    ArchitectureSourceScanState,
    consume_architecture_outbox_once,
)


AUDIT_RETENTION_INTERVAL_SECONDS = 24 * 60 * 60
_operation_lock = threading.Lock()
_source_scan_state = ArchitectureSourceScanState.start()
_next_audit_retention_at = 0.0


def run_incident_maintenance_cycle(identity: WorkerRuntimeIdentity) -> int:
    """Serialize one local cycle so a single API process cannot overlap DB writers."""
    with _operation_lock:
        delivery = consume_architecture_outbox_once(_source_scan_state)
        archived_count = _archive_audits_if_due()
    processed = delivery.delivered_count + archived_count
    record_runtime_heartbeat(identity, processed)
    return processed


def _archive_audits_if_due() -> int:
    global _next_audit_retention_at
    now = time.monotonic()
    if now < _next_audit_retention_at:
        return 0
    archived_count = archive_due_security_audits_once()
    _next_audit_retention_at = now + AUDIT_RETENTION_INTERVAL_SECONDS
    return archived_count
