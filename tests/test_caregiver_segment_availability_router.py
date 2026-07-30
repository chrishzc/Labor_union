from pathlib import Path

import ast
import pytest
from datetime import date, datetime
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi import HTTPException
from pydantic import ValidationError

from api.dependencies import admin_auth
from api.routes import caregiver_segment_availability as router_module
from services.admin_auth_service import AdminPrincipal


def _principal() -> AdminPrincipal:
    return AdminPrincipal(11, "admin", "Admin", "system_admin")


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router_module.router)
    return app


def _headers() -> dict[str, str]:
    return {"X-Internal-API-Key": "internal-test-key", "Authorization": "Bearer session-token"}


def _as_of_body() -> dict:
    return {
        "as_of": "2026-07-10",
        "segment_count": 2,
        "segment_drafts": [
            {
                "staff_id": 10,
                "start_date": "2026-07-01",
                "end_date": "2026-07-02",
            },
        ],
    }


def _service_complete_payload() -> dict:
    return {
        "case_no": "CASE-100",
        "planned_start_date": "2026-07-01",
        "planned_end_date": "2026-07-03",
        "feasibility": "complete",
        "complete_combinations": [
            [
                {
                    "segment_index": 0,
                    "staff_id": 1,
                    "start_date": "2026-07-01",
                    "end_date": "2026-07-02",
                },
                {
                    "segment_index": 1,
                    "staff_id": 2,
                    "start_date": "2026-07-03",
                    "end_date": "2026-07-03",
                },
            ],
        ],
        "segment_candidates": [
            {
                "segment_index": 0,
                "staff_id": 1,
                "start_date": "2026-07-01",
                "end_date": "2026-07-02",
            },
        ],
        "conflicts": [],
    }


def _service_partial_payload() -> dict:
    return {
        "case_no": "CASE-100",
        "planned_start_date": "2026-07-01",
        "planned_end_date": "2026-07-03",
        "feasibility": "partial",
        "complete_combinations": [],
        "segment_candidates": [
            {
                "segment_index": 0,
                "staff_id": 1,
                "start_date": "2026-07-01",
                "end_date": "2026-07-03",
            }
        ],
        "conflicts": [
            {
                "segment_index": 0,
                "staff_id": 1,
                "work_date": "2026-07-02",
                "reason_code": "coverage_gap",
            },
        ],
    }


def test_router_delegates_once_and_forwards_payload_exactly(monkeypatch):
    captured: list[dict] = []

    def fake_service(*, case_no, segment_count, segment_drafts, as_of):
        captured.append(
            {
                "case_no": case_no,
                "segment_count": segment_count,
                "segment_drafts": segment_drafts,
                "as_of": as_of,
            }
        )
        return _service_complete_payload()

    monkeypatch.setattr(router_module, "search_segmented_caregiver_availability", fake_service)

    request = router_module.CaregiverSegmentAvailabilitySearchRequest(**_as_of_body())
    router_module.search_caregiver_segment_availability(request, "CASE-100", _principal())

    assert len(captured) == 1
    payload = captured[0]
    assert payload["case_no"] == "CASE-100"
    assert payload["segment_count"] == 2
    assert payload["as_of"] == date(2026, 7, 10)
    assert payload["segment_drafts"] == [
        {"staff_id": 10, "start_date": "2026-07-01", "end_date": "2026-07-02"}
    ]


def test_single_caregiver_gate_owns_internal_segment_count_one(monkeypatch):
    captured = {}

    def fake_service(**kwargs):
        captured.update(kwargs)
        return _service_complete_payload()

    monkeypatch.setattr(
        router_module,
        "search_segmented_caregiver_availability",
        fake_service,
    )
    request = router_module.SingleCaregiverEligibilityRequest(
        start_date="2026-07-01",
        end_date="2026-07-03",
        as_of="2026-06-20",
    )

    response = router_module.check_single_caregiver_eligibility(
        request,
        "CASE-100",
        _principal(),
    )

    assert response.data.feasibility == "complete"
    assert captured == {
        "case_no": "CASE-100",
        "segment_count": 1,
        "segment_drafts": [
            {"start_date": "2026-07-01", "end_date": "2026-07-03"}
        ],
        "as_of": date(2026, 6, 20),
    }


