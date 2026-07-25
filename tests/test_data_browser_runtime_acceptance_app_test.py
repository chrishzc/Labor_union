"""Runtime acceptance test for Data Browser page rendering and metadata request."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _run_data_browser_page(requests_calls: list[tuple[str, dict]]) -> AppTest:
    def _app():
        import importlib
        import builtins
        import os as _os
        import pathlib
        import sys as _sys

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
                return _FakeResponse(
                    {
                        "rows": [{"staff_id": "S-1", "name": "測試月嫂"}],
                        "columns": ["staff_id", "name"],
                        "primary_key": "staff_id",
                        "editable_columns": ["name"],
                        "read_only": False,
                        "valid_options": {},
                    }
                )
            if url.endswith("/api/v1/admin/data-browser/case_staff_assignments"):
                return _FakeResponse(
                    {
                        "rows": [],
                        "columns": ["id", "case_no"],
                        "primary_key": "id",
                        "editable_columns": [],
                        "read_only": True,
                        "valid_options": {},
                    }
                )
            if "/api/v1/admin/data-browser/" in url:
                table = url.rsplit("/", 1)[-1]
                return _FakeResponse(
                    {
                        "rows": [],
                        "columns": [f"{table}_id", "name"],
                        "primary_key": f"{table}_id",
                        "editable_columns": [],
                        "read_only": False,
                        "valid_options": {},
                    }
                )
            if url.endswith("/api/v1/holidays"):
                return _FakeResponse({"rows": []})
            raise AssertionError(f"Unexpected GET call: {url}")

        page.requests.get = _fake_get
        page.show()

    app = AppTest.from_function(_app)
    app.run()
    return app


def test_data_browser_show_calls_admin_metadata_with_auth_header(monkeypatch):
    monkeypatch.setenv("ADMIN_AUTH_CONTEXT", "admin_role")
    monkeypatch.setenv("API_BASE_URL", "http://localhost:8000")

    requests_calls: list[tuple[str, dict]] = []
    import builtins
    builtins._DATA_BROWSER_TEST_CALLS = requests_calls
    app = _run_data_browser_page(requests_calls)

    import builtins
    observed_calls = builtins._DATA_BROWSER_TEST_CALLS

    assert not app.exception
    assert any(
        "/api/v1/admin/data-browser/" in url
        and headers.get("X-Auth-Context") == "admin_role"
        for url, headers in observed_calls
    )


def test_data_browser_show_fails_fast_when_admin_context_missing(monkeypatch):
    monkeypatch.delenv("ADMIN_AUTH_CONTEXT", raising=False)
    monkeypatch.setenv("API_BASE_URL", "http://localhost:8000")

    requests_calls: list[tuple[str, dict]] = []
    import builtins
    builtins._DATA_BROWSER_TEST_CALLS = requests_calls
    app = _run_data_browser_page(requests_calls)
    observed_calls = builtins._DATA_BROWSER_TEST_CALLS

    assert not app.exception
    assert not observed_calls
    assert any("未完成管理員授權設定" in str(err.value) for err in app.error)
