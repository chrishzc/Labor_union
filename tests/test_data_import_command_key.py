"""
File: test_data_import_command_key.py
Description: 驗證 HCM UI 僅在開發環境允許驗收用 command key 覆寫。
"""

from __future__ import annotations

import importlib


data_import_page = importlib.import_module("ui.pages.09_data_import")


def test_production_uses_digest_key_without_rendering_override(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(data_import_page.st, "text_input", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))

    assert data_import_page._resolve_command_key(b"workbook") == data_import_page._command_key(b"workbook")


def test_development_can_supply_a_conflict_verification_key(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setattr(data_import_page.st, "text_input", lambda *args, **kwargs: "controlled-conflict-key")

    assert data_import_page._resolve_command_key(b"workbook") == "controlled-conflict-key"
