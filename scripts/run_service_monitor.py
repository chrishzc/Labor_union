"""Actively probe runtime services and persist debounced health projections."""

from __future__ import annotations

import argparse
import json
import os
import socket
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from infrastructure.mysql.line_runtime_repository import MySqlLineRuntimeRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.runtime_monitor_repository import MySqlRuntimeMonitorRepository
from subsystems.line.runtime_alert_application import RuntimeLineAlertProjector
from subsystems.line.runtime_monitoring import RuntimeHealthObservation, RuntimeHealthStatus

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def main() -> int:
    args = _arguments()
    instance_id = f"monitor:{socket.gethostname()}:{os.getpid()}"
    while True:
        _run_cycle(instance_id)
        if args.once:
            return 0
        time.sleep(max(5.0, args.interval_seconds))


def _run_cycle(instance_id: str) -> None:
    observations = [_http_probe("api", "FastAPI", "http://127.0.0.1:8000/health")]
    observations.append(_http_probe("streamlit", "Streamlit", "http://127.0.0.1:8501/_stcore/health"))
    public_url = os.getenv("LINE_PUBLIC_BASE_URL", "").strip().rstrip("/")
    observations.append(_http_probe("public_endpoint", "Public endpoint", f"{public_url}/health") if public_url else _unknown("public_endpoint", "Public endpoint", "尚未設定 LINE_PUBLIC_BASE_URL"))
    liff_url = os.getenv("LINE_LIFF_HEALTH_URL", "").strip()
    observations.append(_http_probe("liff", "LIFF", liff_url) if liff_url else _unknown("liff", "LIFF", "尚未設定 LINE_LIFF_HEALTH_URL"))
    observations.append(_supervisor_probe())
    observations.append(_storage_probe())
    try:
        connection = get_connection()
        connection.begin()
        repository = MySqlRuntimeMonitorRepository(connection)
        runtime = MySqlLineRuntimeRepository(connection)
        now = _now()
        repository.record_heartbeat("runtime-monitor", instance_id, os.getpid(), socket.gethostname(), "running", {}, now)
        observations.extend(_database_observations(connection, runtime, now))
        projector = RuntimeLineAlertProjector(_now)
        for observation in observations:
            event_id = repository.record_observation(observation)
            if event_id:
                projector.project(event_id, repository, MySqlLineDeliveryTaskRepository(connection))
        connection.commit()
    except Exception as error:
        try:
            connection.rollback()
            connection.close()
        except Exception:
            pass
        print(f"[MONITOR] 無法寫入監控結果：{type(error).__name__}: {error}", flush=True)
    else:
        connection.close()


def _database_observations(connection, runtime, now):
    started = time.perf_counter()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 AS ready")
        cursor.fetchone()
        cursor.execute("SELECT COUNT(*) AS total FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('line_delivery_tasks','runtime_health_status','line_alert_notification_targets','matching_notification_intents','matching_response_events')")
        schema_count = int(cursor.fetchone()["total"])
    db_status = RuntimeHealthStatus.HEALTHY if schema_count == 5 else RuntimeHealthStatus.CRITICAL
    observations = [RuntimeHealthObservation("database", "MySQL", db_status, "資料庫與 Stage 7 schema 正常" if schema_count == 5 else "Stage 7 schema 尚未完整套用", {"required_tables": schema_count}, now, int((time.perf_counter()-started)*1000))]
    heartbeat = runtime.latest_heartbeat()
    worker_age = None if heartbeat is None else (now - heartbeat.heartbeat_at).total_seconds()
    worker_ok = heartbeat is not None and heartbeat.stopped_at is None and worker_age is not None and worker_age <= 60
    observations.append(RuntimeHealthObservation("line_worker", "LINE Worker", RuntimeHealthStatus.HEALTHY if worker_ok else RuntimeHealthStatus.CRITICAL, "LINE Worker heartbeat 正常" if worker_ok else "LINE Worker heartbeat 過期或不存在", {"age_seconds": worker_age}, now))
    counts = runtime.queue_counts()
    backlog = sum(counts.get(name, 0) for name in ("inbox_pending", "delivery_pending", "legacy_pending"))
    observations.append(RuntimeHealthObservation("line_queues", "LINE queues", RuntimeHealthStatus.WARNING if backlog >= int(os.getenv("MONITOR_QUEUE_WARNING", "100")) else RuntimeHealthStatus.HEALTHY, f"待處理任務 {backlog} 筆", counts, now))
    matching_failed = counts.get("matching_delivery_failed", 0)
    matching_status = RuntimeHealthStatus.WARNING if matching_failed else RuntimeHealthStatus.HEALTHY
    observations.append(RuntimeHealthObservation("matching_delivery", "Matching LINE delivery", matching_status, f"配對通知失敗 {matching_failed} 筆", {"active": counts.get("matching_delivery_active", 0), "failed": matching_failed}, now))
    observations.append(_redis_probe(now))
    return observations


