"""Acceptance coverage for the current Data Browser client identity source."""

from pathlib import Path

from api.routes import data_browser_admin


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT / "infrastructure/mysql/data_browser_query_repository.py"


def test_data_browser_projects_client_identity_status_with_the_expected_label():
    source = REPOSITORY.read_text(encoding="utf-8")
    assert '_cell("identity_status", "身分資格"' in source


def test_client_identity_status_is_read_only_in_data_browser():
    assert [(route.path, route.methods) for route in data_browser_admin.router.routes] == [
        ("/api/v1/admin/data-browser/sources/{source_id}", {"GET"}),
    ]
