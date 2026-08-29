"""
File: test_line_staff_order_page.py
Description: 驗證月嫂訂單 LIFF 只顯示 strict typed staff-order view，不渲染 raw survey。
"""

from pathlib import Path


ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "requirements.txt").is_file() and (parent / "subsystems").is_dir()
)


def test_staff_order_page_does_not_render_untyped_raw_survey_rows() -> None:
    source = (ROOT / "line" / "static" / "staff_order_search.html").read_text(
        encoding="utf-8"
    )

    assert "survey_rows" not in source
    assert "查看完整表單填寫內容" not in source
    assert "/api/v1/line/staff-self-service/orders" in source


def test_staff_order_page_validates_typed_page_and_uses_safe_dom_rendering() -> None:
    source = (ROOT / "line" / "static" / "staff_order_search.html").read_text(
        encoding="utf-8"
    )

    assert "function requireStaffOrderPage" in source
    assert "function requireStaffOrderItem" in source
    assert "replaceChildren" in source
    assert ".innerHTML" not in source
    assert "JSON.stringify(data" not in source
    assert "data.detail?.error?.message" in source