def _http_probe(name, component, url):
    now = _now()
    started = time.perf_counter()
    try:
        response = requests.get(url, timeout=3)
        response.raise_for_status()
        return RuntimeHealthObservation(name, component, RuntimeHealthStatus.HEALTHY, f"{component} 可連線", {"url": url, "status_code": response.status_code}, now, int((time.perf_counter()-started)*1000))
    except requests.RequestException as error:
        return RuntimeHealthObservation(name, component, RuntimeHealthStatus.CRITICAL, f"{component} 無法連線", {"url": url, "error": type(error).__name__}, now, int((time.perf_counter()-started)*1000))


def _redis_probe(now):
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return _unknown("redis", "Redis", "REDIS_URL 未設定，Worker 使用低頻保底輪詢")
    try:
        import redis
        client = redis.Redis.from_url(url, socket_timeout=2)
        client.ping()
        return RuntimeHealthObservation("redis", "Redis", RuntimeHealthStatus.HEALTHY, "Redis 可連線", {}, now)
    except Exception as error:
        return RuntimeHealthObservation("redis", "Redis", RuntimeHealthStatus.WARNING, "Redis 無法連線，Worker 仍可由保底輪詢處理", {"error": type(error).__name__}, now)


def _supervisor_probe():
    path = PROJECT_ROOT / ".monitor_state" / "supervisor-heartbeat.json"
    now = _now()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        seen = datetime.fromisoformat(str(payload["written_at_utc"]))
        age = (now - seen).total_seconds()
        ok = age <= 30
        return RuntimeHealthObservation("supervisor", "Development supervisor", RuntimeHealthStatus.HEALTHY if ok else RuntimeHealthStatus.CRITICAL, "Supervisor heartbeat 正常" if ok else "Supervisor heartbeat 已過期", {"age_seconds": age}, now)
    except Exception:
        return _unknown("supervisor", "Development supervisor", "Supervisor heartbeat 尚未建立")


def _storage_probe():
    root = Path(os.getenv("MEDIA_STORAGE_ROOT", ".local_media"))
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    now = _now()
    try:
        root.mkdir(parents=True, exist_ok=True)
        usage = __import__("shutil").disk_usage(root)
        free_ratio = usage.free / usage.total
        status = RuntimeHealthStatus.WARNING if free_ratio < 0.1 else RuntimeHealthStatus.HEALTHY
        return RuntimeHealthObservation("media_storage", "Media storage", status, f"媒體儲存可用空間 {free_ratio:.1%}", {"path": str(root), "free_bytes": usage.free}, now)
    except OSError as error:
        return RuntimeHealthObservation("media_storage", "Media storage", RuntimeHealthStatus.CRITICAL, "媒體儲存無法存取", {"error": type(error).__name__}, now)


def _unknown(name, component, message):
    return RuntimeHealthObservation(name, component, RuntimeHealthStatus.UNKNOWN, message, {}, _now())


def _now():
    return datetime.now(timezone.utc)


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=float(os.getenv("MONITOR_INTERVAL_SECONDS", "15")))
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
