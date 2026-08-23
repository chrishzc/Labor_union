"""
File: test_react_phase3b_public_contracts.py
Description: 凍結 Phase 3B1 四個 bounded flow 的 route、strict schema 與錯誤邊界。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from api.schemas.staff_availability import (
    StaffAvailabilityApplyBody,
    StaffAvailabilityPreviewView,
    StaffAvailabilityReceiptView,
)
from api.schemas.staff_matching_preferences import (
    DefinitionPreviewView,
    ProfileApplyRequest,
    ProfilePreviewView,
    StaffPreferenceProfileApplyReceiptView,
)
from api.schemas.staff_retirement import (
    StaffLifecycleApplyInput,
    StaffLifecycleApplyReceiptView,
    StaffLifecyclePreviewView,
)
from api.routes import staff_availability, staff_matching_preferences, staff_retirement


ROOT = Path(__file__).resolve().parents[1]


def _route_signatures(router):
    return {
        (route.path, method)
        for route in router.routes
        for method in route.methods
    }


def test_phase3b1_http_allowlist_has_no_dynamic_or_legacy_mutation_path():
    assert _route_signatures(staff_matching_preferences.router) >= {
        (
            "/api/v1/scheduling/staff-matching-preferences/definitions",
            "GET",
        ),
        (
            "/api/v1/scheduling/staff-matching-preferences/staff/{staff_id}",
            "GET",
        ),
        (
            "/api/v1/scheduling/staff-matching-preferences/staff/{staff_id}/preview",
            "POST",
        ),
        (
            "/api/v1/scheduling/staff-matching-preferences/staff/{staff_id}/apply",
            "POST",
        ),
    }
    assert _route_signatures(staff_availability.router) >= {
        ("/api/v1/scheduling/staff/{staff_id}/availability-blocks", "GET"),
        (
            "/api/v1/scheduling/staff/{staff_id}/availability-blocks/preview",
            "POST",
        ),
        (
            "/api/v1/scheduling/staff/{staff_id}/availability-blocks/apply",
            "POST",
        ),
    }
    assert _route_signatures(staff_retirement.router) >= {
        ("/api/v1/staff/{staff_id}/lifecycle", "GET"),
        ("/api/v1/staff/{staff_id}/{action}/preview", "POST"),
        ("/api/v1/staff/{staff_id}/{action}/apply", "POST"),
    }
    assert not any(
        route.path.endswith("/definitions") and "POST" in route.methods
        for route in staff_matching_preferences.router.routes
    )


@pytest.mark.parametrize(
    "schema",
    [
        DefinitionPreviewView,
        ProfilePreviewView,
        ProfileApplyRequest,
        StaffPreferenceProfileApplyReceiptView,
        StaffAvailabilityApplyBody,
        StaffAvailabilityPreviewView,
        StaffAvailabilityReceiptView,
        StaffLifecycleApplyInput,
        StaffLifecyclePreviewView,
        StaffLifecycleApplyReceiptView,
    ],
)
def test_phase3b1_public_models_forbid_unknown_fields(schema):
    assert schema.model_config.get("extra") == "forbid"


def test_fingerprints_are_lowercase_64_hex_and_receipts_are_distinct_views():
    availability_payload = {
        "action": "create_pause",
        "reason": "暫停接案",
        "start_date": "2026-10-01",
        "expected_version": 0,
        "preview_fingerprint": "A" * 64,
    }
    with pytest.raises(ValidationError):
        StaffAvailabilityApplyBody.model_validate(availability_payload)

    lifecycle_payload = {
        "effective_at": "2026-08-15T09:00:00+08:00",
        "reason_code": "left_union",
        "expected_version": 0,
        "preview_fingerprint": "a" * 63 + "g",
    }
    with pytest.raises(ValidationError):
        StaffLifecycleApplyInput.model_validate(lifecycle_payload)

    lifecycle_naive = dict(lifecycle_payload)
    lifecycle_naive["preview_fingerprint"] = "a" * 64
    lifecycle_naive["effective_at"] = "2026-08-15T09:00:00"
    with pytest.raises(ValidationError):
        StaffLifecycleApplyInput.model_validate(lifecycle_naive)

    assert {"preview_fingerprint", "idempotency_key"}.issubset(
        StaffPreferenceProfileApplyReceiptView.model_fields
    )
    assert {"preview_fingerprint", "idempotency_key"}.issubset(
        StaffLifecycleApplyReceiptView.model_fields
    )
    assert "resulting_version" in StaffLifecycleApplyReceiptView.model_fields


def test_global_error_boundary_owns_business_errors_not_raw_route_details():
    for filename in (
        "api/routes/staff_matching_preferences.py",
        "api/routes/staff_retirement.py",
    ):
        source = (ROOT / filename).read_text(encoding="utf-8")
        assert 'detail={"code"' not in source
        assert 'detail={"message"' not in source


def test_availability_correlation_is_request_scoped_not_fixed_query_literal():
    source = (ROOT / "api/routes/staff_availability.py").read_text(encoding="utf-8")
    assert 'CorrelationId("staff-availability-query")' not in source
    assert "X-Correlation-ID" in source
