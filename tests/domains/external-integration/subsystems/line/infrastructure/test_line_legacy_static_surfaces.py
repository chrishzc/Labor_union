"""
File: test_line_legacy_static_surfaces.py
Description: 驗證直接靜態舊入口不再繞過 canonical LIFF 身分與異動契約。
"""

from pathlib import Path

from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient

from api.main import app
from api.nas_apps import line_app


def test_static_bind_redirects_to_canonical_identity_and_preserves_navigation_query() -> None:
    response = TestClient(app).get(
        "/static/bind.html?userId=U-navigation-only&target=staff_schedule",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == (
        "/line-identity?userId=U-navigation-only&target=staff_schedule"
    )


def test_customer_profile_application_routes_are_retired() -> None:
    retired_prefixes = (
        "/api/v1/line/client-profile",
        "/api/v1/client-profile/requests",
        "/api/v1/line/mobile-admin/client-profile/requests",
    )
    for application in (app, line_app()):
        routes = [route.path for route in iter_route_contexts(application.routes)]
        assert "/line-profile-guard" not in routes
        assert "/line-profile-update" not in routes
        assert not any(path.startswith(retired_prefixes) for path in routes)
        assert "/line-staff-profile-update" in routes

    for file in ("profile_update.html", "profile_guard.html"):
        assert not (Path("line/static") / file).exists()
