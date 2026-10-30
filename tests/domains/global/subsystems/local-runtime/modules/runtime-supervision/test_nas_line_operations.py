"""
File: test_nas_line_operations.py
Description: 驗證獨立 LINE 操作代理、內部私人 HTTPS 憑證授權與公開回應 Gzip 壓縮邊界。
"""
import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import ssl
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
import httpx
import pytest
import yaml

from infrastructure.runtime.worker_credentials import (
    LINE_OPERATIONS_SERVICE, SERVICES, ensure_line_operations_credentials,
    prepare_credentials, read_verifiers,
)


ROOT = Path(__file__).resolve().parents[7]


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    import dotenv
    from api.nas_apps import line_app
    from api.routes import nas_line_operations as routes
    from infrastructure.http import line_operations_client as transport

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)
    old = tmp_path / "workers"
    prepare_credentials(old)
    credential_root = tmp_path / "operations"
    ensure_line_operations_credentials(credential_root)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("INTERNAL_SERVICE_AUTH_MODE", "nas_service_token")
    monkeypatch.setenv("INTERNAL_SERVICE_CREDENTIALS_FILE", str(old / "api/verifiers.json"))
    monkeypatch.setenv("LINE_OPERATIONS_CREDENTIALS_FILE", str(credential_root / "api/verifiers.json"))

    private = FastAPI()
    private.include_router(routes.private_router)
    public = line_app()
    options = []
    context = ssl.create_default_context()
    monkeypatch.setattr(transport, "ssl", SimpleNamespace(create_default_context=lambda **kwargs: context))
    def private_client(**kwargs):
        options.append(kwargs)
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=private), **kwargs)
    monkeypatch.setattr(transport, "httpx", SimpleNamespace(
        AsyncClient=private_client, HTTPError=httpx.HTTPError, InvalidURL=httpx.InvalidURL))
    client = transport.LineOperationsClient("https://management-api:8443",
        str(credential_root / LINE_OPERATIONS_SERVICE / "token"), "private-ca.pem")
    public.dependency_overrides[routes.get_line_operations_client] = lambda: client

    async def request(method, path, *, private_request=False, **kwargs):
        app = private if private_request else public
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="https://line.test") as http:
            return await http.request(method, path, **kwargs)
    return SimpleNamespace(public=public, private=private, request=request, options=options,
                           credentials=credential_root, old=old, context=context, client=client)


def test_five_restored_pages_are_served_and_management_surfaces_stay_private(bridge):
    async def check():
        for path in ("/line-mobile-admin", "/line-candidate-contact", "/line-candidate-contact-customer",
                     "/line-deposit-payment", "/line-service-help"):
            response = await bridge.request("GET", path)
            assert response.status_code == 200, path
            assert "text/html" in response.headers["content-type"]
        for path in ("/admin/", "/setup", "/api/v1/admin/accounts",
                     "/internal/v1/line-operations/api/v1/line/mobile-admin/profile"):
            assert (await bridge.request("GET", path)).status_code == 404
    asyncio.run(check())


@pytest.fixture
def mobile_owner(bridge, monkeypatch):
    from api.routes import line_mobile_admin as mobile
    from api.dependencies.service_start import get_service_start_application
    from domains.line.identities import LineUserId

    state = SimpleNamespace(linked=True, role="system_admin", invalid=False)
    def verify(token):
        from infrastructure.line.liff_token_verifier import InvalidLiffTokenError
        if state.invalid:
            raise InvalidLiffTokenError("expired")
        assert token == "verified-line-token"
        return SimpleNamespace(line_user_id=LineUserId("U" + "a" * 32))
    monkeypatch.setattr(mobile, "get_liff_token_verifier", lambda: SimpleNamespace(verify=verify))
    @contextmanager
    def identity_unit():
        linked = (SimpleNamespace(admin_user_id=7, display_name="Synthetic operator", role=state.role)
                  if state.linked else None)
        yield SimpleNamespace(admins=SimpleNamespace(get_linked_admin=lambda identity: linked))
    monkeypatch.setattr(mobile, "open_line_unit_of_work", identity_unit)
    @dataclass
    class Receipt:
        request_id: int
        version: int
    owner = Mock()
    owner.invite.return_value = Receipt(41, 4)
    bridge.private.dependency_overrides[get_service_start_application] = lambda: owner
    return state, owner


def _invite(bridge, **updates):
    body = {"line_id_token": "verified-line-token", "expected_version": 3, "idempotency_key": "invite-once"}
    body.update(updates)
    return asyncio.run(bridge.request("POST", "/api/v1/line/mobile-admin/service-start/41/invite", json=body))


