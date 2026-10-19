"""One-time NAS root setup: same-origin HTTPS, shared password policy and closure."""
import asyncio

import httpx
import pytest
from fastapi import FastAPI

from api.routes import nas_setup
from api.exception_handlers import install_typed_error_handlers

ORIGIN = "https://nas.example.test:18443"
PASSWORD = "test-root1"  # Synthetic ten-character password; never a deployment credential.


@pytest.fixture
def setup_app(monkeypatch):
    state = {"root": False, "writes": 0}
    monkeypatch.delenv("NAS_SETUP_KEY", raising=False)
    monkeypatch.delenv("NAS_PUBLIC_ORIGIN", raising=False)
    monkeypatch.setattr(nas_setup, "get_access_control_connection_factory", lambda: object())
    monkeypatch.setattr(nas_setup, "has_root_admin", lambda **_: state["root"])
    def bootstrap(**kwargs):
        assert kwargs["password"] == PASSWORD
        if state["root"]:
            raise ValueError("root exists")
        state["root"] = True
        state["writes"] += 1
    monkeypatch.setattr(nas_setup, "bootstrap_root_admin", bootstrap)
    app = FastAPI()
    install_typed_error_handlers(app)
    app.include_router(nas_setup.router)
    return app, state


def request(app, method="POST", *, base=ORIGIN, headers=None, content=None, payload=None):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=base) as client:
            return await client.request(method, "/api/v1/admin/setup", headers=headers,
                                        content=content, json=payload)
    return asyncio.run(run())


def headers():
    return {"Origin": ORIGIN}


def payload():
    return {"username": "test-root", "display_name": "Test administrator", "password": PASSWORD}


def test_first_root_created_once_without_session_or_secret_projection(setup_app):
    app, state = setup_app
    response = request(app, headers=headers(), payload=payload())
    assert response.status_code == 201
    assert response.json() == {"created": True, "next": "/admin/"}
    assert response.headers["cache-control"] == "no-store"
    assert len(PASSWORD) == 10 and PASSWORD not in response.text
    assert request(app, headers=headers(), payload=payload()).status_code == 410
    assert state["writes"] == 1
    assert request(app, "GET").json() == {"required": False}


@pytest.mark.parametrize("case,status", [("http", 426), ("origin", 403), ("missing_origin", 403),
                                        ("password", 422), ("extra", 422), ("oversize", 413)])
def test_unowned_or_invalid_setup_cannot_write_and_does_not_echo_secrets(setup_app, case, status):
    app, state = setup_app
    values = payload()
    options = {"headers": headers(), "payload": values}
    if case == "http": options["base"] = ORIGIN.replace("https:", "http:")
    if case == "origin": options["headers"]["Origin"] = "https://untrusted.example.test"
    if case == "missing_origin": options["headers"].pop("Origin")
    if case == "password": values["password"] = "tiny-test"
    if case == "extra": values["unexpected"] = "sensitive-input"
    if case == "oversize":
        options.pop("payload")
        options["content"] = b"x" * 8193
        options["headers"]["Content-Type"] = "application/json"
    response = request(app, **options)
    assert response.status_code == status
    assert PASSWORD not in response.text and "tiny-test" not in response.text
    assert "sensitive-input" not in response.text
    assert state["writes"] == 0


def test_bootstrap_race_is_typed_conflict_without_retry(setup_app, monkeypatch):
    import pymysql
    app, state = setup_app
    calls = []
    def race(**_):
        calls.append(True)
        raise pymysql.err.OperationalError(1213, "synthetic deadlock")
    monkeypatch.setattr(nas_setup, "bootstrap_root_admin", race)
    response = request(app, headers=headers(), payload=payload())
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "setup_conflict"
    assert len(calls) == 1 and state["writes"] == 0


@pytest.mark.parametrize("base,origin", [
    ("https://192.168.10.20:19443", "https://192.168.10.20:19443"),
    ("https://another-nas.example.test", "https://another-nas.example.test:443"),
])
def test_current_https_address_needs_no_installation_key_or_fixed_url(setup_app, base, origin):
    app, state = setup_app
    response = request(app, base=base, headers={"Origin": origin}, payload=payload())
    assert response.status_code == 201 and state["writes"] == 1
