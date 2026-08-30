"""Retirement contract tests for the former Anomalies historical projector URLs."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_historical_order_review_remediator
from api.routes.historical_baseline_projector import (
    query_historical_baseline_projection_delivery,
    query_latest_historical_baseline_projection,
    router,
)


_CASE_NO = "CASE-HPROJ-RETIRE-001"
_DELIVERY_ID = "1" * 64
_REPLACEMENT = "/api/v1/orders/{case_no}/historical-operational-baseline"


def _assert_retired(error: HTTPException, *, correlation_id: str, replacement: str) -> None:
    assert error.status_code == 410
    payload = error.detail["error"]
    assert payload == {
        "category": "domain_blocked",
        "code": "historical_baseline_projector_endpoint_retired",
        "message": "歷史基線 projector 已由 Orders 作業基準 Query 取代。",
        "correlation_id": correlation_id,
        "field_errors": [],
        "domain_blockers": [f"replacement_identifier:{replacement}"],
        "retryable": False,
        "current_version": None,
    }


def test_case_endpoint_is_stable_typed_410_without_legacy_application() -> None:
    try:
        query_latest_historical_baseline_projection(
            case_no=_CASE_NO,
            correlation_header="legacy-case-correlation",
            principal=object(),
        )
    except HTTPException as error:
        _assert_retired(
            error,
            correlation_id="legacy-case-correlation",
            replacement=f"/api/v1/orders/{_CASE_NO}/historical-operational-baseline",
        )
    else:  # pragma: no cover - the route must never return a payload
        raise AssertionError("legacy case endpoint unexpectedly returned")


def test_delivery_endpoint_is_stable_typed_410_with_replacement_identifier() -> None:
    try:
        query_historical_baseline_projection_delivery(
            delivery_identity=_DELIVERY_ID,
            correlation_header="legacy-delivery-correlation",
            principal=object(),
        )
    except HTTPException as error:
        _assert_retired(
            error,
            correlation_id="legacy-delivery-correlation",
            replacement=_REPLACEMENT,
        )
    else:  # pragma: no cover - the route must never return a payload
        raise AssertionError("legacy delivery endpoint unexpectedly returned")


def test_fastapi_legacy_urls_remain_registered_but_never_reach_mysql_composition() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_historical_order_review_remediator] = lambda: object()
    client = TestClient(app)

    case_response = client.get(
        f"/api/v1/orders/{_CASE_NO}/historical-baseline-projector",
        headers={"X-Correlation-ID": "legacy-http-case"},
    )
    delivery_response = client.get(
        f"/api/v1/orders/historical-baseline-projector/deliveries/{_DELIVERY_ID}",
        headers={"X-Correlation-ID": "legacy-http-delivery"},
    )

    assert case_response.status_code == delivery_response.status_code == 410
    assert case_response.json()["detail"]["error"]["domain_blockers"] == [
        f"replacement_identifier:/api/v1/orders/{_CASE_NO}/historical-operational-baseline"
    ]
    assert delivery_response.json()["detail"]["error"]["domain_blockers"] == [
        f"replacement_identifier:{_REPLACEMENT}"
    ]


def test_retired_router_keeps_only_get_legacy_paths() -> None:
    assert {route.path for route in router.routes} == {
        "/api/v1/orders/{case_no}/historical-baseline-projector",
        "/api/v1/orders/historical-baseline-projector/deliveries/{delivery_identity}",
    }
    assert all(route.methods == {"GET"} for route in router.routes)
