"""Runtime acceptance test for Data Browser page rendering and metadata request."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _data_browser_test_app():
    """以檔案層級函式供 AppTest 取得可檢查的原始碼。"""
    import builtins
    import importlib
    import os as _os
    import pathlib
    import sys as _sys
    from unittest import mock

    _sys.path.insert(0, str(pathlib.Path(_os.getcwd()).resolve()))
    page = importlib.import_module("ui.pages.01_data_browser")

    class _FakeResponse:
        def __init__(self, data: dict):
            self._data = {"data": data}

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    def _fake_get(url, headers=None, timeout=10, **_kwargs):
        builtins._DATA_BROWSER_TEST_CALLS.append((url, headers or {}))
        if url.endswith("/api/v1/admin/data-browser/staff"):
            return _FakeResponse({"rows": [{"staff_id": "S-1", "name": "測試月嫂"}], "columns": ["staff_id", "name"], "primary_key": "staff_id", "editable_columns": ["name"], "read_only": False, "valid_options": {}})
        if url.endswith("/api/v1/admin/data-browser/case_staff_assignments"):
            return _FakeResponse({"rows": [], "columns": ["id", "case_no"], "primary_key": "id", "editable_columns": [], "read_only": True, "valid_options": {}})
        if "/api/v1/admin/data-browser/" in url:
            table = url.rsplit("/", 1)[-1]
            return _FakeResponse({"rows": [], "columns": [f"{table}_id", "name"], "primary_key": f"{table}_id", "editable_columns": [], "read_only": False, "valid_options": {}})
        if url.endswith("/api/v1/holidays"):
            return _FakeResponse({"rows": []})
        raise AssertionError(f"Unexpected GET call: {url}")

    with mock.patch.object(page.requests, "get", _fake_get):
        page.show()


def test_shared_admin_context_loads_project_dotenv():
    from pathlib import Path

    source = Path("ui/pages/shared.py").read_text(encoding="utf-8")

    assert 'load_dotenv(PROJECT_ROOT / ".env")' in source


def test_fastapi_loads_project_dotenv_before_importing_routes() -> None:
    from pathlib import Path

    source = Path("api/main.py").read_text(encoding="utf-8")

    assert source.index('load_dotenv(PROJECT_ROOT / ".env")') < source.index(
        "from api.routes import ("
    )


def _run_data_browser_page(
    requests_calls: list[tuple[str, dict]],
    *,
    token: str | None,
) -> AppTest:
    app = AppTest.from_function(_data_browser_test_app)
    if token is not None:
        app.session_state["line_admin_access_token"] = token
    app.run(timeout=10)
    return app


def test_data_browser_show_calls_admin_metadata_with_auth_header(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "true")
    monkeypatch.setenv("API_BASE_URL", "http://localhost:8000")

    requests_calls: list[tuple[str, dict]] = []
    import builtins
    monkeypatch.setattr(builtins, "_DATA_BROWSER_TEST_CALLS", requests_calls, raising=False)
    app = _run_data_browser_page(requests_calls, token="session-token")

    import builtins
    observed_calls = builtins._DATA_BROWSER_TEST_CALLS

    assert not app.exception
    assert any(
        "/api/v1/admin/data-browser/" in url
        and headers.get("Authorization") == "Bearer session-token"
        and "X-Auth-Context" not in headers
        for url, headers in observed_calls
    )


def test_data_browser_show_fails_fast_when_admin_session_missing(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "true")
    monkeypatch.setenv("API_BASE_URL", "http://localhost:8000")

    requests_calls: list[tuple[str, dict]] = []
    import builtins
    monkeypatch.setattr(builtins, "_DATA_BROWSER_TEST_CALLS", requests_calls, raising=False)
    app = _run_data_browser_page(requests_calls, token=None)
    observed_calls = builtins._DATA_BROWSER_TEST_CALLS

    assert not app.exception
    assert not observed_calls
    assert any("未完成管理員授權設定" in str(err.value) for err in app.error)
