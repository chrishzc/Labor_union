"""Compose the typed runtime heartbeat application for API callers."""

from __future__ import annotations

from api.schemas.private_operations import WorkerRuntimeIdentity
from functools import lru_cache
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work

from subsystems.line.runtime_alert_application import RuntimeHeartbeatApplication


@lru_cache(maxsize=1)
def get_runtime_heartbeat_application() -> RuntimeHeartbeatApplication:
    return RuntimeHeartbeatApplication(
        open_line_unit_of_work,
        lambda unit_of_work: unit_of_work.runtime_monitor,
    )


def record_runtime_heartbeat(identity: WorkerRuntimeIdentity, processed: int) -> None:
    get_runtime_heartbeat_application().record(identity, processed)


__all__ = ["get_runtime_heartbeat_application", "record_runtime_heartbeat"]
