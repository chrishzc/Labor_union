import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from types import SimpleNamespace

from api.routes.contract_signing import _response, router
from api.schemas.base import BaseResponse
from api.schemas.contract_signing import (
    ContractSigningManualAttestationPreviewView,
    ContractSigningQueryView,
    ContractSigningReceiptView,
)


def test_contract_signature_idempotency_conflict_is_typed_domain_blocker():
    with pytest.raises(HTTPException) as raised:
        _response(
            lambda: (_ for _ in ()).throw(
                ValueError("contract_signature_idempotency_conflict")
            ),
            "unused",
            "wp56-correlation",
        )

    assert raised.value.status_code == 409
    assert raised.value.detail["error"] == {
        "category": "domain_blocked",
        "code": "contract_signature_idempotency_conflict",
        "message": "契約簽署流程目前無法執行。",
        "correlation_id": "wp56-correlation",
        "field_errors": [],
        "domain_blockers": [],
        "retryable": False,
        "current_version": None,
    }


def test_contract_document_version_stale_is_typed_domain_blocker():
    with pytest.raises(HTTPException) as raised:
        _response(
            lambda: (_ for _ in ()).throw(ValueError("contract_document_version_stale")),
            "unused",
            "wp56-stale-correlation",
        )

    assert raised.value.status_code == 409
    assert raised.value.detail["error"]["code"] == "contract_document_version_stale"
    assert raised.value.detail["error"]["category"] == "domain_blocked"


def test_manual_contract_preview_stale_is_a_typed_domain_blocker():
    with pytest.raises(HTTPException) as raised:
        _response(
            lambda: (_ for _ in ()).throw(ValueError("manual_contract_preview_stale")),
            "unused",
            "manual-preview-correlation",
        )

    assert raised.value.status_code == 409
    assert raised.value.detail["error"]["code"] == "manual_contract_preview_stale"


def test_manual_contract_requires_customer_acceptance_as_a_typed_domain_blocker():
    with pytest.raises(HTTPException) as raised:
        _response(
            lambda: (_ for _ in ()).throw(ValueError("manual_contract_customer_acceptance_required")),
            "unused",
            "manual-acceptance-correlation",
        )

    assert raised.value.status_code == 409
    assert raised.value.detail["error"]["code"] == "manual_contract_customer_acceptance_required"


def test_contract_signing_success_endpoints_use_closed_output_views():
    response_models = {
        route.path: route.response_model
        for route in router.routes
        if route.response_model is not None
    }

    assert response_models["/api/v1/orders/{case_no}/contract-signing"] == BaseResponse[
        ContractSigningQueryView
    ]
    assert all(
        model.model_config["extra"] == "forbid"
        for model in (
            ContractSigningQueryView,
            ContractSigningReceiptView,
            ContractSigningManualAttestationPreviewView,
        )
    )


@pytest.mark.parametrize(("path", "openapi_path"), [
    ("client/send", "client/send"),
    ("staff-segments/71/send", "staff-segments/{segment_id}/send"),
])
def test_contract_download_link_send_routes_are_unreachable(path, openapi_path):
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        f"/api/v1/orders/SYNTHETIC/contract-signing/{path}",
        json={"download_url": "https://example.invalid/contract"},
        headers={"Idempotency-Key": "retired-send-test", "X-Correlation-ID": "retired-send-test"},
    )

    assert response.status_code == 404
    paths = client.get("/openapi.json").json()["paths"]
    base = "/api/v1/orders/{case_no}/contract-signing"
    assert f"{base}/{openapi_path}" not in paths
    assert f"{base}/{openapi_path.removesuffix('send')}signed-return" in paths
    assert f"{base}/{openapi_path.removesuffix('send')}manual-attestation" in paths
    assert base + "/documents/{document_version_id}/download" in paths


def test_contract_signing_receipt_preserves_nullable_json_keys():
    response = _response(
        lambda: SimpleNamespace(
            document_version_id=12,
            signing_event_id=34,
            line_delivery_task_id=None,
            commitment_id=None,
        ),
        "已完成",
        "contract-signing-test",
    )

    assert isinstance(response.data, ContractSigningReceiptView)
    assert response.model_dump()["data"] == {
        "document_version_id": 12,
        "signing_event_id": 34,
        "line_delivery_task_id": None,
        "commitment_id": None,
        "contract_identity": None,
    }
