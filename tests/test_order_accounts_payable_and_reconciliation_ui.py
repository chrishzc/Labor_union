"""Direct acceptance tests for Tab 4 (Accounts Payable) and Tab 5 (Subsidy Reconciliation) submodules."""

from __future__ import annotations

import ast
from pathlib import Path

TAB4_FILE = Path(__file__).resolve().parents[1] / "ui" / "pages" / "order" / "tab4_accounts_payable.py"
TAB5_FILE = Path(__file__).resolve().parents[1] / "ui" / "pages" / "order" / "tab5_subsidy_reconciliation.py"


def test_tab4_accounts_payable_submodule_is_read_only_and_uses_report_request():
    assert TAB4_FILE.exists()
    text = TAB4_FILE.read_text(encoding="utf-8")
    module = ast.parse(text)

    renderer = next(
        node for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "_render_tab4_accounts_payable"
    )
    source = ast.get_source_segment(text, renderer) or ""

    assert "_finance_report_request(" in source
    assert '"POST"' not in source
    assert "_payment_api_request(" not in source
    assert "download=True" in source
    assert 'file_name=f"應付帳款_{target_month}.xlsx"' in source


def test_tab5_subsidy_reconciliation_submodule_is_read_only_and_uses_report_request():
    assert TAB5_FILE.exists()
    text = TAB5_FILE.read_text(encoding="utf-8")
    module = ast.parse(text)

    renderer = next(
        node for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "_render_tab5_subsidy_reconciliation"
    )
    source = ast.get_source_segment(text, renderer) or ""

    assert "_finance_report_request(" in source
    assert '"POST"' not in source
    assert "_payment_api_request(" not in source
    assert "download=True" in source
    assert 'subsidized_rows = report.get("subsidized_citizen_rows")' in source
    assert "if subsidized_rows:" in source
