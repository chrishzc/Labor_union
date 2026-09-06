"""HTTP composition proof for the existing Orders intake repair contract."""

import pytest
from fastapi.testclient import TestClient

from api.main import app


_CASE = "SYN-218-ROUTE"
_FP = "0" * 64


@pytest.mark.parametrize(
    ("path", "body", "headers"),
    [
        (
            f"/api/v1/orders/{_CASE}/intake-terms-bootstrap/preview",
            {"proposed_start_date": "2026-09-10", "proposed_service_days": 5},
            {},
        ),
        (
            f"/api/v1/orders/{_CASE}/intake-terms-bootstrap/apply",
            {
                "proposed_start_date": "2026-09-10",
                "proposed_service_days": 5,
                "expected_lifecycle_version": 0,
                "preview_fingerprint": _FP,
                "reason": "synthetic route composition proof",
            },
            {"Idempotency-Key": "route-terms", "X-Correlation-ID": "route-terms"},
        ),
        (
            f"/api/v1/orders/{_CASE}/intake-completion/client-name/preview",
            {"client_name": "合成姓名"},
            {},
        ),
        (
            f"/api/v1/orders/{_CASE}/intake-completion/client-name/apply",
            {
                "client_name": "合成姓名",
                "expected_lifecycle_version": 0,
                "preview_fingerprint": _FP,
                "reason": "synthetic route composition proof",
            },
            {"Idempotency-Key": "route-name", "X-Correlation-ID": "route-name"},
        ),
        (f"/api/v1/orders/{_CASE}/intake-completion/preview", None, {}),
        (
            f"/api/v1/orders/{_CASE}/intake-completion/apply",
            {
                "expected_lifecycle_version": 0,
                "preview_fingerprint": _FP,
                "reason": "synthetic route composition proof",
            },
            {"Idempotency-Key": "route-completion", "X-Correlation-ID": "route-completion"},
        ),
    ],
)
def test_intake_repair_public_paths_reach_persisted_admin_boundary(path, body, headers):
    client = TestClient(app)
    response = client.post(path, json=body, headers=headers)

    assert response.status_code == 401
    assert response.status_code != 404
