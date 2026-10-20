"""Machine secrets are service-bound, never replaced, and require private TLS."""
import json

import pytest

from infrastructure.runtime.worker_credentials import SERVICES, prepare_credentials, read_verifiers
from infrastructure.http.private_operations_client import PrivateOperationError, PrivateOperationsClient
from fastapi import HTTPException
from starlette.requests import Request
from api.dependencies.internal_service_auth import require_internal_service, require_operation_service


def test_generated_credentials_are_distinct_and_server_has_only_verifiers(tmp_path):
    prepare_credentials(tmp_path)
    tokens = [(tmp_path / name / "token").read_text().strip() for name in SERVICES]
    registry_path = tmp_path / "api/verifiers.json"
    registry = registry_path.read_text()
    assert len(set(tokens)) == len(SERVICES)
    assert all(token not in registry for token in tokens)
    assert set(read_verifiers(registry_path)) == set(SERVICES)
    with pytest.raises(ValueError, match="refusing to overwrite"):
        prepare_credentials(tmp_path)
    assert tokens == [(tmp_path / name / "token").read_text().strip() for name in SERVICES]


def test_duplicate_verifier_cannot_bind_one_token_to_two_services(tmp_path):
    prepare_credentials(tmp_path)
    path = tmp_path / "api/verifiers.json"
    data = json.loads(path.read_text())
    data["services"][SERVICES[1]] = data["services"][SERVICES[0]]
    path.chmod(0o600)
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="invalid worker verifier"):
        read_verifiers(path)


@pytest.mark.parametrize("base_url,token_file", [("http://api", "missing"), ("https://api", "missing")])
def test_client_fails_before_transport_for_http_or_missing_secret(base_url, token_file, monkeypatch):
    monkeypatch.setattr("infrastructure.http.private_operations_client.requests.post",
                        lambda *args, **kwargs: pytest.fail("must fail before request"))
    client = PrivateOperationsClient("line-worker", base_url=base_url, auth_mode="nas_service_token",
                                     token_file=token_file, max_attempts=1)
    with pytest.raises(PrivateOperationError) as error:
        client.check()
    assert error.value.retryable is False


def _request(scheme="https"):
    return Request({"type": "http", "scheme": scheme, "server": ("line-api", 8443),
                    "path": "/internal/v1/runtime/check", "headers": [], "query_string": b""})


def test_photo_credential_is_confined_to_photo_routes(tmp_path, monkeypatch):
    prepare_credentials(tmp_path)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("INTERNAL_SERVICE_AUTH_MODE", "nas_service_token")
    monkeypatch.setenv("INTERNAL_SERVICE_CREDENTIALS_FILE", str(tmp_path / "api/verifiers.json"))
    token = (tmp_path / "line-media-proxy/token").read_text().strip()
    with pytest.raises(HTTPException) as blocked:
        require_internal_service(_request(), "Bearer " + token, None, "line-media-proxy")
    assert blocked.value.status_code == 403
    request = _request()
    request.scope["path"] = "/internal/v1/line-media/service-day-media"
    principal = require_internal_service(request, "Bearer " + token, None, "line-media-proxy")
    assert principal.service_name == "line-media-proxy"
    with pytest.raises(HTTPException) as wrong_operation:
        require_operation_service(principal, "line-worker")
    assert wrong_operation.value.status_code == 403


def test_server_binds_credential_and_rejects_cross_worker_and_operation(tmp_path, monkeypatch):
    prepare_credentials(tmp_path)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("INTERNAL_SERVICE_AUTH_MODE", "nas_service_token")
    monkeypatch.setenv("INTERNAL_SERVICE_CREDENTIALS_FILE", str(tmp_path / "api/verifiers.json"))
    token = (tmp_path / "line-worker/token").read_text().strip()
    principal = require_internal_service(_request(), "Bearer " + token, None, "line-worker")
    assert principal.service_name == "line-worker"
    require_operation_service(principal, "line-worker")
    with pytest.raises(HTTPException) as wrong_name:
        require_internal_service(_request(), "Bearer " + token, None, "incident-worker")
    assert wrong_name.value.status_code == 401
    with pytest.raises(HTTPException) as wrong_operation:
        require_operation_service(principal, "incident-worker")
    assert wrong_operation.value.status_code == 403
    with pytest.raises(HTTPException) as cleartext:
        require_internal_service(_request("http"), "Bearer " + token, None, "line-worker")
    assert cleartext.value.status_code == 426
    path = tmp_path / "api/verifiers.json"
    registry = json.loads(path.read_text())
    del registry["services"]["line-worker"]
    path.chmod(0o600)
    path.write_text(json.dumps(registry))
    with pytest.raises(HTTPException) as revoked:
        require_internal_service(_request(), "Bearer " + token, None, "line-worker")
    assert revoked.value.status_code == 401


@pytest.mark.parametrize("mode", ["local_shared_key", "google_oidc"])
def test_production_cannot_fall_back_to_local_key_or_old_google_mode(mode, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("INTERNAL_SERVICE_AUTH_MODE", mode)
    monkeypatch.setenv("INTERNAL_SERVICE_SHARED_KEY", "x" * 40)
    with pytest.raises(HTTPException) as error:
        require_internal_service(_request(), None, "x" * 40, "line-worker")
    assert error.value.status_code == 503
