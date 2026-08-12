import pytest

from ui.api_clients.contract_signing_api_client import (
    ContractSigningApiClient,
    ContractSigningApiError,
)


class _Response:
    def __init__(self, *, ok, status_code, payload, content=b""):
        self.ok = ok
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self):
        return self._payload


def test_contract_signing_client_validates_the_success_payload(monkeypatch):
    payload = {
        "success": True,
        "data": {
            "case_no": "CASE-1",
            "staff_segments": [{"segment_id": 1, "staff_id": 9, "sent": True, "signed_received": True}],
            "commitment_id": 5,
            "client_document_sent": True,
            "client_signed_received": False,
            "contract_identity": None,
        },
    }
    monkeypatch.setattr("ui.api_clients.contract_signing_api_client.requests.get", lambda *args, **kwargs: _Response(ok=True, status_code=200, payload=payload))

    result = ContractSigningApiClient(base_url="http://api", headers={}).query("CASE-1")

    assert result.staff_segments[0].signed_received is True
    assert result.commitment_id == 5


def test_contract_signing_client_rejects_untyped_error_payload(monkeypatch):
    monkeypatch.setattr("ui.api_clients.contract_signing_api_client.requests.get", lambda *args, **kwargs: _Response(ok=False, status_code=500, payload={}))

    with pytest.raises(ContractSigningApiError, match="請求失敗"):
        ContractSigningApiClient(base_url="http://api", headers={}).query("CASE-1")


def test_contract_signing_client_preserves_typed_error_code(monkeypatch):
    payload = {
        "detail": {
            "error": {
                "code": "contract_document_version_stale",
                "message": "契約文件版本已過期。",
            }
        }
    }
    monkeypatch.setattr(
        "ui.api_clients.contract_signing_api_client.requests.get",
        lambda *args, **kwargs: _Response(ok=False, status_code=409, payload=payload),
    )

    with pytest.raises(ContractSigningApiError) as raised:
        ContractSigningApiClient(base_url="http://api", headers={}).query("CASE-1")

    assert raised.value.status_code == 409
    assert raised.value.code == "contract_document_version_stale"


def test_contract_signing_client_preserves_request_validation_field(monkeypatch):
    payload = {
        "detail": [
            {
                "loc": ["body", "expected_document_version_id"],
                "msg": "Field required",
            }
        ]
    }
    monkeypatch.setattr(
        "ui.api_clients.contract_signing_api_client.requests.get",
        lambda *args, **kwargs: _Response(ok=False, status_code=422, payload=payload),
    )

    with pytest.raises(ContractSigningApiError) as raised:
        ContractSigningApiClient(base_url="http://api", headers={}).query("CASE-1")

    assert raised.value.code == "contract_signing_request_validation_error"
    assert "expected_document_version_id" in raised.value.message


def test_contract_signing_client_returns_a_typed_command_receipt(monkeypatch):
    payload = {
        "success": True,
        "data": {
            "document_version_id": 7,
            "signing_event_id": 8,
            "line_delivery_task_id": None,
            "commitment_id": 3,
            "contract_identity": "contract-identity",
        },
    }
    monkeypatch.setattr(
        "ui.api_clients.contract_signing_api_client.requests.request",
        lambda *args, **kwargs: _Response(ok=True, status_code=200, payload=payload),
    )

    receipt = ContractSigningApiClient(base_url="http://api", headers={}).send_client_contract(
        "CASE-1", "https://example.test/document",
    )

    assert receipt.document_version_id == 7
    assert receipt.contract_identity == "contract-identity"


def test_client_signed_return_uses_the_supplied_idempotency_key(monkeypatch):
    payload = {
        "success": True,
        "data": {
            "document_version_id": 7,
            "signing_event_id": 8,
            "line_delivery_task_id": None,
            "commitment_id": 3,
            "contract_identity": "contract-identity",
        },
    }
    captured = {}

    def request(*args, **kwargs):
        captured.update(kwargs)
        return _Response(ok=True, status_code=200, payload=payload)

    monkeypatch.setattr("ui.api_clients.contract_signing_api_client.requests.request", request)
    document = __import__("io").BytesIO(b"signed")

    ContractSigningApiClient(base_url="http://api", headers={}).record_client_signed_return(
        "CASE-1", document, "signed.pdf", "application/pdf", 7, idempotency_key="retry-key",
    )

    assert captured["headers"]["Idempotency-Key"] == "retry-key"


def test_contract_signing_client_downloads_a_document_from_its_case_bound_route(monkeypatch):
    captured = {}

    def get(*args, **kwargs):
        captured["url"] = args[0]
        captured.update(kwargs)
        return _Response(ok=True, status_code=200, payload={}, content=b"contract-bytes")

    monkeypatch.setattr("ui.api_clients.contract_signing_api_client.requests.get", get)

    content = ContractSigningApiClient(base_url="http://api", headers={"Authorization": "Bearer test"}).download_document("CASE-1", 8)

    assert content == b"contract-bytes"
    assert captured["url"].endswith("/CASE-1/contract-signing/documents/8/download")
    assert captured["headers"]["Authorization"] == "Bearer test"