def test_verified_bound_admin_reaches_original_owner_with_version_and_idempotency(bridge, mobile_owner):
    _, owner = mobile_owner
    response = _invite(bridge)
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"request_id": 41, "version": 4}
    owner.invite.assert_called_once_with(41, 3, "admin:7", "invite-once")
    assert response.headers["cache-control"] == "private, no-store"
    assert bridge.options[0]["verify"] is bridge.context
    assert bridge.options[0]["trust_env"] is False
    assert bridge.options[0]["follow_redirects"] is False


@pytest.mark.parametrize("denial,status", [("invalid", 401), ("unbound", 403), ("capability", 403)])
def test_original_line_identity_binding_and_capability_checks_are_not_bypassed(bridge, mobile_owner, denial, status):
    state, owner = mobile_owner
    if denial == "invalid": state.invalid = True
    if denial == "unbound": state.linked = False
    if denial == "capability": state.role = "viewer"
    response = _invite(bridge)
    assert response.status_code == status, response.text
    owner.invite.assert_not_called()


def test_invalid_payload_cannot_replace_the_owner_actor_or_skip_version_validation(bridge, mobile_owner):
    _, owner = mobile_owner
    assert _invite(bridge, expected_version=0).status_code == 422
    assert _invite(bridge, actor="root").status_code == 422
    owner.invite.assert_not_called()


def test_owner_conflict_survives_the_private_and_public_transports(bridge, mobile_owner):
    _, owner = mobile_owner
    from domains.scheduling.service_start import ServiceStartConflict
    owner.invite.side_effect = ServiceStartConflict("service_start_stale", "資料已更新")
    response = _invite(bridge)
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "service_start_stale"
    owner.invite.assert_called_once()


def test_management_factory_mounts_the_private_bridge_once_and_keeps_its_gate(bridge, mobile_owner, monkeypatch):
    from api.dependencies.service_start import get_service_start_application
    from api.nas_apps import management_app
    _, owner = mobile_owner
    # Do not manufacture a production React artifact to inspect API composition.
    # Machine authentication below is still explicitly production/nas_service_token.
    monkeypatch.setenv("APP_ENV", "development")
    # Other tests may already have served the process-wide API. Verify this
    # composition on a fresh app so middleware is attached before its first use.
    monkeypatch.setattr("api.main.app", FastAPI())
    app = management_app()
    assert management_app() is app
    monkeypatch.setenv("APP_ENV", "production")
    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_service_start_application] = lambda: owner
    token = (bridge.credentials / LINE_OPERATIONS_SERVICE / "token").read_text().strip()
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://management-api") as client:
            path = "/internal/v1/line-operations/api/v1/line/mobile-admin/service-start/41/invite"
            assert (await client.post(path, json={})).status_code == 401
            response = await client.post(path, json={"line_id_token": "verified-line-token",
                "expected_version": 3, "idempotency_key": "invite-once"}, headers={
                "Authorization": "Bearer " + token, "X-Internal-Service-Name": LINE_OPERATIONS_SERVICE})
            assert response.status_code == 200, response.text
        owner.invite.assert_called_once_with(41, 3, "admin:7", "invite-once")
    try:
        asyncio.run(check())
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


def test_only_the_dedicated_machine_credential_can_reach_private_operations(bridge, mobile_owner):
    _, owner = mobile_owner
    path = "/internal/v1/line-operations/api/v1/line/mobile-admin/service-start/41/invite"
    old_token = (bridge.old / "line-worker/token").read_text().strip()
    async def check():
        missing = await bridge.request("POST", path, private_request=True, json={})
        assert missing.status_code == 401
        wrong_service = await bridge.request("POST", path, private_request=True, json={}, headers={
            "Authorization": "Bearer " + old_token, "X-Internal-Service-Name": "line-worker"})
        assert wrong_service.status_code == 403
        forged_identity = await bridge.request("POST", path, private_request=True, json={}, headers={
            "Authorization": "Bearer " + old_token, "X-Internal-Service-Name": LINE_OPERATIONS_SERVICE})
        assert forged_identity.status_code == 401
    asyncio.run(check())
    owner.invite.assert_not_called()


def test_machine_bridge_cannot_call_worker_cycles(bridge):
    from api.dependencies.internal_service_auth import require_internal_service
    from fastapi import HTTPException
    from starlette.requests import Request
    token = (bridge.credentials / LINE_OPERATIONS_SERVICE / "token").read_text().strip()
    request = Request({"type": "http", "scheme": "https", "method": "POST",
                       "path": "/internal/v1/runtime/line/run-once", "headers": [],
                       "server": ("management-api", 8443)})
    with pytest.raises(HTTPException) as denied:
        require_internal_service(request, "Bearer " + token, None, LINE_OPERATIONS_SERVICE)
    assert denied.value.status_code == 403


