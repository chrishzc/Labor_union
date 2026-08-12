from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from api.main import app
from api.routes.client_refund_reversal import preview_refund_overage_recovery


def test_unmatched_client_collection_endpoint_requires_immutable_matching() -> None:
    with pytest.raises(HTTPException) as raised:
        preview_refund_overage_recovery()

    assert raised.value.status_code == 410
    assert raised.value.detail["error"]["code"] == "client_over_refund_recovery_matching_required"


def test_unmatched_client_collection_http_endpoint_returns_typed_410() -> None:
    response = TestClient(app).post(
        "/api/v1/orders/115000001/client-finance/refund-overage-recovery/preview"
    )

    assert response.status_code == 410
    assert response.json()["detail"]["error"]["replacement"].endswith(
        "/matching/preview"
    )
