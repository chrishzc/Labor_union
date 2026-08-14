"""Persist authenticated caller runtime identity from API-owned operations."""

from __future__ import annotations

from datetime import datetime, timezone

from api.schemas.private_operations import WorkerRuntimeIdentity
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.runtime_monitor_repository import MySqlRuntimeMonitorRepository


def record_runtime_heartbeat(identity: WorkerRuntimeIdentity, processed: int) -> None:
    connection = get_connection()
    try:
        connection.begin()
        write_runtime_heartbeat(connection, identity, processed)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def write_runtime_heartbeat(connection, identity: WorkerRuntimeIdentity, processed: int) -> None:
    MySqlRuntimeMonitorRepository(connection).record_heartbeat(
        identity.service_name,
        identity.instance_id,
        identity.process_id,
        identity.hostname,
        "running",
        _heartbeat_details(identity, processed),
        datetime.now(timezone.utc),
    )


def _heartbeat_details(identity: WorkerRuntimeIdentity, processed: int) -> dict[str, object]:
    return {
        "processed_last_cycle": processed,
        "release_version": identity.release_version,
        "caller_started_at": identity.started_at.isoformat(),
    }


__all__ = ["record_runtime_heartbeat", "write_runtime_heartbeat"]
