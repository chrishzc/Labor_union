"""
File: test_m1_liff_identity_browser.py
Description: 受控 LIFF sandbox 的 M1 browser flow；驗證 typed identity 串接並禁止外部發送。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote, urlsplit

import pytest

playwright = pytest.importorskip("playwright.sync_api")


_PROVIDER_HOSTS = frozenset(
    {
        "access.line.me",
        "api.line.me",
        "liff.line.me",
        "profile.line-scdn.net",
        "static.line-scdn.net",
    }
)
_CANONICAL_API_PREFIX = "/api/v1/line/identity/"
_CANONICAL_RESPONSE_KEYS = {
    "/api/v1/line/identity/runtime-config": {"liff_id"},
    "/api/v1/line/identity/flow/open": {"flow_id", "purpose", "expires_at"},
    "/api/v1/line/identity/registration/preview": {
        "status",
        "expected_binding_version",
        "payload_fingerprint",
        "preview_fingerprint",
    },
    "/api/v1/line/identity/registration/apply": {
        "registration_id",
        "client_id",
        "beclass_record_id",
        "client_name",
        "replayed",
        "identity_status",
    },
}
_BINDING_READBACK_KEYS = {
    "line_user_id",
    "status",
    "version",
    "subject_type",
    "subject_reference",
    "subject_name",
    "updated_at",
    "revocation_request_id",
    "revocation_status",
    "revoked_at",
}
_FORBIDDEN_SEND_RE = re.compile(
    r"/(?:v2/bot/)?(?:message|richmenu|webhook)(?:/|$)|/(?:push|multicast|broadcast)(?:/|$)",
    re.IGNORECASE,
)
_SAFE_MARKER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$")
_SAFE_DATABASE_RE = re.compile(r"^lu_test_[A-Za-z0-9][A-Za-z0-9_-]{2,63}$")
_SAFE_SUBJECT_RE = re.compile(r"^sandbox(?:[-_:])[A-Za-z0-9_.:-]{3,127}$", re.IGNORECASE)


@dataclass(frozen=True)
class _SandboxConfig:
    base_url: str
    liff_url: str
    allowed_hosts: frozenset[str]
    database_identity: str
    database_marker: str
    controlled_subject: str
    controlled_line_user_id: str
    expected_subject_type: str
    expected_subject_reference: str
    registration_name: str
    registration_phone: str
    registration_address: str
    storage_state: Path | None
    interactive_token: str | None
    readback_bearer_token: str
    cleanup_url: str
    manual_cleanup_receipt: str


def test_m1_liff_registration_binding_readback_is_typed_and_message_free() -> None:
    config = _full_sandbox_config()

    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True, timeout=20_000)
        context_options = {"service_workers": "block"}
        if config.storage_state is not None:
            context_options["storage_state"] = str(config.storage_state)
        context = browser.new_context(**context_options)
        page = context.new_page()
        network = _install_network_guard(page, config, config.interactive_token)
        registration_id: int | None = None
        cleanup_error: BaseException | None = None
        try:
            response = page.goto(config.liff_url, wait_until="domcontentloaded", timeout=20_000)
            assert response is not None and response.ok
            _assert_navigation_host(page.url, config)

            _open_registration_from_identity(page)
            _fill_registration_form(page, config)
            with page.expect_response(
                lambda item: _url_path(item.url)
                == "/api/v1/line/identity/registration/preview"
            ) as registration_preview_response_info:
                page.locator("#registrationPreviewButton").click()
            registration_preview_response = registration_preview_response_info.value
            _assert_typed_response(
                registration_preview_response,
                _CANONICAL_RESPONSE_KEYS[
                    "/api/v1/line/identity/registration/preview"
                ],
            )
            assert page.locator("#registrationPreviewPanel").is_visible()
            with page.expect_response(
                lambda item: _url_path(item.url)
                == "/api/v1/line/identity/registration/apply"
            ) as registration_response_info:
                page.locator("#confirmRegistrationApply").click()
            registration_response = registration_response_info.value
            registration_data = _assert_typed_response(
                registration_response,
                _CANONICAL_RESPONSE_KEYS["/api/v1/line/identity/registration/apply"],
            )
            registration_id = registration_data["registration_id"]

            readback_response = page.request.get(
                f"{config.base_url}/api/v1/line/identity-bindings/"
                f"{quote(config.controlled_line_user_id, safe='')}",
                headers={"Authorization": f"Bearer {config.readback_bearer_token}"},
                timeout=20_000,
            )
            readback_data = _assert_typed_response(
                readback_response,
                _BINDING_READBACK_KEYS,
            )

            assert readback_data["line_user_id"] == config.controlled_line_user_id
            assert readback_data["subject_type"] == config.expected_subject_type
            assert readback_data["subject_reference"] == config.expected_subject_reference
            assert readback_data["status"] == "bound"
            assert registration_data["identity_status"] == readback_data["status"]
            assert registration_data["client_name"] == config.registration_name
            assert readback_data["subject_name"] == registration_data["client_name"]
            assert page.locator("#successCard").is_visible()
            assert page.locator(".success-title").inner_text() == "登記已受理"
            assert not page.locator("#registerForm").is_visible()

            _assert_required_network_responses(network)
            _assert_no_sensitive_response_values(network)
        finally:
            if registration_id is not None:
                try:
                    _cleanup_sandbox_record(page, config, registration_id)
                except BaseException:
                    cleanup_error = True
            context.close()
            browser.close()
        if cleanup_error is not None:
            pytest.fail(
                "M1 sandbox automatic cleanup failed; stop and perform the human cleanup "
                f"recorded at {config.manual_cleanup_receipt}."
            )


def test_m1_canonical_identity_page_is_reachable_without_message_side_effect() -> None:
    config = _partial_sandbox_config()

    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True, timeout=20_000)
        context = browser.new_context(service_workers="block")
        page = context.new_page()
        network = _install_network_guard(page, config, None)
        try:
            response = page.goto(f"{config.base_url}/line-identity", wait_until="domcontentloaded")
            assert response is not None and response.status == 200
            _assert_navigation_host(page.url, config)
            assert "/api/line/bind" not in page.content()
            assert "/api/v1/line/identity" in page.content()
            assert not network.forbidden_requests
        finally:
            context.close()
            browser.close()


def test_m1_legacy_bind_page_is_retired_in_canonical_sandbox() -> None:
    config = _partial_sandbox_config()

    with playwright.sync_playwright() as runtime:
        request = runtime.request.new_context()
        try:
            response = request.get(f"{config.base_url}/bind-page", timeout=20_000)
            assert response.status == 410
        finally:
            request.dispose()


def _full_sandbox_config() -> _SandboxConfig:
    config = _partial_sandbox_config()
    required = {
        "M1_LINE_SANDBOX_DB_IDENTITY": os.getenv("M1_LINE_SANDBOX_DB_IDENTITY", "").strip(),
        "M1_LINE_SANDBOX_DB_MARKER": os.getenv("M1_LINE_SANDBOX_DB_MARKER", "").strip(),
        "M1_LINE_SANDBOX_CONTROLLED_SUBJECT": os.getenv(
            "M1_LINE_SANDBOX_CONTROLLED_SUBJECT", ""
        ).strip(),
        "M1_LINE_SANDBOX_CONTROLLED_LINE_USER_ID": os.getenv(
            "M1_LINE_SANDBOX_CONTROLLED_LINE_USER_ID", ""
        ).strip(),
        "M1_LINE_SANDBOX_EXPECTED_SUBJECT_TYPE": os.getenv(
            "M1_LINE_SANDBOX_EXPECTED_SUBJECT_TYPE", ""
        ).strip(),
        "M1_LINE_SANDBOX_EXPECTED_SUBJECT_REFERENCE": os.getenv(
            "M1_LINE_SANDBOX_EXPECTED_SUBJECT_REFERENCE", ""
        ).strip(),
        "M1_LINE_SANDBOX_REGISTRATION_NAME": os.getenv(
            "M1_LINE_SANDBOX_REGISTRATION_NAME", ""
        ).strip(),
        "M1_LINE_SANDBOX_REGISTRATION_PHONE": os.getenv(
            "M1_LINE_SANDBOX_REGISTRATION_PHONE", ""
        ).strip(),
        "M1_LINE_SANDBOX_REGISTRATION_ADDRESS": os.getenv(
            "M1_LINE_SANDBOX_REGISTRATION_ADDRESS", ""
        ).strip(),
        "M1_LINE_SANDBOX_MANUAL_CLEANUP_RECEIPT": os.getenv(
            "M1_LINE_SANDBOX_MANUAL_CLEANUP_RECEIPT", ""
        ).strip(),
        "M1_LINE_SANDBOX_READBACK_BEARER_TOKEN": os.getenv(
            "M1_LINE_SANDBOX_READBACK_BEARER_TOKEN", ""
        ).strip(),
    }
    if any(not value for value in required.values()):
        pytest.skip("M1 sandbox full-flow configuration is not present")

    cleanup_url = os.getenv("M1_LINE_SANDBOX_CLEANUP_URL", "").strip()
    if not cleanup_url:
        pytest.fail(
            "M1 sandbox mutation is fail-closed: configure an allowlisted automatic "
            "cleanup URL and a human cleanup receipt path before running registration."
        )

    database_identity = required["M1_LINE_SANDBOX_DB_IDENTITY"]
    database_marker = required["M1_LINE_SANDBOX_DB_MARKER"]
    controlled_subject = required["M1_LINE_SANDBOX_CONTROLLED_SUBJECT"]
    if not _SAFE_DATABASE_RE.fullmatch(database_identity):
        raise AssertionError("M1_LINE_SANDBOX_DB_IDENTITY must name a lu_test_* database")
    if not _SAFE_MARKER_RE.fullmatch(database_marker):
        raise AssertionError("M1_LINE_SANDBOX_DB_MARKER is not a safe disposable marker")
    if not _SAFE_SUBJECT_RE.fullmatch(controlled_subject):
        raise AssertionError("M1_LINE_SANDBOX_CONTROLLED_SUBJECT must identify a sandbox subject")
    if required["M1_LINE_SANDBOX_EXPECTED_SUBJECT_TYPE"] != "customer":
        raise AssertionError("M1 registration readback subject type must equal customer")
    if len(required["M1_LINE_SANDBOX_CONTROLLED_LINE_USER_ID"]) < 8:
        raise AssertionError("M1 controlled LINE user identity is malformed")
    if len(required["M1_LINE_SANDBOX_READBACK_BEARER_TOKEN"]) < 16:
        raise AssertionError("M1 readback bearer session is malformed")

    storage_value = os.getenv("M1_LINE_SANDBOX_STORAGE_STATE", "").strip()
    token = os.getenv("M1_LINE_SANDBOX_INTERACTIVE_ID_TOKEN", "").strip()
    if bool(storage_value) == bool(token):
        raise AssertionError("configure exactly one controlled storage state or interactive token")
    storage_state = None
    if storage_value:
        storage_state = Path(storage_value).expanduser()
        if not storage_state.is_file() or storage_state.suffix.lower() != ".json":
            raise AssertionError("M1_LINE_SANDBOX_STORAGE_STATE must be an existing JSON file")
    elif len(token) < 16 or any(character.isspace() for character in token):
        raise AssertionError("M1_LINE_SANDBOX_INTERACTIVE_ID_TOKEN is malformed")

    cleanup_parts = urlsplit(cleanup_url)
    cleanup_host = (cleanup_parts.hostname or "").lower()
    if cleanup_parts.scheme not in {"https", "http"} or not cleanup_parts.netloc:
        raise AssertionError("M1_LINE_SANDBOX_CLEANUP_URL must be an absolute HTTP(S) URL")
    if cleanup_host not in config.allowed_hosts or _looks_production_like(cleanup_host):
        raise AssertionError("M1 sandbox cleanup URL host is not allowlisted")
    if _FORBIDDEN_SEND_RE.search(cleanup_parts.path):
        raise AssertionError("M1 sandbox cleanup URL matches a forbidden send endpoint")

    return _SandboxConfig(
        base_url=config.base_url,
        liff_url=config.liff_url,
        allowed_hosts=config.allowed_hosts,
        database_identity=database_identity,
        database_marker=database_marker,
        controlled_subject=controlled_subject,
        controlled_line_user_id=required["M1_LINE_SANDBOX_CONTROLLED_LINE_USER_ID"],
        expected_subject_type=required["M1_LINE_SANDBOX_EXPECTED_SUBJECT_TYPE"],
        expected_subject_reference=required[
            "M1_LINE_SANDBOX_EXPECTED_SUBJECT_REFERENCE"
        ],
        registration_name=required["M1_LINE_SANDBOX_REGISTRATION_NAME"],
        registration_phone=required["M1_LINE_SANDBOX_REGISTRATION_PHONE"],
        registration_address=required["M1_LINE_SANDBOX_REGISTRATION_ADDRESS"],
        storage_state=storage_state,
        interactive_token=token or None,
        readback_bearer_token=required["M1_LINE_SANDBOX_READBACK_BEARER_TOKEN"],
        cleanup_url=cleanup_url,
        manual_cleanup_receipt=required["M1_LINE_SANDBOX_MANUAL_CLEANUP_RECEIPT"],
    )


def _partial_sandbox_config() -> _SandboxConfig:
    base_url = os.getenv("M1_LINE_SANDBOX_BASE_URL", "").strip().rstrip("/")
    liff_url = os.getenv("M1_LINE_SANDBOX_LIFF_URL", "").strip()
    allowed_value = os.getenv("M1_LINE_SANDBOX_ALLOWED_HOSTS", "").strip()
    if not base_url or not liff_url or not allowed_value:
        pytest.skip("M1 LINE sandbox configuration is not present")
    if os.getenv("M1_LINE_MESSAGE_SENDING_DISABLED", "") != "true":
        raise AssertionError("M1_LINE_MESSAGE_SENDING_DISABLED must equal true")
    if os.getenv("M1_LINE_SANDBOX_ALLOW_MESSAGES", "").strip().lower() in {
        "1", "true", "yes", "on"
    }:
        raise AssertionError("M1 browser gate refuses any LINE message allowance")

    allowed_hosts = frozenset(
        item.strip().lower().rstrip(".") for item in allowed_value.split(",") if item.strip()
    )
    if not allowed_hosts:
        raise AssertionError("M1_LINE_SANDBOX_ALLOWED_HOSTS must not be empty")
    base_parts = _validate_sandbox_url(base_url, "M1_LINE_SANDBOX_BASE_URL")
    liff_parts = _validate_sandbox_url(liff_url, "M1_LINE_SANDBOX_LIFF_URL")
    if (base_parts.hostname or "").lower() not in allowed_hosts:
        raise AssertionError("M1 sandbox base host is not allowlisted")
    liff_host = (liff_parts.hostname or "").lower()
    if liff_host not in allowed_hosts and liff_host not in _PROVIDER_HOSTS:
        raise AssertionError("M1 LIFF URL host is not allowlisted")
    return _SandboxConfig(
        base_url=base_url,
        liff_url=liff_url,
        allowed_hosts=allowed_hosts,
        database_identity="",
        database_marker="",
        controlled_subject="",
        controlled_line_user_id="",
        expected_subject_type="",
        expected_subject_reference="",
        registration_name="",
        registration_phone="",
        registration_address="",
        storage_state=None,
        interactive_token=None,
        readback_bearer_token="",
        cleanup_url="",
        manual_cleanup_receipt="",
    )


def _validate_sandbox_url(value: str, variable: str):
    parts = urlsplit(value)
    if parts.scheme not in {"https", "http"} or not parts.netloc or parts.username:
        raise AssertionError(f"{variable} must be an absolute HTTP(S) URL without credentials")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host or _looks_production_like(host):
        raise AssertionError(f"{variable} points to a production-like host")
    if parts.scheme != "https" and host not in {"localhost", "127.0.0.1", "::1"}:
        raise AssertionError(f"{variable} must use HTTPS outside local loopback")
    return parts


def _looks_production_like(host: str) -> bool:
    lowered = host.lower().rstrip(".")
    return lowered in {"union.example.com", "api.example.com"} or any(
        part in {"prod", "production", "live"} for part in lowered.split(".")
    )


def _open_registration_from_identity(page) -> None:
    if "/line-identity" not in page.url:
        page.goto(f"{page.url.split('?', 1)[0].rstrip('/')}/line-identity", wait_until="domcontentloaded", timeout=20_000)
    register_button = page.locator("#register-new")
    if register_button.count() != 1:
        raise AssertionError("M1 identity page did not expose the canonical registration action")
    register_button.click()
    page.wait_for_url(re.compile(r"/line-registration(?:\?|$)"), timeout=20_000)
    assert page.locator("#registerForm").is_visible()


def _fill_registration_form(page, config: _SandboxConfig) -> None:
    page.locator("#name").fill(config.registration_name)
    page.locator("#phone").fill(config.registration_phone)
    page.locator("#address").fill(config.registration_address)
    page.locator("#expected_date").fill((date.today() + timedelta(days=30)).isoformat())
    page.locator("#service_days").fill("1")
    page.locator("#agree1").click()
    page.locator("#refundPolicyAccept").click()
    page.locator("#agree2").check()
    page.locator("#agree3").check()
    for control in page.locator(
        "#customFieldsContainer input, #customFieldsContainer textarea, #customFieldsContainer select"
    ).all():
        if not control.is_visible() or not control.is_enabled():
            continue
        if control.get_attribute("type") == "checkbox":
            control.check()
        elif control.get_attribute("type") == "radio":
            control.check()
        elif control.get_attribute("data-liff-field"):
            control.fill("M1 sandbox validation")


def _install_network_guard(page, config: _SandboxConfig, interactive_token: str | None):
    state = _NetworkState()

    def guard(route) -> None:
        request = route.request
        parts = urlsplit(request.url)
        host = (parts.hostname or "").lower().rstrip(".")
        path = parts.path or "/"
        if _FORBIDDEN_SEND_RE.search(path):
            state.forbidden_requests.append(path)
            route.abort()
            return
        if host not in config.allowed_hosts and host not in _PROVIDER_HOSTS:
            state.blocked_hosts.append(host or "<missing-host>")
            route.abort()
            return
        if interactive_token and request.method == "POST" and path.startswith(_CANONICAL_API_PREFIX):
            try:
                payload = request.post_data_json
                if isinstance(payload, dict) and not payload.get("line_id_token"):
                    payload["line_id_token"] = interactive_token
                    route.continue_(post_data=json.dumps(payload, ensure_ascii=False))
                    return
            except (TypeError, ValueError):
                pass
        route.continue_()

    def observe_request(request) -> None:
        path = _url_path(request.url)
        if path.startswith(_CANONICAL_API_PREFIX):
            state.request_paths.append(path)

    def observe_response(response) -> None:
        path = _url_path(response.url)
        if path not in _CANONICAL_RESPONSE_KEYS:
            return
        record: dict[str, object] = {
            "path": path,
            "status": response.status,
            "content_type": response.headers.get("content-type", ""),
        }
        try:
            body = response.json()
            record["body"] = body if isinstance(body, dict) else None
        except (TypeError, ValueError):
            record["body"] = None
        state.responses.append(record)

    page.route("**/*", guard)
    page.on("request", observe_request)
    page.on("response", observe_response)
    return state


class _NetworkState:
    def __init__(self) -> None:
        self.forbidden_requests: list[str] = []
        self.blocked_hosts: list[str] = []
        self.request_paths: list[str] = []
        self.responses: list[dict[str, object]] = []


def _assert_required_network_responses(state: _NetworkState) -> None:
    if state.forbidden_requests:
        raise AssertionError("forbidden LINE send endpoint was requested")
    if state.blocked_hosts:
        raise AssertionError("network request escaped the sandbox/provider allowlist")
    records = {str(item["path"]): item for item in state.responses}
    for required_path in (
        "/api/v1/line/identity/runtime-config",
        "/api/v1/line/identity/flow/open",
        "/api/v1/line/identity/registration/preview",
        "/api/v1/line/identity/registration/apply",
    ):
        if required_path not in records:
            raise AssertionError(f"missing canonical typed response: {required_path}")
        _assert_typed_record(records[required_path], _CANONICAL_RESPONSE_KEYS[required_path])


def _assert_typed_response(response, required_keys: set[str]) -> dict[str, object]:
    assert response.status == 200
    assert "application/json" in response.headers.get("content-type", "")
    body = response.json()
    data = _assert_closed_envelope(body, required_keys)
    assert "line_id_token" not in json.dumps(body, ensure_ascii=False)
    return data


def _assert_typed_record(record: dict[str, object], required_keys: set[str]) -> None:
    assert record["status"] == 200
    assert "application/json" in str(record["content_type"])
    body = record.get("body")
    _assert_closed_envelope(body, required_keys)


def _assert_closed_envelope(body: object, required_keys: set[str]) -> dict[str, object]:
    assert isinstance(body, dict)
    assert set(body) == {"success", "message", "data", "error"}
    assert body["success"] is True
    assert body["error"] is None
    data = body["data"]
    assert isinstance(data, dict)
    assert set(data) == required_keys
    return data


def _assert_no_sensitive_response_values(state: _NetworkState) -> None:
    for response in state.responses:
        body = response.get("body")
        if body is None:
            raise AssertionError("canonical response was not valid JSON")
        assert "line_id_token" not in json.dumps(body, ensure_ascii=False)


def _cleanup_sandbox_record(page, config: _SandboxConfig, registration_id: int) -> None:
    response = page.request.fetch(
        config.cleanup_url,
        method="POST",
        data={
            "database_identity": config.database_identity,
            "marker": config.database_marker,
            "controlled_subject": config.controlled_subject,
            "registration_id": registration_id,
        },
        timeout=20_000,
    )
    if response.status not in {200, 204}:
        raise AssertionError("M1 sandbox cleanup endpoint did not acknowledge cleanup")
    if response.status == 204:
        return
    body = response.json()
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict) or not body.get("success"):
        raise AssertionError("M1 sandbox cleanup acknowledgement was not typed")
    assert isinstance(data.get("cleanup_receipt_id"), str)
    assert data.get("database_identity") == config.database_identity
    assert data.get("marker") == config.database_marker


def _assert_navigation_host(value: str, config: _SandboxConfig) -> None:
    host = (urlsplit(value).hostname or "").lower().rstrip(".")
    if host not in config.allowed_hosts and host not in _PROVIDER_HOSTS:
        raise AssertionError("LIFF navigation escaped the configured sandbox/provider hosts")


def _url_path(value: str) -> str:
    return urlsplit(value).path or "/"
