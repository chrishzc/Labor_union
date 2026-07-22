"""Acceptance coverage for the order overview's filtering and pagination contract."""

from __future__ import annotations

import ast
from pathlib import Path


ORDERS_PAGE = Path(__file__).resolve().parents[1] / "ui" / "pages" / "02_orders.py"


def _overview_source() -> str:
    text = ORDERS_PAGE.read_text(encoding="utf-8")
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


def test_overview_paginates_to_at_most_ten_orders_per_page():
    overview = _overview_source()

    assert "page_size = 10" in overview
    assert "math.ceil(total_orders / page_size)" in overview
    assert "df_filtered.iloc[page_start:page_end]" in overview
    assert "訂單頁碼（每頁最多 10 筆）" in overview
    assert "共 {total_orders} 筆訂單，目前顯示第 {page_start + 1}–{page_end} 筆" in overview


def test_overview_reads_only_client_identity_status_for_eligibility_display():
    overview = _overview_source()

    assert "o.get('identity_status')" in overview
    assert "clients.identity_status" not in overview
