"""Own runtime-monitoring persistence transactions behind typed applications."""

from __future__ import annotations

import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Protocol

from subsystems.line.runtime_monitoring import RuntimeHealthObservation, RuntimeHealthStatus


class RuntimeIdentity(Protocol):
    service_name: str
    instance_id: str
    process_id: int
    hostname: str
    release_version: str
    started_at: datetime


class RuntimeMonitorObservation(Protocol):
    service_name: str
    component: str
    status: str
    message: str
    details: dict[str, object]
    observed_at: datetime
    latency_ms: int | None


class RuntimeHeartbeatRepository(Protocol):
    def record_heartbeat(
        self,
        service_name: str,
        instance_id: str,
        process_id: int,
        host_name: str,
        status: str,
        details: dict[str, object],
        now: datetime,
    ) -> None: ...


class RuntimeMonitorUnitOfWork(Protocol):
    runtime_monitor: RuntimeHeartbeatRepository

    def __enter__(self): ...

    def __exit__(self, exception_type, exception, traceback) -> bool: ...

    def commit(self) -> None: ...


class RuntimeLineRepository(Protocol):
    def latest_heartbeat(self): ...

    def queue_counts(self) -> dict[str, int]: ...


def _heartbeat_details(identity: RuntimeIdentity, processed: int) -> dict[str, object]:
    return {
        "processed_last_cycle": processed,
        "release_version": identity.release_version,
        "caller_started_at": identity.started_at.isoformat(),
    }


def _external_observations(
    observations: Iterable[RuntimeMonitorObservation],
) -> list[RuntimeHealthObservation]:
    return [
        RuntimeHealthObservation(
            item.service_name,
            item.component,
            RuntimeHealthStatus(item.status),
            item.message,
            item.details,
            item.observed_at,
            item.latency_ms,
        )
        for item in observations
    ]


def _database_observations(
    connection,
    runtime: RuntimeLineRepository,
    now: datetime,
) -> list[RuntimeHealthObservation]:
    observations = [_database_readiness_observation(connection, now)]
    observations.extend(_line_runtime_observations(runtime, now))
    observations.extend(_optional_worker_observations(connection, now))
    return observations


def _database_readiness_observation(connection, now: datetime) -> RuntimeHealthObservation:
    started = time.perf_counter()
    schema_count = _required_line_table_count(connection)
    expected_count = 5
    healthy = schema_count == expected_count
    return RuntimeHealthObservation(
        "database",
        "MySQL",
        RuntimeHealthStatus.HEALTHY if healthy else RuntimeHealthStatus.CRITICAL,
        "資料庫與 LINE runtime schema 正常" if healthy else "LINE runtime schema 尚未完整套用",
        {"required_tables": schema_count, "expected_tables": expected_count},
        now,
        int((time.perf_counter() - started) * 1000),
    )


def _redis_observation(now: datetime) -> RuntimeHealthObservation:
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return _unknown_observation("redis", "Redis", "REDIS_URL 未設定", now)
    try:
        import redis

        redis.Redis.from_url(url, socket_timeout=2).ping()
    except Exception as error:
        return RuntimeHealthObservation(
            "redis",
            "Redis",
            RuntimeHealthStatus.WARNING,
            "Redis 無法連線，Worker 將使用保底輪詢",
            {"error": type(error).__name__},
            now,
        )
    return RuntimeHealthObservation(
        "redis", "Redis", RuntimeHealthStatus.HEALTHY, "Redis 可連線", {}, now
    )


def _media_storage_observation(now: datetime) -> RuntimeHealthObservation:
    root = _media_storage_root()
    try:
        usage = shutil.disk_usage(root)
    except OSError as error:
        return RuntimeHealthObservation(
            "media_storage",
            "Media storage",
            RuntimeHealthStatus.CRITICAL,
            "媒體儲存無法存取",
            {"error": type(error).__name__},
            now,
        )
    free_ratio = usage.free / usage.total
    status = RuntimeHealthStatus.WARNING if free_ratio < 0.1 else RuntimeHealthStatus.HEALTHY
    return RuntimeHealthObservation(
        "media_storage",
        "Media storage",
        status,
        f"媒體儲存可用空間 {free_ratio:.1%}",
        {"path": str(root), "free_bytes": usage.free},
        now,
    )


def _media_storage_root() -> Path:
    configured = os.getenv("MEDIA_STORAGE_ROOT", ".local_media").strip() or ".local_media"
    path = Path(configured)
    return path if path.is_absolute() else Path(__file__).resolve().parents[2] / path


def _unknown_observation(
    check_name: str,
    component: str,
    message: str,
    now: datetime,
) -> RuntimeHealthObservation:
    return RuntimeHealthObservation(
        check_name,
        component,
        RuntimeHealthStatus.UNKNOWN,
        message,
        {},
        now,
    )


