"""Acceptance coverage for Tab 2's read-only client identity display."""

from __future__ import annotations

import ast
from pathlib import Path


ORDERS_PAGE = Path(__file__).resolve().parents[1] / "ui" / "pages" / "02_orders.py"


def _assign_source() -> str:
    text = ORDERS_PAGE.read_text(encoding="utf-8")
    module = ast.parse(text)
    renderer = next(
        node for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "_render_tab2_assign"
    )
    return ast.get_source_segment(text, renderer) or ""


def test_tab2_case_picker_and_summary_use_read_only_client_identity_status():
    assign_source = _assign_source()

    assert "o.get('identity_status')" in assign_source
    assert "target_order.get('identity_status')" in assign_source
    assert "身分資格（唯讀）" in assign_source


def test_tab2_does_not_reference_the_retired_order_eligibility_field():
    assign_source = _assign_source()

    assert "subsidy" not in assign_source
