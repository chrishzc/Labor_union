"""API-side composition for runtime operations that are allowed to reach MySQL."""

from __future__ import annotations

import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from api.dependencies.runtime_heartbeat import (
    record_runtime_heartbeat,
    write_runtime_heartbeat,
)
from api.schemas.private_operations import MonitorCycleRequest, WorkerRuntimeIdentity
from infrastructure.knowledge.chroma_gateway import ChromaKnowledgeGateway
from infrastructure.mysql.background_job_repository import BackgroundJobRepository
from infrastructure.mysql.knowledge_retrieval_unit_of_work import (
    open_knowledge_retrieval_unit_of_work,
)
from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from infrastructure.mysql.line_runtime_repository import MySqlLineRuntimeRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.runtime_monitor_repository import MySqlRuntimeMonitorRepository
from subsystems.jobs.durable_job_worker import DurableJobWorker, default_job_handlers
from subsystems.knowledge_retrieval.application import KnowledgeWorker
from subsystems.line.runtime_alert_application import RuntimeLineAlertProjector
from subsystems.line.runtime_monitoring import RuntimeHealthObservation, RuntimeHealthStatus


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_durable_job_cycle(
    worker_id: str,
    lease_seconds: int,
    retry_delay_seconds: int,
    runtime_identity: WorkerRuntimeIdentity,
    *,
    check_only: bool,
) -> int:
    connection = get_connection()
    try:
        repository = BackgroundJobRepository(connection)
        repository.assert_durable_queue_schema()
        if check_only:
            write_runtime_heartbeat(connection, runtime_identity, 0)
            connection.commit()
            return 0
        worker = DurableJobWorker(
            repository,
            default_job_handlers(),
            worker_id,
            lease_seconds,
            retry_delay_seconds,
        )
        processed = int(worker.recover_and_run_once())
        write_runtime_heartbeat(connection, runtime_identity, processed)
        connection.commit()
        return processed
    finally:
        connection.close()


def run_knowledge_cycle(worker_id: str, runtime_identity: WorkerRuntimeIdentity) -> int:
    gateway = ChromaKnowledgeGateway(os.getenv("KNOWLEDGE_CHROMA_PATH", "db/chroma_knowledge"))
    worker = KnowledgeWorker(open_knowledge_retrieval_unit_of_work, gateway, worker_id)
    processed = int(worker.run_once())
    record_runtime_heartbeat(runtime_identity, processed)
    return processed


# Keep the outer transaction visible here so monitor persistence has one auditable commit owner.
def record_monitor_cycle(request: MonitorCycleRequest) -> tuple[int, int]:
    connection = get_connection()
    try:
        now = datetime.now(timezone.utc)
        application_checks = (_redis_observation(now), _media_storage_observation(now))
        connection.begin()
        write_runtime_heartbeat(connection, request.runtime_identity, 0)
        repository = MySqlRuntimeMonitorRepository(connection)
        observations = [
            *_external_observations(request),
            *_database_observations(connection, now),
            *application_checks,
        ]
        projected_count = _record_observations(connection, repository, observations)
        connection.commit()
        return len(observations), projected_count
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def inspect_runtime_readiness() -> tuple[RuntimeHealthObservation, ...]:
    connection = get_connection()
    try:
        now = datetime.now(timezone.utc)
        checks = (
            _database_readiness_observation(connection, now),
            _redis_observation(now),
            _media_storage_observation(now),
        )
        return checks
    finally:
        connection.close()


def _external_observations(request: MonitorCycleRequest) -> list[RuntimeHealthObservation]:
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
        for item in request.observations
    ]


def _database_observations(connection, now: datetime) -> list[RuntimeHealthObservation]:
    observations = [_database_readiness_observation(connection, now)]
    runtime = MySqlLineRuntimeRepository(connection)
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
        return _unavailable_media_storage(now, error)
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


def _unavailable_media_storage(
    now: datetime,
    error: OSError,
) -> RuntimeHealthObservation:
    return RuntimeHealthObservation(
        "media_storage",
        "Media storage",
        RuntimeHealthStatus.CRITICAL,
        "媒體儲存無法存取",
        {"error": type(error).__name__},
        now,
    )


def _media_storage_root() -> Path:
    configured = os.getenv("MEDIA_STORAGE_ROOT", ".local_media").strip() or ".local_media"
    path = Path(configured)
    return path if path.is_absolute() else PROJECT_ROOT / path


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
    runtime: MySqlLineRuntimeRepository,
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


def _record_observations(connection, repository, observations) -> int:
    projector = RuntimeLineAlertProjector(lambda: datetime.now(timezone.utc))
    delivery_tasks = MySqlLineDeliveryTaskRepository(connection)
    projected_count = 0
    for observation in observations:
        event_id = repository.record_observation(observation)
        if event_id is None:
            continue
        projector.project(event_id, repository, delivery_tasks)
        projected_count += 1
    return projected_count