def test_public_multi_segment_request_rejects_single_segment():
    payload = _as_of_body()
    payload["segment_count"] = 1

    with pytest.raises(ValidationError):
        router_module.CaregiverSegmentAvailabilitySearchRequest(**payload)


def test_router_returns_complete_and_partial_200_when_valid(monkeypatch):
    monkeypatch.setattr(
        router_module,
        "search_segmented_caregiver_availability",
        lambda **_kwargs: _service_complete_payload(),
    )
    request = router_module.CaregiverSegmentAvailabilitySearchRequest(**_as_of_body())
    complete_response = router_module.search_caregiver_segment_availability(
        request, "CASE-100", _principal()
    )
    assert complete_response.data.feasibility == "complete"
    assert complete_response.data.case_no == "CASE-100"

    monkeypatch.setattr(
        router_module,
        "search_segmented_caregiver_availability",
        lambda **_kwargs: _service_partial_payload(),
    )
    partial_response = router_module.search_caregiver_segment_availability(
        request, "CASE-100", _principal()
    )
    assert partial_response.data.feasibility == "partial"
    assert partial_response.data.segment_candidates


def test_router_http_complete_and_partial_response_codes(monkeypatch):
    app = _build_app()
    client = TestClient(app)
    _configure_bypass_auth(monkeypatch)
    responses = [_service_complete_payload(), _service_partial_payload()]

    def fake_service(**_kwargs):
        return responses.pop(0)

    monkeypatch.setattr(router_module, "search_segmented_caregiver_availability", fake_service)

    first = client.post(
        "/api/v1/orders/CASE-100/caregiver-segment-availability/search",
        headers={"X-Internal-API-Key": "internal-test-key"},
        json=_as_of_body(),
    )
    assert first.status_code == 200
    assert first.json()["data"]["feasibility"] == "complete"

    second = client.post(
        "/api/v1/orders/CASE-100/caregiver-segment-availability/search",
        headers={"X-Internal-API-Key": "internal-test-key"},
        json=_as_of_body(),
    )
    assert second.status_code == 200
    assert second.json()["data"]["feasibility"] == "partial"


def test_router_maps_case_not_found_and_not_in_negotiation(monkeypatch):
    monkeypatch.setattr(
        router_module,
        "search_segmented_caregiver_availability",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("case not found")),
    )
    request = router_module.CaregiverSegmentAvailabilitySearchRequest(**_as_of_body())

    with pytest.raises(HTTPException) as error:
        router_module.search_caregiver_segment_availability(request, "CASE-100", _principal())
    assert error.value.status_code == 404

    monkeypatch.setattr(
        router_module,
        "search_segmented_caregiver_availability",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("case is not in negotiation stage")),
    )
    with pytest.raises(HTTPException) as error:
        router_module.search_caregiver_segment_availability(request, "CASE-100", _principal())
    assert error.value.status_code == 409


def test_router_maps_service_validation_and_unexpected_errors(monkeypatch):
    monkeypatch.setattr(
        router_module,
        "search_segmented_caregiver_availability",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("segment_drafts are out of order")),
    )
    request = router_module.CaregiverSegmentAvailabilitySearchRequest(**_as_of_body())
    with pytest.raises(HTTPException) as error:
        router_module.search_caregiver_segment_availability(request, "CASE-100", _principal())
    assert error.value.status_code == 422

    monkeypatch.setattr(
        router_module,
        "search_segmented_caregiver_availability",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("sql unavailable")),
    )
    with pytest.raises(HTTPException) as error:
        router_module.search_caregiver_segment_availability(request, "CASE-100", _principal())
    assert error.value.status_code == 500
    assert error.value.detail == "Unexpected error during caregiver segment availability search"