def _required_line_table_count(connection) -> int:
    required_tables = (
        "line_delivery_tasks",
        "runtime_health_status",
        "line_alert_notification_targets",
        "matching_notification_intents",
        "matching_response_events",
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 AS ready")
        cursor.fetchone()
        placeholders = ",".join(["%s"] * len(required_tables))
        cursor.execute(
            "SELECT COUNT(*) AS total FROM information_schema.tables "
            f"WHERE table_schema=DATABASE() AND table_name IN ({placeholders})",
            required_tables,
        )
        return int(cursor.fetchone()["total"])


def _line_runtime_observations(
    runtime: RuntimeLineRepository,
    now: datetime,
) -> list[RuntimeHealthObservation]:
    heartbeat = runtime.latest_heartbeat()
    worker_age = None if heartbeat is None else (now - heartbeat.heartbeat_at).total_seconds()
    worker_healthy = (
        heartbeat is not None
        and heartbeat.stopped_at is None
        and worker_age is not None
        and worker_age <= 60
    )
    counts = runtime.queue_counts()
    backlog = sum(counts.get(name, 0) for name in ("inbox_pending", "delivery_pending", "legacy_pending"))
    queue_warning = backlog >= int(os.getenv("MONITOR_QUEUE_WARNING", "100"))
    matching_failed = counts.get("matching_delivery_failed", 0)
    return [
        RuntimeHealthObservation(
            "line_worker",
            "LINE Worker",
            RuntimeHealthStatus.HEALTHY if worker_healthy else RuntimeHealthStatus.CRITICAL,
            "LINE Worker heartbeat 正常" if worker_healthy else "LINE Worker heartbeat 過期或不存在",
            {"age_seconds": worker_age},
            now,
        ),
        RuntimeHealthObservation(
            "line_queues",
            "LINE queues",
            RuntimeHealthStatus.WARNING if queue_warning else RuntimeHealthStatus.HEALTHY,
            f"待處理任務 {backlog} 筆",
            counts,
            now,
        ),
        RuntimeHealthObservation(
            "matching_delivery",
            "Matching LINE delivery",
            RuntimeHealthStatus.WARNING if matching_failed else RuntimeHealthStatus.HEALTHY,
            f"配對通知失敗 {matching_failed} 筆",
            {"active": counts.get("matching_delivery_active", 0), "failed": matching_failed},
            now,
        ),
    ]


def _optional_worker_observations(connection, now: datetime) -> list[RuntimeHealthObservation]:
    enabled = os.getenv("KNOWLEDGE_RETRIEVAL_RUNTIME_ENABLED", "false").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return [
            RuntimeHealthObservation(
                "knowledge-retrieval-worker",
                "Knowledge Retrieval Worker",
                RuntimeHealthStatus.UNKNOWN,
                "KNOWLEDGE_RETRIEVAL_RUNTIME_ENABLED 尚未啟用",
                {},
                now,
            )
        ]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT last_seen_at_utc,service_status FROM runtime_service_heartbeats "
            "WHERE service_name=%s ORDER BY last_seen_at_utc DESC LIMIT 1",
            ("knowledge-retrieval-worker",),
        )
        row = cursor.fetchone()
    age = None if row is None else (now - row["last_seen_at_utc"].replace(tzinfo=timezone.utc)).total_seconds()
    healthy = row is not None and row["service_status"] == "running" and age is not None and age <= 60
    return [
        RuntimeHealthObservation(
            "knowledge-retrieval-worker",
            "Knowledge Retrieval Worker",
            RuntimeHealthStatus.HEALTHY if healthy else RuntimeHealthStatus.CRITICAL,
            "Knowledge Retrieval Worker heartbeat 正常" if healthy else "Knowledge Retrieval Worker heartbeat 過期或不存在",
            {"age_seconds": age},
            now,
        )
    ]


def _record_observations(repository, delivery_tasks, observations) -> int:
    from subsystems.line.runtime_alert_application import RuntimeLineAlertProjector

    projector = RuntimeLineAlertProjector(lambda: datetime.now(timezone.utc))
    projected_count = 0
    for observation in observations:
        event_id = repository.record_observation(observation)
        if event_id is None:
            continue
        projector.project(event_id, repository, delivery_tasks)
        projected_count += 1
    return projected_count


__all__ = [
    "RuntimeIdentity",
    "RuntimeMonitorObservation",
    "_database_observations",
    "_database_readiness_observation",
    "_external_observations",
    "_heartbeat_details",
    "_media_storage_observation",
    "_record_observations",
    "_redis_observation",
]