def test_public_gateway_has_no_wildcard_management_forwarding(bridge):
    async def check():
        for path in ("/api/v1/orders/CASE-1/status", "/api/v1/admin/users",
                     "/api/v1/line/mobile-admin/not-an-operation"):
            assert (await bridge.request("POST", path, json={})).status_code == 404
    asyncio.run(check())
    assert bridge.options == []


def test_bridge_credentials_are_additive_and_leave_existing_workers_rollback_compatible(tmp_path):
    old = tmp_path / "existing-workers"
    prepare_credentials(old)
    before = {path: path.read_bytes() for path in old.rglob("*") if path.is_file()}
    added = tmp_path / "new-operations"
    ensure_line_operations_credentials(added)
    token = (added / LINE_OPERATIONS_SERVICE / "token").read_bytes()
    ensure_line_operations_credentials(added)
    assert (added / LINE_OPERATIONS_SERVICE / "token").read_bytes() == token
    assert {path: path.read_bytes() for path in before} == before
    assert set(read_verifiers(old / "api/verifiers.json")) == set(SERVICES)
    assert set(read_verifiers(added / "api/verifiers.json", allowed_services=(LINE_OPERATIONS_SERVICE,))) == {LINE_OPERATIONS_SERVICE}
    assert token.strip().decode() not in (added / "api/verifiers.json").read_text()


def test_new_credential_can_resume_token_creation_without_rotating_it(tmp_path):
    folder = tmp_path / LINE_OPERATIONS_SERVICE
    folder.mkdir()
    token = "x" * 43
    (folder / "token").write_text(token + "\n")
    ensure_line_operations_credentials(tmp_path)
    assert (folder / "token").read_text() == token + "\n"
    before = (tmp_path / "api/verifiers.json").read_bytes()
    (folder / "token").write_text("y" * 43 + "\n")
    with pytest.raises(ValueError, match="mismatch"):
        ensure_line_operations_credentials(tmp_path)
    assert (tmp_path / "api/verifiers.json").read_bytes() == before


def test_restored_customer_payment_query_keeps_the_original_ownership_check(bridge, monkeypatch):
    from api.routes import line_deposit_payment as deposit
    from domains.line.identities import LineUserId
    from subsystems.line.deposit_notifications import DepositPaymentForbidden
    identity = LineUserId("U" + "b" * 32)
    monkeypatch.setattr(deposit, "get_liff_token_verifier", lambda: SimpleNamespace(
        verify=lambda token: SimpleNamespace(line_user_id=identity)))
    application = Mock(bank_code="fixture-bank")
    application.query_customer.return_value = SimpleNamespace(
        case_no="CASE-OWN", amount_ntd=1200, settled=False, due_date=None,
        virtual_account="fixture-va", received_on=None)
    monkeypatch.setattr(deposit, "get_deposit_notifications", lambda: application)
    async def query():
        own = await bridge.request("POST", "/api/v1/line/deposit-payment/query",
                                   json={"line_id_token": "customer-token", "case_no": "CASE-OWN"})
        assert own.status_code == 200
        assert own.json()["data"]["case_no"] == "CASE-OWN"
        application.query_customer.assert_called_once_with("CASE-OWN", identity)
        application.query_customer.side_effect = DepositPaymentForbidden("not-owned")
        other = await bridge.request("POST", "/api/v1/line/deposit-payment/query",
                                     json={"line_id_token": "customer-token", "case_no": "CASE-OTHER"})
        assert other.status_code == 403
    asyncio.run(query())


def test_transport_does_not_retry_or_forward_browser_credentials(bridge, monkeypatch):
    from infrastructure.http import line_operations_client as transport
    captured = []
    def unavailable(request):
        captured.append(request)
        raise httpx.ConnectError("unavailable", request=request)
    def client(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(unavailable), **kwargs)
    monkeypatch.setattr(transport, "httpx", SimpleNamespace(
        AsyncClient=client, HTTPError=httpx.HTTPError, InvalidURL=httpx.InvalidURL))
    response = asyncio.run(bridge.request("POST", "/api/v1/line/mobile-admin/profile",
        json={"line_id_token": "line-token"}, headers={
            "Authorization": "Bearer browser-value", "Cookie": "session=browser-value",
            "X-Internal-Service-Name": "line-worker", "X-Internal-Service-Key": "browser-value",
            "Idempotency-Key": "keep-original-command", "X-Correlation-ID": "test-correlation"}))
    assert response.status_code == 503
    assert len(captured) == 1
    request = captured[0]
    assert request.headers["X-Internal-Service-Name"] == LINE_OPERATIONS_SERVICE
    assert request.headers["Idempotency-Key"] == "keep-original-command"
    assert request.headers["X-Correlation-ID"] == "test-correlation"
    assert "cookie" not in request.headers and "x-internal-service-key" not in request.headers
    assert "browser-value" not in request.headers["authorization"]
    token = (bridge.credentials / LINE_OPERATIONS_SERVICE / "token").read_text().strip()
    assert request.headers["authorization"] == "Bearer " + token
    assert token not in response.text and "line-token" not in response.text


