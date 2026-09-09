"""Static entrypoint and UX contract for the customer order-change LIFF."""

import json
from pathlib import Path

from api.routes.line_order_change import page_router, router


PROJECT_ROOT = Path(__file__).resolve().parents[8]


def test_liff_uses_verified_query_preview_apply_and_never_claims_direct_change() -> None:
    page = (PROJECT_ROOT / "line/static/order_update.html").read_text(encoding="utf-8")

    assert "liff.getIDToken()" in page
    assert "userId" not in page
    assert "/api/v1/line/order-change/query" in page
    assert "/api/v1/line/order-change/preview" in page
    assert "/api/v1/line/order-change/apply" in page
    assert page.index("/api/v1/line/order-change/preview") < page.index("/api/v1/line/order-change/apply")
    assert "送出申請不代表訂單已修改" in page
    assert "正式訂單尚未修改" in page
    assert "服務地址" in page
    assert "下廚需求" in page
    assert "服務日期／天數" in page
    assert "每日服務時段" in page


def test_studio_preview_skips_line_login_without_reaching_real_data_or_apply() -> None:
    page = (PROJECT_ROOT / "line/static/order_update.html").read_text(encoding="utf-8")

    assert 'get("studio_preview") === "1"' in page
    assert "後台安全預覽：已跳過 LINE 登入" in page
    assert "畫面只使用示意資料，不會讀取或修改正式資料" in page
    assert 'applyButton.disabled = true' in page
    assert 'if (!preview || studioPreview) return;' in page
    assert page.index("if (studioPreview)") < page.index("await liff.init({liffId})")


def test_rich_menu_and_liff_shell_route_order_update_to_real_page() -> None:
    menu = json.loads((PROJECT_ROOT / "config/line_menu.json").read_text(encoding="utf-8"))
    customer = next(item for item in menu["menus"] if item["id"] == "customer_menu")
    action = next(item for item in customer["buttons"] if item["id"] == "order_update")["action"]
    gateway = (PROJECT_ROOT / "line/static/gateway.html").read_text(encoding="utf-8")
    identity = (PROJECT_ROOT / "line/static/identity.html").read_text(encoding="utf-8")
    routes = {
        (route.path, method)
        for route in (*page_router.routes, *router.routes)
        for method in getattr(route, "methods", ())
    }
    main = (PROJECT_ROOT / "api/main.py").read_text(encoding="utf-8")

    assert action == {
        "type": "uri",
        "text": None,
        "uri": "?target=order_update",
        "uri_source": "liff",
        "data": None,
    }
    assert "order_update: '/line-order-update'" in gateway
    assert 'order_update: "/line-order-update"' in identity
    assert ("/line-order-update", "GET") in routes
    assert ("/api/v1/line/order-change/query", "POST") in routes
    assert ("/api/v1/line/order-change/preview", "POST") in routes
    assert ("/api/v1/line/order-change/apply", "POST") in routes
    assert "app.include_router(line_order_change.router)" in main
    assert "app.include_router(line_order_change.page_router)" in main
