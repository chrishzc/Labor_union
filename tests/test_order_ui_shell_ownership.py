"""Acceptance coverage for Page 2 shell and entry-point ownership."""

from __future__ import annotations

import ast
from pathlib import Path


ORDERS_PAGE = Path(__file__).resolve().parents[1] / "ui" / "pages" / "02_orders.py"


def _function_source(name: str) -> str:
    text = ORDERS_PAGE.read_text(encoding="utf-8")
    tree = ast.parse(text)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert name in functions, f"missing Page 2 function: {name}"
    source = ast.get_source_segment(text, functions[name])
    assert source is not None
    return source


def test_show_only_loads_initial_data_then_delegates_to_order_ui_shell():
    show = _function_source("show")

    assert "db_service.get_order_details()" in show
    assert "db_service.get_table_data('clients')" in show
    assert "db_service.get_table_data('staff')" in show
    assert "_render_order_page_shell(orders_data, clients, staff_list)" in show
    assert "st.tabs(" not in show
    assert "get_table_data('payments')" not in show
    assert "update_payment_details" not in show
    for renderer in (
        "_render_tab1_overview(",
        "_render_tab2_assign(",
        "_render_tab3_finance(",
        "_render_tab4_accounts_payable(",
        "_render_tab5_subsidy_reconciliation(",
    ):
        assert renderer not in show


def test_order_ui_shell_owns_fixed_five_tab_layout_and_dispatch():
    shell = _function_source("_render_order_page_shell")

    assert "st.tabs([" in shell
    for label in (
        "訂單資訊總覽",
        "月嫂配對中心",
        "訂單帳務總覽",
        "應付帳款查詢/輸出",
        "核銷補助清冊",
    ):
        assert label in shell
    for renderer in (
        "_render_tab1_overview(orders_data)",
        "_render_tab2_assign(orders_data, clients, staff_list)",
        "_render_tab3_finance(orders_data)",
        "_render_tab4_accounts_payable()",
        "_render_tab5_subsidy_reconciliation()",
    ):
        assert renderer in shell
    assert "db_service." not in shell
    assert "_payment_api_request(" not in shell
