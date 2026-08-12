import pytest
from fastapi import HTTPException

from api.routes.contract_signing import _response


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
