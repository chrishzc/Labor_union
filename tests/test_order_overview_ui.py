"""Acceptance coverage for the order overview's filtering and pagination contract."""

from __future__ import annotations

import ast
from pathlib import Path

TAB1_MODULE = Path(__file__).resolve().parents[1] / "ui" / "pages" / "order" / "tab1_overview.py"
ORDERS_PAGE = Path(__file__).resolve().parents[1] / "ui" / "pages" / "02_orders.py"


def _overview_source() -> str:
    text = TAB1_MODULE.read_text(encoding="utf-8")
    module = ast.parse(text)
    overview = next(
        node for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "_render_tab1_overview"
    )
    return ast.get_source_segment(text, overview) or ""


def test_overview_has_unrestricted_status_filter_by_default():
    overview = _overview_source()

    assert '"篩選訂單狀態"' in overview
    assert "default=" not in overview
    assert "if status_filter else df_orders" in overview


def test_overview_displays_all_filtered_orders_in_one_selectbox():
    overview = _overview_source()

    assert "page_size = 10" not in overview
    assert "math.ceil(total_orders / page_size)" not in overview
    assert "df_filtered.iloc[page_start:page_end]" not in overview
    assert "訂單頁碼（每頁最多 10 筆）" not in overview
    assert "tab1_overview_page_number" not in overview
    assert "共 {total_orders} 筆訂單，請直接在下拉式選單中選擇要編輯的訂單。" in overview
    assert "選擇要編輯的訂單" in overview


def test_overview_reads_only_client_identity_status_for_eligibility_display():
    overview = _overview_source()

    assert "o.get('identity_status')" in overview
    assert "clients.identity_status" not in overview


def test_overview_only_has_single_order_list_view():
    overview = _overview_source()

    assert "selected_view = st.selectbox" not in overview
    assert "服務人員付款日/補助退款日" not in overview
    assert "選擇要編輯的訂單" in overview


def test_overview_imports_and_delegates_to_new_editor_module():
    tab1_text = TAB1_MODULE.read_text(encoding="utf-8")
    assert "from ui.pages.order.editor import render_editor" in tab1_text
    assert "ui.pages.04_edit_order" not in tab1_text

    overview = _overview_source()
    assert "render_editor(" in overview
    assert "_edit_order_mod" not in overview
