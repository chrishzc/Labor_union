"""
File: test_controlled_file_api.py
Description: 驗證受控檔案管理 API 的認證、typed projection 與錯誤邊界。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_persisted_admin
from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes import controlled_files
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ExpectedVersion
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.controlled_files.contracts import ControlledFileContent, ControlledFileStagingResult
from subsystems.controlled_files.workflow import (
    ControlledFileApplyOutcome,
    ControlledFileApplyReceipt,
    ControlledFileCandidate,
    ControlledFileOwner,
    ControlledFilePreview,
    ControlledFilePurpose,
    ControlledFileReadback,
    ControlledFileWorkflowError,
)


_STAGING_ID = "cfs_0123456789abcdef0123456789abcdef"
_FILE_ID = "cf_0123456789abcdef0123456789abcdef"
_RECEIPT_ID = "cfr_0123456789abcdef0123456789abcdef"
_NOW = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)


class _Workflow:
    def __init__(self) -> None:
        self.preview_calls = []
        self.apply_calls = []
        self.readback_calls = []
        self.receipt_calls = []
        self.stage_calls = []
        self.failure: ControlledFileWorkflowError | None = None
        self.readback_result = ControlledFileReadback(
            file_id=_FILE_ID,
            owner=ControlledFileOwner.ORDERS,
            purpose=ControlledFilePurpose.ORDER_NOTICE,
            subject_reference="ORD-HC019",
            filename="NOTICE_ORD-HC019_SEQ-1.pdf",
            logical_folder="orders/ORD-HC019",
            version=1,
            sha256_digest="a" * 64,
            mime_type="application/pdf",
            size_bytes=512,
            status="available",
            applied_at=_NOW,
        )
        candidate = ControlledFileCandidate(
            staging_id=_STAGING_ID,
            staging_version=2,
            owner=ControlledFileOwner.ORDERS,
            purpose=ControlledFilePurpose.ORDER_NOTICE,
            subject_reference="ORD-HC019",
            object_key="notice",
            logical_folder="orders/ORD-HC019",
            filename="NOTICE_ORD-HC019_SEQ-1.pdf",
            mime_type="application/pdf",
            size_bytes=512,
            sha256_digest="a" * 64,
            expires_at=_NOW + timedelta(hours=24),
        )
        self.preview_result = ControlledFilePreview(
            candidate=candidate,
            preview_fingerprint=PreviewFingerprint("b" * 64),
            expected_staging_version=ExpectedVersion(2),
            blockers=(),
        )
        self.receipt_result = ControlledFileApplyReceipt(
            receipt_id=_RECEIPT_ID,
            outcome=ControlledFileApplyOutcome.CREATED,
            readback=self.readback_result,
        )

    def preview(self, intent):
        self.preview_calls.append(intent)
        if self.failure is not None:
            raise self.failure
        return self.preview_result

    def stage(self, command):
        self.stage_calls.append(command)
        return ControlledFileStagingResult(
            staging_id=_STAGING_ID,
            filename=command.filename,
            mime_type=command.mime_type,
            size_bytes=len(command.content),
            sha256_digest="a" * 64,
            expires_at=_NOW + timedelta(hours=24),
            replayed=False,
        )

    def apply(self, command):
        self.apply_calls.append(command)
        if self.failure is not None:
            raise self.failure
        return self.receipt_result

    def readback(self, file_id):
        self.readback_calls.append(file_id)
        if self.failure is not None:
            raise self.failure
        return self.readback_result

    def read_receipt(self, receipt_id):
        self.receipt_calls.append(receipt_id)
        if self.failure is not None:
            raise self.failure
        return self.receipt_result

    def list_readbacks(self):
        return (self.readback_result,)

    def download(self, file_id):
        return ControlledFileContent(
            object_reference=file_id,
            filename=self.readback_result.filename,
            content_type=self.readback_result.mime_type,
            content=b"pdf",
            content_sha256="a" * 64,
        )


def _client(workflow: _Workflow) -> tuple[TestClient, list[Request]]:
    app = FastAPI()
    app.include_router(controlled_files.router)
    requests: list[Request] = []
    principal = AdminPrincipal(17, "storage-admin", "檔案管理員", "operator")

    def authorize(request: Request) -> AdminPrincipal:
        requests.append(request)
        return principal

    app.dependency_overrides[require_persisted_admin] = authorize
    app.dependency_overrides[
        controlled_files.get_controlled_file_route_workflow
    ] = lambda: workflow
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    return TestClient(app), requests


def _intent_payload() -> dict[str, object]:
    return {
        "staging_id": _STAGING_ID,
        "owner": "orders",
        "purpose": "order_notice",
        "subject_reference": "ORD-HC019",
        "object_key": "notice",
        "logical_folder": "orders/ORD-HC019",
    }


def _assert_no_locator_projection(payload: object) -> None:
    forbidden = {
        "path",
        "storage_path",
        "storage_locator",
        "object_reference",
        "url",
        "download_url",
        "content",
        "raw_bytes",
    }
    if isinstance(payload, dict):
        for key, value in payload.items():
            assert key.casefold() not in forbidden
            _assert_no_locator_projection(value)
    elif isinstance(payload, list):
        for value in payload:
            _assert_no_locator_projection(value)


def test_preview_is_typed_zero_command_projection() -> None:
    workflow = _Workflow()
    client, requests = _client(workflow)

    response = client.post(
        "/api/v1/storage/files/preview",
        json=_intent_payload(),
        headers={"X-Correlation-ID": "controlled-files-preview-test"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["preview_fingerprint"] == "b" * 64
    assert response.json()["data"]["candidate"]["logical_folder"] == "orders/ORD-HC019"
    assert len(workflow.preview_calls) == 1
    assert workflow.apply_calls == []
    assert len(requests) == 1
    _assert_no_locator_projection(response.json())


def test_apply_uses_persisted_actor_and_returns_terminal_receipt() -> None:
    workflow = _Workflow()
    client, requests = _client(workflow)
    payload = {
        **_intent_payload(),
        "expected_staging_version": 2,
        "preview_fingerprint": "b" * 64,
    }

    response = client.post(
        "/api/v1/storage/files/apply",
        json=payload,
        headers={
            "Idempotency-Key": "controlled-file.apply:ord-hc019",
            "X-Correlation-ID": "controlled-files-apply-test",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "file_id": _FILE_ID,
        "owner": "orders",
        "purpose": "order_notice",
        "subject_reference": "ORD-HC019",
            "filename": "NOTICE_ORD-HC019_SEQ-1.pdf",
            "logical_folder": "orders/ORD-HC019",
            "version": 1,
        "mime_type": "application/pdf",
        "size_bytes": 512,
        "status": "available",
        "applied_at": "2026-08-26T08:00:00Z",
        "receipt_id": _RECEIPT_ID,
        "outcome": "created",
        "receipt_type": "controlled_file_apply",
        "schema_version": "controlled-file-apply-receipt.v1",
        "sha256_digest": "a" * 64,
    }
    assert workflow.apply_calls[0].actor.actor_id == "admin:17"
    assert workflow.apply_calls[0].idempotency_key.value == "controlled-file.apply:ord-hc019"
    assert len(requests) == 1
    _assert_no_locator_projection(response.json())


def test_detail_and_receipt_are_authenticated_safe_projections() -> None:
    workflow = _Workflow()
    client, requests = _client(workflow)

    detail = client.get(f"/api/v1/storage/files/{_FILE_ID}")
    receipt = client.get(f"/api/v1/storage/receipts/{_RECEIPT_ID}")

    assert detail.status_code == 200
    assert "sha256_digest" not in detail.json()["data"]
    assert receipt.status_code == 200
    assert receipt.json()["data"]["sha256_digest"] == "a" * 64
    assert workflow.readback_calls == [_FILE_ID]
    assert workflow.receipt_calls == [_RECEIPT_ID]
    assert len(requests) == 2
    _assert_no_locator_projection(detail.json())
    _assert_no_locator_projection(receipt.json())


def test_workflow_error_maps_to_typed_safe_failure() -> None:
    workflow = _Workflow()
    workflow.failure = ControlledFileWorkflowError(
        "controlled_file_reconciliation_required",
        "C:\\secret\\nas\\object.pdf",
        retryable=True,
    )
    client, _requests = _client(workflow)

    response = client.post(
        "/api/v1/storage/files/preview",
        json=_intent_payload(),
        headers={"X-Correlation-ID": "controlled-files-error-test"},
    )

    assert response.status_code == 503
    error = response.json()["detail"]["error"]
    assert error["code"] == "controlled_file_reconciliation_required"
    assert error["retryable"] is True
    assert "secret" not in response.text
    assert "nas" not in response.text.casefold()


def test_closed_owner_purpose_pairing_and_header_contract_fail_before_workflow() -> None:
    workflow = _Workflow()
    client, _requests = _client(workflow)
    invalid_pair = {**_intent_payload(), "purpose": "staff_resume"}

    pairing_response = client.post(
        "/api/v1/storage/files/preview",
        json=invalid_pair,
    )
    invalid_key_response = client.post(
        "/api/v1/storage/files/apply",
        json={
            **_intent_payload(),
            "expected_staging_version": 2,
            "preview_fingerprint": "b" * 64,
        },
        headers={
            "Idempotency-Key": "UPPER CASE",
            "X-Correlation-ID": "controlled-files-invalid-key",
        },
    )

    assert pairing_response.status_code == 422
    assert invalid_key_response.status_code == 422
    assert workflow.preview_calls == []
    assert workflow.apply_calls == []


def test_composition_failure_remains_typed_after_authentication() -> None:
    app = FastAPI()
    app.include_router(controlled_files.router)
    principal = AdminPrincipal(17, "storage-admin", "檔案管理員", "operator")
    app.dependency_overrides[require_persisted_admin] = lambda: principal
    def unavailable():
        raise controlled_files.typed_http_error(
            503,
            "unavailable",
            "controlled_file_workflow_unavailable",
            "受控檔案服務尚未完成組態。",
            "controlled-files",
            retryable=True,
        )
    app.dependency_overrides[controlled_files.get_controlled_file_route_workflow] = unavailable
    client = TestClient(app)

    response = client.get(f"/api/v1/storage/files/{_FILE_ID}")

    assert response.status_code == 503
    assert response.json()["detail"]["error"]["code"] == "controlled_file_workflow_unavailable"


def test_staging_list_and_download_are_authenticated_real_routes() -> None:
    workflow = _Workflow()
    client, _ = _client(workflow)

    staged = client.post(
        "/api/v1/storage/staging",
        files={"document": ("notice.pdf", b"pdf", "application/pdf")},
        data={
            "owner": "orders",
            "purpose": "order_notice",
            "subject_reference": "ORD-HC019",
            "object_key": "notice",
            "logical_folder": "orders/ORD-HC019",
        },
        headers={"Idempotency-Key": "stage:ord-hc019", "X-Correlation-ID": "corr-stage"},
    )
    listed = client.get("/api/v1/storage/files")
    downloaded = client.get(f"/api/v1/storage/files/{_FILE_ID}/download")

    assert staged.status_code == listed.status_code == downloaded.status_code == 200
    assert staged.json()["data"]["staging_id"] == _STAGING_ID
    assert listed.json()["data"]["items"][0]["logical_folder"] == "orders/ORD-HC019"
    assert downloaded.content == b"pdf"
    assert "attachment" in downloaded.headers["content-disposition"]
