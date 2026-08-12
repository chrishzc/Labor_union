"""Guard the two read workspaces against reintroducing manual load gates."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FINANCE_PAGE = ROOT / "ui/pages/04_finance.py"


def _function_source(function_name: str) -> str:
    source = FINANCE_PAGE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    return ast.get_source_segment(source, function) or ""


def test_accounts_payable_workspace_loads_without_manual_toggle() -> None:
    source = _function_source("_render_accounts_payable_workspace")

    assert "st.toggle" not in source
    assert "load_accounts_payable" not in source
    assert "_render_tab4_accounts_payable()" in source


def test_subsidy_reconciliation_workspace_loads_without_manual_toggle() -> None:
    source = _function_source("_render_subsidy_reconciliation_workspace")

    assert "st.toggle" not in source
    assert "load_subsidy_reconciliation" not in source
    assert "_render_tab5_subsidy_reconciliation()" in source
    assert "_render_government_subsidy_claim_workspace()" in source


def test_subsidy_workspace_exposes_existing_claim_plan_panel() -> None:
    source = _function_source("_render_government_subsidy_claim_workspace")

    assert "GovernmentSubsidyApiClient" in source
    assert "render_government_subsidy_claim_panel" in source