@pytest.mark.parametrize("base", ["http://management-api:8443", "https://management-api/subpath",
                                  "https://management-api?q=bad", "https://management-api#bad",
                                  "https://user:password@management-api"])
def test_transport_requires_a_private_https_origin_without_credential_or_path_injection(base):
    from infrastructure.http.line_operations_client import LineOperationsClient, LineOperationsUnavailable
    with pytest.raises(LineOperationsUnavailable):
        LineOperationsClient(base, "token", "ca.pem")


def test_path_normalization_cannot_escape_the_private_operation_prefix(bridge):
    from infrastructure.http.line_operations_client import LineOperationsUnavailable
    async def check():
        with pytest.raises(LineOperationsUnavailable):
            await bridge.client.request("POST", "/api/v1/line/mobile-admin/../../../../admin",
                                        content=b"{}", headers={}, params=[])
    asyncio.run(check())
    assert bridge.options == []


def _write_test_tls_bundle(folder: Path, sans: list) -> tuple[Path, Path, Path]:
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test Private API CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .add_extension(x509.KeyUsage(True, False, False, False, False, True, True, False, False), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    srv_key = ec.generate_private_key(ec.SECP256R1())
    srv_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "management-api")]))
        .issuer_name(ca_name)
        .public_key(srv_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(srv_key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    ca_file = folder / "ca.pem"
    cert_file = folder / "server-cert.pem"
    key_file = folder / "server-key.pem"
    ca_file.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    cert_file.write_bytes(srv_cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        srv_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return ca_file, cert_file, key_file


def test_real_private_tls_requires_the_correct_ca_hostname_and_machine_token(tmp_path, monkeypatch):
    import ipaddress
    import socket
    import threading
    import time
    from cryptography import x509
    from fastapi import Depends
    import uvicorn
    from api.routes.nas_line_operations import require_private_line_operations
    from infrastructure.http.line_operations_client import LineOperationsClient, LineOperationsUnavailable, PREFIX

    ca_file, cert_file, key_file = _write_test_tls_bundle(
        tmp_path / "tls", [x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]
    )
    other_ca_file, _, _ = _write_test_tls_bundle(
        tmp_path / "other-tls", [x509.DNSName("management-api")]
    )
    credential_root = tmp_path / "credentials"
    ensure_line_operations_credentials(credential_root)
    token_file = credential_root / LINE_OPERATIONS_SERVICE / "token"
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("INTERNAL_SERVICE_AUTH_MODE", "nas_service_token")
    monkeypatch.setenv("LINE_OPERATIONS_CREDENTIALS_FILE", str(credential_root / "api/verifiers.json"))
    app = FastAPI()
    @app.post(PREFIX + "/api/v1/line/test-query", dependencies=[Depends(require_private_line_operations)])
    def query():
        return {"data": "verified-private-transport"}
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.listen()
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False,
        ssl_certfile=str(cert_file),
        ssl_keyfile=str(key_file)))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        async def check():
            arguments = {"content": b"{}", "headers": {"content-type": "application/json"}, "params": []}
            good = LineOperationsClient(f"https://127.0.0.1:{port}", str(token_file), str(ca_file))
            response = await good.request("POST", "/api/v1/line/test-query", **arguments)
            assert response.status_code == 200
            assert response.json() == {"data": "verified-private-transport"}
            wrong_name = LineOperationsClient(f"https://localhost:{port}", str(token_file), str(ca_file))
            with pytest.raises(LineOperationsUnavailable):
                await wrong_name.request("POST", "/api/v1/line/test-query", **arguments)
            wrong_token = tmp_path / "wrong-token"
            wrong_token.write_text("z" * 43)
            rejected = LineOperationsClient(f"https://127.0.0.1:{port}", str(wrong_token), str(ca_file))
            assert (await rejected.request("POST", "/api/v1/line/test-query", **arguments)).status_code == 401
            wrong_ca = LineOperationsClient(f"https://127.0.0.1:{port}", str(token_file), str(other_ca_file))
            with pytest.raises(LineOperationsUnavailable):
                await wrong_ca.request("POST", "/api/v1/line/test-query", **arguments)
        asyncio.run(check())
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()


def test_public_line_app_gzip_compresses_large_liff_html_responses(bridge):
    async def check():
        response = await bridge.request(
            "GET",
            "/line-mobile-admin",
            headers={"Accept-Encoding": "gzip"},
        )
        assert response.status_code == 200
        assert response.headers.get("content-encoding") == "gzip"
        assert "Accept-Encoding" in response.headers.get("vary", "")
        assert len(response.text.encode("utf-8")) >= 1024
        assert "<html" in response.text.lower()

    asyncio.run(check())
