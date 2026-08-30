"""
File: test_private_runtime_operations.py
Description: 驗證 API-only runtime 的認證、傳輸與 Worker 無資料庫憑證契約。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import internal_service_auth
from api.dependencies import private_operations as private_operation_dependencies
from api.dependencies.line_worker_operation import _heartbeat_from_caller
from api.schemas.base import BaseResponse
from api.schemas.private_operations import WorkerRuntimeIdentity
from api.schemas.runtime_health import PrivateRuntimeCheckView
from api.routes import private_operations
from infrastructure.http.private_operations_client import (
    PrivateOperationError,
    PrivateOperationsClient,
    discard_database_credentials,
)
import infrastructure.http.private_operations_client as private_operations_client
from subsystems.line.runtime_contracts import LineRuntimeMode, LineWorkerHeartbeat
from subsystems.line.runtime_monitoring import RuntimeHealthObservation, RuntimeHealthStatus
from subsystems.line.runtime_alert_application import (
    RuntimeHeartbeatApplication,
    RuntimeMonitoringApplication,
)
import subsystems.line.runtime_monitoring_application as runtime_monitoring_application


LOCAL_KEY = "local-test-key-that-is-longer-than-thirty-two-characters"
LOCAL_HEADERS = {
    "X-Internal-Service-Key": LOCAL_KEY,
    "X-Internal-Service-Name": "durable-job-worker",
}


def _runtime_identity(service_name: str = "durable-job-worker") -> dict[str, object]:
    return {
        "service_name": service_name,
        "instance_id": f"{service_name}:instance-1",
        "process_id": 321,
        "hostname": "worker-host",
        "started_at": datetime(2026, 8, 14, tzinfo=timezone.utc).isoformat(),
        "release_version": "test-release",
    }


def _client() -> TestClient:
    application = FastAPI()
    application.include_router(private_operations.router)
    return TestClient(application)


def test_private_endpoint_rejects_missing_key(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("INTERNAL_SERVICE_SHARED_KEY", LOCAL_KEY)

    response = _client().post("/internal/v1/runtime/check", json={})

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "internal_service_authentication_failed"


def test_private_endpoint_accepts_local_service_key(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("INTERNAL_SERVICE_SHARED_KEY", LOCAL_KEY)

    response = _client().post(
        "/internal/v1/runtime/check",
        json={},
        headers={
            "X-Internal-Service-Key": LOCAL_KEY,
            "X-Internal-Service-Name": "test-worker",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"status": "ready", "service": "test-worker"}

    response_models = {
        route.path: route.response_model
        for route in private_operations.router.routes
        if getattr(route, "response_model", None) is not None
    }
    assert response_models["/internal/v1/runtime/check"] == BaseResponse[
        PrivateRuntimeCheckView
    ]


def test_production_rejects_local_shared_key(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("INTERNAL_SERVICE_SHARED_KEY", LOCAL_KEY)

    response = _client().post(
        "/internal/v1/runtime/check",
        json={},
        headers={"X-Internal-Service-Key": LOCAL_KEY},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "internal_service_authentication_unavailable"


def test_production_accepts_allowlisted_google_oidc_caller(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("INTERNAL_SERVICE_AUTH_MODE", "google_oidc")
    monkeypatch.setenv("INTERNAL_SERVICE_OIDC_AUDIENCE", "https://private-api.example")
    monkeypatch.setenv(
        "INTERNAL_SERVICE_OIDC_ALLOWED_CALLERS",
        "durable-job-worker=durable@example.iam.gserviceaccount.com",
    )
    monkeypatch.setattr(
        internal_service_auth.id_token,
        "verify_oauth2_token",
        lambda *_args, **_kwargs: {
            "iss": "https://accounts.google.com",
            "email": "durable@example.iam.gserviceaccount.com",
            "email_verified": True,
            "sub": "caller-subject",
        },
    )

    response = _client().post(
        "/internal/v1/runtime/check",
        json={},
        headers={
            "Authorization": "Bearer signed-id-token",
            "X-Internal-Service-Name": "durable-job-worker",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["service"] == "durable-job-worker"


def test_production_rejects_oidc_caller_not_bound_to_service_name(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("INTERNAL_SERVICE_AUTH_MODE", "google_oidc")
    monkeypatch.setenv("INTERNAL_SERVICE_OIDC_AUDIENCE", "https://private-api.example")
    monkeypatch.setenv(
        "INTERNAL_SERVICE_OIDC_ALLOWED_CALLERS",
        "line-worker=line@example.iam.gserviceaccount.com",
    )

    response = _client().post(
        "/internal/v1/runtime/check",
        json={},
        headers={
            "Authorization": "Bearer signed-id-token",
            "X-Internal-Service-Name": "durable-job-worker",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"]["retryable"] is False


def test_production_rejects_invalid_oidc_token(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("INTERNAL_SERVICE_AUTH_MODE", "google_oidc")
    monkeypatch.setenv("INTERNAL_SERVICE_OIDC_AUDIENCE", "https://private-api.example")
    monkeypatch.setenv(
        "INTERNAL_SERVICE_OIDC_ALLOWED_CALLERS",
        "durable-job-worker=durable@example.iam.gserviceaccount.com",
    )
    monkeypatch.setattr(
        internal_service_auth,
        "_verify_google_oidc_token",
        lambda token, audience: (_ for _ in ()).throw(ValueError("bad signature")),
    )

    response = _client().post(
        "/internal/v1/runtime/check",
        json={},
        headers={
            "Authorization": "Bearer invalid-token",
            "X-Internal-Service-Name": "durable-job-worker",
        },
    )

    assert response.status_code == 401
    assert "bad signature" not in response.text


def test_production_rejects_wrong_google_oidc_issuer(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("INTERNAL_SERVICE_AUTH_MODE", "google_oidc")
    monkeypatch.setenv("INTERNAL_SERVICE_OIDC_AUDIENCE", "https://private-api.example")
    monkeypatch.setenv(
        "INTERNAL_SERVICE_OIDC_ALLOWED_CALLERS",
        "durable-job-worker=durable@example.iam.gserviceaccount.com",
    )
    monkeypatch.setattr(
        internal_service_auth.id_token,
        "verify_oauth2_token",
        lambda *_args, **_kwargs: {
            "iss": "https://identity-provider.example",
            "email": "durable@example.iam.gserviceaccount.com",
            "email_verified": True,
        },
    )

    response = _client().post(
        "/internal/v1/runtime/check",
        json={},
        headers={
            "Authorization": "Bearer wrong-issuer-token",
            "X-Internal-Service-Name": "durable-job-worker",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "internal_service_authentication_failed"


def test_missing_environment_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("INTERNAL_SERVICE_SHARED_KEY", LOCAL_KEY)

    response = _client().post(
        "/internal/v1/runtime/check",
        json={},
        headers={"X-Internal-Service-Key": LOCAL_KEY},
    )

    assert response.status_code == 503


def test_durable_endpoint_delegates_one_complete_cycle(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("INTERNAL_SERVICE_SHARED_KEY", LOCAL_KEY)
    captured = {}

    def fake_cycle(worker_id, lease_seconds, retry_delay_seconds, runtime_identity, *, check_only):
        captured.update(
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            retry_delay_seconds=retry_delay_seconds,
            runtime_identity=runtime_identity,
            check_only=check_only,
        )
        return 1

    monkeypatch.setattr(private_operations, "run_durable_job_cycle", fake_cycle)
    response = _client().post(
        "/internal/v1/runtime/durable-jobs/run-once",
        json={
            "worker_id": "worker-1",
            "lease_seconds": 60,
            "retry_delay_seconds": 15,
            "runtime_identity": _runtime_identity(),
        },
        headers=LOCAL_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["data"]["processed"] == 1
    runtime = captured.pop("runtime_identity")
    assert captured == {
        "worker_id": "worker-1",
        "lease_seconds": 60,
        "retry_delay_seconds": 15,
        "check_only": False,
    }
    assert runtime.service_name == "durable-job-worker"
    assert runtime.process_id == 321
    assert runtime.hostname == "worker-host"


def test_durable_composition_delegates_heartbeat_to_typed_application_after_worker(monkeypatch) -> None:
    calls = []
    connection = SimpleNamespace(
        close=lambda: calls.append("close"),
    )

    class Repository:
        def __init__(self, active_connection):
            assert active_connection is connection

        def assert_durable_queue_schema(self):
            calls.append("schema")

    class Worker:
        def __init__(self, repository, transaction, _handlers, worker_id, lease_seconds, retry_delay):
            assert isinstance(repository, Repository)
            assert transaction is connection
            assert (worker_id, lease_seconds, retry_delay) == ("worker-1", 60, 15)

        def recover_and_run_once(self):
            calls.append("worker-terminal-committed")
            return True

    class HeartbeatApplication:
        def record(self, runtime_identity, processed):
            calls.append(
                (
                    "heartbeat-application",
                    runtime_identity.service_name,
                    runtime_identity.process_id,
                    processed,
                )
            )

    identity = WorkerRuntimeIdentity.model_validate(_runtime_identity())
    monkeypatch.setattr(private_operation_dependencies, "get_connection", lambda: connection)
    monkeypatch.setattr(private_operation_dependencies, "BackgroundJobRepository", Repository)
    monkeypatch.setattr(private_operation_dependencies, "DurableJobWorker", Worker)
    monkeypatch.setattr(private_operation_dependencies, "default_job_handlers", lambda: {})
    monkeypatch.setattr(
        private_operation_dependencies,
        "get_runtime_heartbeat_application",
        lambda: HeartbeatApplication(),
    )

    assert private_operation_dependencies.run_durable_job_cycle(
        "worker-1", 60, 15, identity, check_only=False
    ) == 1
    assert calls == [
        "schema",
        "worker-terminal-committed",
        ("heartbeat-application", "durable-job-worker", 321, 1),
        "close",
    ]


def test_runtime_heartbeat_application_commits_after_repository_write() -> None:
    calls = []
    identity = WorkerRuntimeIdentity.model_validate(_runtime_identity())

    class UnitOfWork:
        def __enter__(self):
            calls.append("uow-enter")
            return self

        def __exit__(self, exception_type, _exception, _traceback):
            calls.append("uow-exit")
            return False

        def commit(self):
            calls.append("uow-commit")

    class Repository:
        def record_heartbeat(self, *args):
            calls.append(
                (
                    "heartbeat-write",
                    args[0],
                    args[1],
                    args[2],
                    args[3],
                    args[4],
                    args[5],
                )
            )

    application = RuntimeHeartbeatApplication(
        lambda: UnitOfWork(),
        lambda _unit_of_work: Repository(),
    )

    application.record(identity, 1)

    assert calls[0] == "uow-enter"
    assert calls[1][:6] == (
        "heartbeat-write",
        "durable-job-worker",
        "durable-job-worker:instance-1",
        321,
        "worker-host",
        "running",
    )
    assert calls[1][6] == {
        "processed_last_cycle": 1,
        "release_version": "test-release",
        "caller_started_at": identity.started_at.isoformat(),
    }
    assert calls[2:] == ["uow-commit", "uow-exit"]


def test_runtime_heartbeat_application_rolls_back_on_repository_failure() -> None:
    calls = []

    class UnitOfWork:
        def __enter__(self):
            calls.append("uow-enter")
            return self

        def __exit__(self, exception_type, _exception, _traceback):
            if exception_type is not None:
                calls.append("uow-rollback")
            calls.append("uow-exit")
            return False

        def commit(self):
            calls.append("uow-commit")

    class Repository:
        def record_heartbeat(self, *_args):
            calls.append("heartbeat-write-failed")
            raise RuntimeError("heartbeat unavailable")

    application = RuntimeHeartbeatApplication(
        lambda: UnitOfWork(),
        lambda _unit_of_work: Repository(),
    )

    with pytest.raises(RuntimeError, match="heartbeat unavailable"):
        application.record(WorkerRuntimeIdentity.model_validate(_runtime_identity()), 1)

    assert calls == [
        "uow-enter",
        "heartbeat-write-failed",
        "uow-rollback",
        "uow-exit",
    ]


def test_endpoint_rejects_authenticated_service_for_another_operation(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("INTERNAL_SERVICE_SHARED_KEY", LOCAL_KEY)

    response = _client().post(
        "/internal/v1/runtime/durable-jobs/run-once",
        json={"worker_id": "worker-1", "runtime_identity": _runtime_identity("line-worker")},
        headers={
            "X-Internal-Service-Key": LOCAL_KEY,
            "X-Internal-Service-Name": "line-worker",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "internal_service_operation_forbidden"


def test_incident_endpoint_delegates_one_complete_cycle(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("INTERNAL_SERVICE_SHARED_KEY", LOCAL_KEY)
    monkeypatch.setattr(private_operations, "run_incident_maintenance_cycle", lambda identity: 3)

    response = _client().post(
        "/internal/v1/runtime/incident-maintenance/run-once",
        json={
            "worker_id": "incident-1",
            "runtime_identity": _runtime_identity("incident-worker"),
        },
        headers={
            "X-Internal-Service-Key": LOCAL_KEY,
            "X-Internal-Service-Name": "incident-worker",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "processed": 3,
        "operation": "incident_maintenance",
    }


def test_private_readiness_reports_critical_dependency_without_details(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("INTERNAL_SERVICE_SHARED_KEY", LOCAL_KEY)
    monkeypatch.setattr(
        private_operations,
        "inspect_runtime_readiness",
        lambda: (
            SimpleNamespace(
                check_name="database",
                status=SimpleNamespace(value="critical"),
                message="database unavailable",
            ),
        ),
    )

    response = _client().post(
        "/internal/v1/runtime/readiness",
        json={},
        headers=LOCAL_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "ready": False,
        "checks": [
            {
                "check_name": "database",
                "status": "critical",
                "message": "database unavailable",
            }
        ],
    }


def test_worker_and_monitor_entrypoints_do_not_import_mysql() -> None:
    project_root = Path(__file__).resolve().parents[1]
    entrypoints = (
        "scripts/run_durable_job_worker.py",
        "scripts/run_line_worker.py",
        "scripts/run_knowledge_worker.py",
        "scripts/run_incident_worker.py",
        "scripts/run_service_monitor.py",
    )
    for relative_path in entrypoints:
        source = (project_root / relative_path).read_text(encoding="utf-8")
        assert "infrastructure.mysql" not in source
        assert "get_connection" not in source


def test_private_client_never_places_key_in_url(monkeypatch) -> None:
    captured = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"data": {"status": "ready"}}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        return Response()

    monkeypatch.setattr("infrastructure.http.private_operations_client.requests.post", fake_post)
    client = PrivateOperationsClient(
        "test-worker",
        base_url="http://private-api",
        shared_key=LOCAL_KEY,
    )

    client.check()

    assert LOCAL_KEY not in captured["url"]
    assert captured["headers"]["X-Internal-Service-Key"] == LOCAL_KEY


def test_private_client_decodes_closed_react_admin_artifact_health(monkeypatch) -> None:
    digest = "a" * 64
    captured = {}

    def fake_get(url, **kwargs):
        captured.update(url=url, headers=kwargs["headers"])
        return _Response(200, {"data": {
            "active_selector": "current", "artifact_version": "react-admin-v1",
            "artifact_digest": digest, "manifest_digest": "b" * 64,
            "api_compatibility_revision": "api-v1", "root_marker_checked": True,
            "checked_asset_digest": "c" * 64, "healthy": True,
        }})

    monkeypatch.setattr("infrastructure.http.private_operations_client.requests.get", fake_get)
    client = PrivateOperationsClient("runtime-monitor", base_url="http://private-api", shared_key=LOCAL_KEY)

    attestation = client.react_admin_artifact_health()

    assert attestation.active_selector == "current"
    assert captured["url"].endswith("/internal/v1/runtime/react-admin/artifact-health")
    assert captured["headers"]["X-Internal-Service-Key"] == LOCAL_KEY


def test_private_client_loads_local_credential_without_overriding_process_values(
    monkeypatch, tmp_path
) -> None:
    environment_file = tmp_path / ".env"
    environment_file.write_text(
        "INTERNAL_SERVICE_SHARED_KEY=local-file-key-that-is-longer-than-thirty-two-characters\n"
        "DB_HOST=must-not-enter-worker.example\n"
        "DB_PASSWORD=must-not-enter-worker\n"
        "MYSQL_USER=must-not-enter-worker\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("INTERNAL_SERVICE_SHARED_KEY", raising=False)
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    monkeypatch.delenv("MYSQL_USER", raising=False)
    monkeypatch.setattr(private_operations_client, "LOCAL_ENVIRONMENT_PATH", environment_file)

    loaded_client = PrivateOperationsClient("incident-worker")

    assert loaded_client._shared_key == "local-file-key-that-is-longer-than-thirty-two-characters"
    assert "DB_HOST" not in os.environ
    assert "DB_PASSWORD" not in os.environ
    assert "MYSQL_USER" not in os.environ
    monkeypatch.setenv("INTERNAL_SERVICE_SHARED_KEY", LOCAL_KEY)
    configured_client = PrivateOperationsClient("incident-worker")

    assert configured_client._shared_key == LOCAL_KEY


def test_private_client_honors_typed_non_retryable_503(monkeypatch) -> None:
    calls = []

    class Response:
        status_code = 503

        @staticmethod
        def json():
            return {"detail": {"code": "auth_unavailable", "retryable": False}}

    monkeypatch.setattr(
        "infrastructure.http.private_operations_client.requests.post",
        lambda *args, **kwargs: calls.append(args) or Response(),
    )
    client = PrivateOperationsClient(
        "durable-job-worker",
        base_url="http://private-api",
        shared_key=LOCAL_KEY,
        max_attempts=3,
        sleep=lambda _: None,
    )

    with pytest.raises(PrivateOperationError) as raised:
        client.check()

    assert raised.value.retryable is False
    assert len(calls) == 1


def test_private_client_retries_transient_failure_within_budget(monkeypatch) -> None:
    responses = [_Response(503, {"detail": {"retryable": True}}), _Response(200, {"data": {}})]
    delays = []
    monkeypatch.setattr(
        "infrastructure.http.private_operations_client.requests.post",
        lambda *args, **kwargs: responses.pop(0),
    )
    client = PrivateOperationsClient(
        "durable-job-worker",
        base_url="http://private-api",
        shared_key=LOCAL_KEY,
        max_attempts=2,
        sleep=delays.append,
        random_fraction=lambda: 0.5,
    )

    client.check()

    assert delays == [0.25]


def test_private_client_uses_google_oidc_without_shared_key(monkeypatch) -> None:
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs["headers"])
        return _Response(200, {"data": {"status": "ready"}})

    monkeypatch.setattr(
        "infrastructure.http.private_operations_client.requests.post",
        fake_post,
    )
    client = PrivateOperationsClient(
        "durable-job-worker",
        base_url="https://private-api.example",
        shared_key="",
        auth_mode="google_oidc",
        oidc_audience="https://private-api.example",
        token_provider=lambda audience: "signed-token",
    )

    client.check()

    assert captured["Authorization"] == "Bearer signed-token"
    assert "X-Internal-Service-Key" not in captured


class _Response:
    def __init__(self, status_code: int, body: dict[str, object]) -> None:
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


def test_worker_process_discards_inherited_database_credentials(monkeypatch) -> None:
    monkeypatch.setenv("DB_HOST", "private-db.example")
    monkeypatch.setenv("DB_PASSWORD", "must-not-remain-in-worker")
    monkeypatch.setenv("MYSQL_USER", "database-user")

    discard_database_credentials()

    assert "DB_HOST" not in os.environ
    assert "DB_PASSWORD" not in os.environ
    assert "MYSQL_USER" not in os.environ


def test_monitor_does_not_probe_api_internal_redis_or_storage() -> None:
    project_root = Path(__file__).resolve().parents[1]
    monitor_source = (project_root / "scripts/run_service_monitor.py").read_text(encoding="utf-8")
    api_source = (project_root / "api/dependencies/private_operations.py").read_text(encoding="utf-8")
    application_source = (
        project_root / "subsystems/line/runtime_monitoring_application.py"
    ).read_text(encoding="utf-8")

    assert "REDIS_URL" not in monitor_source
    assert "MEDIA_STORAGE_ROOT" not in monitor_source
    assert "REDIS_URL" not in api_source
    assert "MEDIA_STORAGE_ROOT" not in api_source
    assert "REDIS_URL" in application_source
    assert "MEDIA_STORAGE_ROOT" in application_source


def test_runtime_monitoring_application_commits_heartbeat_and_observations_in_order(
    monkeypatch,
) -> None:
    calls = []
    identity = WorkerRuntimeIdentity.model_validate(_runtime_identity("runtime-monitor"))

    class RuntimeRepository:
        def record_heartbeat(self, *args):
            calls.append(("heartbeat", args[0], args[1], args[2], args[3], args[4]))

        def record_observation(self, observation):
            calls.append(("observation", observation.check_name))
            return None

    class UnitOfWork:
        runtime_monitor = RuntimeRepository()

        def __enter__(self):
            calls.append("uow-enter")
            return self

        def __exit__(self, exception_type, _exception, _traceback):
            calls.append("uow-exit")
            return False

        def commit(self):
            calls.append("uow-commit")

    def application_check(name):
        def build(now):
            calls.append(name)
            return RuntimeHealthObservation(
                name,
                name,
                RuntimeHealthStatus.UNKNOWN,
                name,
                {},
                now,
            )

        return build

    monkeypatch.setattr(
        runtime_monitoring_application,
        "_redis_observation",
        application_check("redis"),
    )
    monkeypatch.setattr(
        runtime_monitoring_application,
        "_media_storage_observation",
        application_check("media-storage"),
    )
    monkeypatch.setattr(
        runtime_monitoring_application,
        "_database_observations",
        lambda *_args: [],
    )
    application = RuntimeMonitoringApplication(
        lambda: UnitOfWork(),
        lambda _unit_of_work: calls.append("line-repository") or object(),
        lambda _unit_of_work: calls.append("delivery-repository") or object(),
        lambda _unit_of_work: calls.append("connection") or object(),
    )

    result = application.record_cycle(identity, ())

    assert result == (2, 0)
    assert calls == [
        "uow-enter",
        "connection",
        "redis",
        "media-storage",
        ("heartbeat", "runtime-monitor", "runtime-monitor:instance-1", 321, "worker-host", "running"),
        "line-repository",
        "delivery-repository",
        ("observation", "redis"),
        ("observation", "media-storage"),
        "uow-commit",
        "uow-exit",
    ]


def test_api_media_readiness_does_not_create_missing_storage(monkeypatch, tmp_path) -> None:
    missing_storage = tmp_path / "missing-media"
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(missing_storage))

    observation = runtime_monitoring_application._media_storage_observation(
        datetime.now(timezone.utc)
    )

    assert observation.status.value == "critical"
    assert not missing_storage.exists()


def test_line_heartbeat_uses_authenticated_caller_process_identity() -> None:
    observed_at = datetime(2026, 8, 14, tzinfo=timezone.utc)
    api_process_heartbeat = LineWorkerHeartbeat(
        "line-worker:instance-1",
        999,
        "api-host",
        LineRuntimeMode.CANONICAL,
        "{}",
        observed_at,
        last_cycle_at=observed_at,
    )
    caller = WorkerRuntimeIdentity.model_validate(_runtime_identity("line-worker"))

    heartbeat = _heartbeat_from_caller(api_process_heartbeat, caller)

    assert heartbeat.process_id == 321
    assert heartbeat.host_name == "worker-host"
    assert heartbeat.worker_identity == "line-worker:instance-1"


@pytest.mark.parametrize(
    "module_name,prefix",
    (
        ("scripts.run_durable_job_worker", "DURABLE WORKER"),
        ("scripts.run_line_worker", "LINE WORKER"),
        ("scripts.run_knowledge_worker", "KNOWLEDGE WORKER"),
        ("scripts.run_incident_worker", "INCIDENT WORKER"),
        ("scripts.run_service_monitor", "MONITOR"),
    ),
)
def test_worker_once_returns_failure_for_retryable_error(monkeypatch, module_name, prefix) -> None:
    module = __import__(module_name, fromlist=["main"])
    monkeypatch.setattr(module, "_arguments" if hasattr(module, "_arguments") else "_parse_arguments", lambda: _OnceArguments())
    monkeypatch.setattr(module, "PrivateOperationsClient", _RetryableFailureClient)

    assert module.main() == 1


class _OnceArguments:
    once = True
    check = False
    worker_id = "worker-1"
    poll_seconds = 0
    lease_seconds = 60
    retry_delay_seconds = 15


class _RetryableFailureClient:
    def __init__(self, service_name: str) -> None:
        self.service_name = service_name

    def run_durable_cycle(self, payload):
        raise PrivateOperationError("temporary", retryable=True)

    def run_line_cycle(self, payload):
        raise PrivateOperationError("temporary", retryable=True)

    def run_knowledge_cycle(self, payload):
        raise PrivateOperationError("temporary", retryable=True)

    def run_incident_maintenance_cycle(self, payload):
        raise PrivateOperationError("temporary", retryable=True)

    def record_monitor_cycle(self, payload):
        raise PrivateOperationError("temporary", retryable=True)
