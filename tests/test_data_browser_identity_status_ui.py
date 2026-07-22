"""Acceptance coverage for the data browser's client identity source."""

from __future__ import annotations

import ast
from pathlib import Path


DATA_BROWSER = Path(__file__).resolve().parents[1] / "ui" / "pages" / "01_data_browser.py"


def _module() -> ast.Module:
    return ast.parse(DATA_BROWSER.read_text(encoding="utf-8"))


def _assigned_dict(name: str) -> ast.Dict:
    assignment = next(
        node for node in _module().body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    )
    assert isinstance(assignment.value, ast.Dict)
    return assignment.value


def _literal_dict(value: ast.expr) -> dict[str, object]:
    return ast.literal_eval(value)


def test_data_browser_displays_only_client_identity_status_for_eligibility():
    source = DATA_BROWSER.read_text(encoding="utf-8")
    labels = _literal_dict(_assigned_dict("DB_COLUMN_LABEL_MAP"))

    assert labels["identity_status"] == "身分資格"
    assert "clients.identity_status" not in source


def test_client_identity_status_is_read_only_in_data_browser():
    editable_columns = _literal_dict(_assigned_dict("EDITABLE_COLUMNS"))

    assert "identity_status" not in editable_columns["clients"]
