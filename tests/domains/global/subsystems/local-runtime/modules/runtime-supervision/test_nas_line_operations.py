"""
File: test_nas_line_operations.py
Description: 驗證公開 LINE 組合路由邊界、延後結果專用路由與 Gzip 回應壓縮。
"""
import asyncio
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.routing import iter_route_contexts
import httpx
import pytest


@pytest.fixture
def public_line():
    from api.nas_apps import line_app

    public = line_app()

    async def request(method, path, **kwargs):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=public),
            base_url="https://line.test",
        ) as http:
            return await http.request(method, path, **kwargs)

    return SimpleNamespace(public=public, request=request)


def test_current_pages_and_retired_candidate_links_are_served_with_correct_status(public_line):
    async def check():
        for path in ("/line-mobile-admin", "/line-deposit-payment", "/line-service-help"):
            response = await public_line.request("GET", path)
            assert response.status_code == 200, path
            assert "text/html" in response.headers["content-type"]
        for path in ("/line-candidate-contact", "/line-candidate-contact-customer"):
            assert (await public_line.request("GET", path)).status_code == 410
        for path in ("/admin/", "/setup", "/api/v1/admin/accounts"):
            assert (await public_line.request("GET", path)).status_code == 404

    asyncio.run(check())


def test_split_line_postponement_mounts_only_verified_result_handlers():
    from api.nas_apps import line_app
    from api.routes import staff_leave_intake

    base = "/api/v1/line/staff-self-service/leave-results"
    public = {route.path: route for route in iter_route_contexts(line_app().routes)}
    expected = {
        "cases": staff_leave_intake.leave_result_cases,
        "preview": staff_leave_intake.preview_leave_defer,
        "propose": staff_leave_intake.propose_leave_defer,
    }
    assert {path for path in public if path.startswith(base)} == {
        f"{base}/{name}" for name in (*expected, "submit")
    }
    assert not any("/line/staff-self-service/leave-requests" in path for path in public)
    for name, handler in expected.items():
        route = public[f"{base}/{name}"]
        assert route.methods == {"POST"}
        assert route.endpoint is handler
    retired = public[f"{base}/submit"]
    assert retired.endpoint is staff_leave_intake.submit_leave_result
    with pytest.raises(HTTPException) as rejected:
        retired.endpoint()
    assert rejected.value.status_code == 410
    assert rejected.value.detail["error"]["code"] == "staff_leave_direct_submit_retired"


def test_public_gateway_has_no_wildcard_management_forwarding(public_line):
    async def check():
        for path in (
            "/api/v1/orders/CASE-1/status",
            "/api/v1/admin/users",
            "/api/v1/line/mobile-admin/not-an-operation",
        ):
            assert (await public_line.request("POST", path, json={})).status_code == 404

    asyncio.run(check())


def test_public_line_app_gzip_compresses_large_liff_html_responses(public_line):
    async def check():
        response = await public_line.request(
            "GET",
            "/line-mobile-admin",
            headers={"Accept-Encoding": "gzip"},
        )
        assert response.status_code == 200
        assert response.headers.get("content-encoding") == "gzip"
        assert "Accept-Encoding" in response.headers.get("vary", "")
        assert len(response.text.encode("utf-8")) >= 1024
        assert "<html" in response.text.lower()

    asyncio.run(check())
