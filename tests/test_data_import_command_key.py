"""
File: test_data_import_command_key.py
Description: 驗證資料匯入中心的穩定 command key 與各 typed category card wiring。
"""

from __future__ import annotations

import importlib
from pathlib import Path


data_import_page = importlib.import_module("ui.pages.09_data_import")


def test_production_uses_digest_key_without_rendering_override(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(data_import_page.st, "text_input", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))

    assert data_import_page._resolve_command_key(b"workbook") == data_import_page._command_key(b"workbook")


def test_development_can_supply_a_conflict_verification_key(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setattr(data_import_page.st, "text_input", lambda *args, **kwargs: "controlled-conflict-key")

    assert data_import_page._resolve_command_key(b"workbook") == "controlled-conflict-key"


def test_hcm_preview_state_is_reset_when_selected_workbook_changes(monkeypatch):
    monkeypatch.setattr(data_import_page.st, "session_state", {})
    state = data_import_page._hcm_import_state(b"first")
    state["preview"] = object()

    changed = data_import_page._hcm_import_state(b"second")

    assert "preview" not in changed


def test_data_import_center_wires_finance_through_typed_ui_client():
    body = Path(data_import_page.__file__).read_text(encoding="utf-8")

    assert "FinanceImportApiClient" in body
    assert "render_finance_import_panel" in body
    assert "import_finance_excel" not in body


def test_data_import_center_has_all_five_typed_cards_without_placeholder():
    body = Path(data_import_page.__file__).read_text(encoding="utf-8")

    for client_name in (
        "HcmImportApiClient",
        "ClientBeClassImportApiClient",
        "StaffHistoricalImportApiClient",
        "HistoricalOrderAdoptionApiClient",
        "FinanceImportApiClient",
    ):
        assert client_name in body
    assert "後續類別" not in body
    assert "process_import" not in body


def test_hcm_card_requires_typed_preview_before_apply():
    body = Path(data_import_page.__file__).read_text(encoding="utf-8")

    assert "client.preview_workbook" in body
    assert "client.apply_workbook" in body
    assert ".ingest_workbook(workbook.name" not in body
    assert 'confirmation != "APPLY"' in body


def test_data_import_center_does_not_navigate_to_warning_center():
    body = Path(data_import_page.__file__).read_text(encoding="utf-8")

    assert "nav_helper" not in body
    assert "前往異常警示中心" not in body


def test_hcm_card_explains_partial_formal_case_behavior():
    body = Path(data_import_page.__file__).read_text(encoding="utf-8")

    assert "錯誤欄位保持空值" in body