def test_search_request_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        router_module.CaregiverSegmentAvailabilitySearchRequest(
            segment_count=2,
            as_of="2026-07-10",
            segment_drafts=[],
            unexpected=123,
        )

    with pytest.raises(ValidationError):
        router_module.CaregiverSegmentDraft(staff_id=10, bad_field="x")


def test_search_request_rejects_invalid_segment_count_and_staff_id():
    with pytest.raises(ValidationError):
        router_module.CaregiverSegmentAvailabilitySearchRequest(
            segment_count=0,
            as_of="2026-07-10",
            segment_drafts=[],
        )

    with pytest.raises(ValidationError):
        router_module.CaregiverSegmentDraft(staff_id=True)

    with pytest.raises(ValidationError):
        router_module.CaregiverSegmentDraft(staff_id=0)


def test_search_request_rejects_invalid_dates():
    with pytest.raises(ValidationError):
        router_module.CaregiverSegmentAvailabilitySearchRequest(
            segment_count=2,
            as_of="2026/07/10",
            segment_drafts=[],
        )

    with pytest.raises(ValidationError):
        router_module.CaregiverSegmentDraft(
            staff_id=1,
            start_date="2026/07/01",
        )

    with pytest.raises(ValidationError):
        router_module.CaregiverSegmentAvailabilitySearchRequest(
            segment_count=2,
            as_of="2026-07-10T00:00:00",
            segment_drafts=[],
        )

    with pytest.raises(ValidationError):
        router_module.CaregiverSegmentAvailabilitySearchRequest(
            segment_count=2,
            as_of=datetime(2026, 7, 10, 8, 30),
            segment_drafts=[],
        )

    with pytest.raises(ValidationError):
        router_module.CaregiverSegmentDraft(
            staff_id=1,
            start_date="2026-07-01T00:00:00",
            end_date="2026-07-02",
        )

    with pytest.raises(ValidationError):
        router_module.CaregiverSegmentDraft(
            staff_id=1,
            start_date="2026-07-01",
            end_date=datetime(2026, 7, 2),
        )


def test_router_preserves_segment_drafts_order(monkeypatch):
    captured = {}

    def fake_service(*, case_no, segment_drafts, **_kwargs):
        captured["segment_drafts"] = segment_drafts
        return _service_complete_payload()

    monkeypatch.setattr(router_module, "search_segmented_caregiver_availability", fake_service)
    request = router_module.CaregiverSegmentAvailabilitySearchRequest(
        segment_count=2,
        as_of="2026-07-10",
        segment_drafts=[
            {"staff_id": 2},
            {"staff_id": 1, "start_date": "2026-07-02", "end_date": "2026-07-03"},
        ],
    )
    router_module.search_caregiver_segment_availability(request, "CASE-100", _principal())
    assert captured["segment_drafts"] == [
        {"staff_id": 2},
        {"staff_id": 1, "start_date": "2026-07-02", "end_date": "2026-07-03"},
    ]


def _configure_formal_auth(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "true")
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-test-key")


def _configure_bypass_auth(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "false")
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-test-key")


def test_formal_auth_missing_or_invalid_internal_key_and_bearer(monkeypatch):
    app = _build_app()
    client = TestClient(app)
    _configure_formal_auth(monkeypatch)
    response = client.post(
        "/api/v1/orders/CASE-100/caregiver-segment-availability/search",
        headers={"Authorization": "Bearer session-token"},
        json=_as_of_body(),
    )
    assert response.status_code == 401

    response = client.post(
        "/api/v1/orders/CASE-100/caregiver-segment-availability/search",
        headers={"X-Internal-API-Key": "wrong-key"},
        json=_as_of_body(),
    )
    assert response.status_code == 401

    response = client.post(
        "/api/v1/orders/CASE-100/caregiver-segment-availability/search",
        headers={"X-Internal-API-Key": "internal-test-key"},
        json=_as_of_body(),
    )
    assert response.status_code == 401

    monkeypatch.setattr(
        admin_auth,
        "get_admin_session",
        lambda _token: None,
    )
    response = client.post(
        "/api/v1/orders/CASE-100/caregiver-segment-availability/search",
        headers=_headers(),
        json=_as_of_body(),
    )
    assert response.status_code == 401


