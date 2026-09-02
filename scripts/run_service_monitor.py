"""Probe runtime services and submit typed observations to the private API."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.http.private_operations_client import (
    PrivateOperationError,
    PrivateOperationsClient,
    discard_database_credentials,
    runtime_identity,
)
from subsystems.line.runtime_monitoring import RuntimeHealthObservation, RuntimeHealthStatus


def main() -> int:
    discard_database_credentials()
    arguments = _arguments()
    instance_id = f"monitor:{socket.gethostname()}:{os.getpid()}"
    identity = runtime_identity("runtime-monitor", instance_id)
    client = PrivateOperationsClient("runtime-monitor")
    if getattr(arguments, "react_admin_health_check", False):
        try:
            attestation = client.react_admin_artifact_health()
        except PrivateOperationError as error:
            print(f"[MONITOR] {error}", flush=True)
            return 1 if error.retryable else 2
        print(json.dumps(asdict(attestation), ensure_ascii=False, sort_keys=True), flush=True)
        return 0
    while True:
        exit_code = _run_cycle(client, identity)
        if arguments.once or exit_code == 2:
            return exit_code
        time.sleep(max(5.0, arguments.interval_seconds))


def _run_cycle(client: PrivateOperationsClient, identity: dict[str, object]) -> int:
    observations = _external_observations()
    payload = {
        "runtime_identity": identity,
        "observations": [_serialize_observation(item) for item in observations],
    }
    try:
        client.record_monitor_cycle(payload)
    except PrivateOperationError as error:
        print(f"[MONITOR] {error}", flush=True)
        return 1 if error.retryable else 2
    return 0


def _external_observations() -> list[RuntimeHealthObservation]:
    observations = [
        _http_probe("api", "FastAPI", _api_health_url()),
        _http_probe("react", "React Admin", _ui_health_url()),
    ]
    public_url = os.getenv("LINE_PUBLIC_BASE_URL", "").strip().rstrip("/")
    observations.append(
        _http_probe("public_endpoint", "Public endpoint", f"{public_url}/health")
        if public_url
        else _unknown(
            "public_endpoint", "Public endpoint", "尚未設定 LINE_PUBLIC_BASE_URL"
        )
    )
    liff_url = os.getenv("LINE_LIFF_HEALTH_URL", "").strip()
    observations.append(
        _http_probe("liff", "LIFF", liff_url)
        if liff_url
        else _unknown("liff", "LIFF", "尚未設定 LINE_LIFF_HEALTH_URL")
    )
    return observations


def _http_probe(name: str, component: str, url: str) -> RuntimeHealthObservation:
    now = _now()
    started = time.perf_counter()
    try:
        response = requests.get(url, timeout=3)
        response.raise_for_status()
        return RuntimeHealthObservation(
            name,
            component,
            RuntimeHealthStatus.HEALTHY,
            f"{component} 可連線",
            {"url": _redacted_url(url), "status_code": response.status_code},
            now,
            int((time.perf_counter() - started) * 1000),
        )
    except requests.RequestException as error:
        return RuntimeHealthObservation(
            name,
            component,
            RuntimeHealthStatus.CRITICAL,
            f"{component} 無法連線",
            {"url": _redacted_url(url), "error": type(error).__name__},
            now,
            int((time.perf_counter() - started) * 1000),
        )


def _serialize_observation(
    observation: RuntimeHealthObservation,
) -> dict[str, object]:
    return {
        "service_name": observation.check_name,
        "component": observation.component,
        "status": observation.status.value,
        "message": observation.message,
        "details": observation.details,
        "observed_at": observation.checked_at.isoformat(),
        "latency_ms": observation.response_ms,
    }


def _unknown(name: str, component: str, message: str) -> RuntimeHealthObservation:
    return RuntimeHealthObservation(
        name,
        component,
        RuntimeHealthStatus.UNKNOWN,
        message,
        {},
        _now(),
    )


def _api_health_url() -> str:
    return os.getenv("API_HEALTH_URL", "http://127.0.0.1:8000/health").strip()


def _ui_health_url() -> str:
    return os.getenv("UI_HEALTH_URL", "http://127.0.0.1:5173/admin/").strip()


def _redacted_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--react-admin-health-check", action="store_true")
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=float(os.getenv("MONITOR_INTERVAL_SECONDS", "15")),
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
