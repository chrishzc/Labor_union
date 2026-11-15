"""Verified retirement contract for customer order-change self-service LIFF."""

import json
from pathlib import Path

from api.routes.line_order_change import admin_router, page_router, router


PROJECT_ROOT = Path(__file__).resolve().parents[8]


def test_customer_order_update_page_is_retired_and_not_exposed() -> None:
    """Verify that order_update.html is removed and /line-order-update is not routed."""
    page_file = PROJECT_ROOT / "line/static/order_update.html"
    assert not page_file.exists()

    menu = json.loads((PROJECT_ROOT / "config/line_menu.json").read_text(encoding="utf-8"))
    customer = next(item for item in menu["menus"] if item["id"] == "customer_menu")
    button_ids = {item["id"] for item in customer["buttons"]}
    assert "order_update" not in button_ids
    assert "profile_update" not in button_ids

    gateway = (PROJECT_ROOT / "line/static/gateway.html").read_text(encoding="utf-8")
    identity = (PROJECT_ROOT / "line/static/identity.html").read_text(encoding="utf-8")
    assert "order_update: '/line-order-update'" not in gateway
    assert 'order_update: "/line-order-update"' not in identity

    routes = {
        (route.path, method)
        for route in (*page_router.routes, *router.routes, *admin_router.routes)
        for method in getattr(route, "methods", ())
    }
    assert ("/line-order-update", "GET") not in routes
    # Admin change-request management endpoints remain available for union staff
    assert ("/api/v1/orders/change-requests", "GET") in routes
    assert ("/api/v1/orders/change-requests/{request_id}/complete", "POST") in routes