def test_formal_auth_internal_key_missing_config_returns_503(monkeypatch):
    app = _build_app()
    client = TestClient(app)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "true")
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)

    response = client.post(
        "/api/v1/orders/CASE-100/caregiver-segment-availability/search",
        headers={"X-Internal-API-Key": "anything", "Authorization": "Bearer session-token"},
        json=_as_of_body(),
    )
    assert response.status_code == 503


def test_formal_auth_role_guard_and_dev_bypass(monkeypatch):
    app = _build_app()
    client = TestClient(app)
    _configure_formal_auth(monkeypatch)
    monkeypatch.setattr(
        admin_auth,
        "get_admin_session",
        lambda _token: AdminPrincipal(1, "line", "Line Manager", "line_manager"),
    )
    monkeypatch.setattr(
        router_module,
        "search_segmented_caregiver_availability",
        lambda **_kwargs: _service_partial_payload(),
    )

    response = client.post(
        "/api/v1/orders/CASE-100/caregiver-segment-availability/search",
        headers=_headers(),
        json=_as_of_body(),
    )
    assert response.status_code == 403

    _configure_bypass_auth(monkeypatch)
    monkeypatch.setattr(
        router_module,
        "search_segmented_caregiver_availability",
        lambda **_kwargs: _service_partial_payload(),
    )
    response = client.post(
        "/api/v1/orders/CASE-100/caregiver-segment-availability/search",
        headers={"X-Internal-API-Key": "internal-test-key"},
        json=_as_of_body(),
    )
    assert response.status_code == 200


def test_openapi_and_response_shape_covered():
    app = _build_app()
    openapi = app.openapi()
    assert "/api/v1/orders/{case_no}/caregiver-segment-availability/search" in openapi["paths"]
    assert "/api/v1/orders/{case_no}/caregiver-single-eligibility/check" in openapi["paths"]
    post = openapi["paths"]["/api/v1/orders/{case_no}/caregiver-segment-availability/search"]["post"]
    request_schema = post["requestBody"]["content"]["application/json"]["schema"]
    request_ref = request_schema["$ref"].split("/")[-1]
    request_component = openapi["components"]["schemas"][request_ref]
    assert set(request_component["required"]) == {"segment_count", "segment_drafts", "as_of"}
    segment_schema = request_component["properties"]["segment_count"]
    segment_enum = segment_schema.get("enum") or segment_schema.get("allOf", [{}])[0].get("enum")
    assert segment_enum == [2, 3, 4]
    assert "additionalProperties" in request_component
    assert request_component["additionalProperties"] is False

    response_schema = post["responses"]["200"]["content"]["application/json"]["schema"]
    if "$ref" in response_schema:
        response_ref = response_schema["$ref"].split("/")[-1]
        response_component = openapi["components"]["schemas"][response_ref]
        assert "data" in response_component["properties"]


def test_router_source_is_read_only_and_free_of_db_mutation_patterns():
    source_path = Path(router_module.__file__).resolve()
    source = source_path.read_text(encoding="utf-8")
    lowered = source.lower()

    forbidden_tokens = [
        "get_connection",
        "db_service",
        "commit(",
        "rollback(",
        "insert",
        "update",
        "delete ",
        "replace",
        "drop ",
        "orders.staff_id",
        "legacy recommendation",
        "get_recommended_staff_for_order",
        "pymysql",
    ]
    for token in forbidden_tokens:
        assert token not in lowered

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        module = getattr(node, "module", None) or ""
        if "db_service" in module or "pymysql" in module:
            pytest.fail(f"Router should not import module: {module}")
        for alias in node.names:
            if alias.name in {"db_service", "pymysql"} or "get_connection" in alias.name:
                pytest.fail(f"Router should not import symbol: {alias.name}")
