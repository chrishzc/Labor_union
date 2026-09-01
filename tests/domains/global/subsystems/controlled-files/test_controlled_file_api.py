"""Contract tests for the authenticated controlled-files API composition."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from fastapi import FastAPI
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
)

_STAGING_ID = "cfs_0123456789abcdef0123456789abcdef"
_FILE_ID = "cf_0123456789abcdef0123456789abcdef"
_RECEIPT_ID = "cfr_0123456789abcdef0123456789abcdef"
_NOW = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)


def _workflow() -> Mock:
    workflow = Mock()
    readback = ControlledFileReadback(
        file_id=_FILE_ID,
        owner=ControlledFileOwner.ORDERS,
        purpose=ControlledFilePurpose.ORDER_NOTICE,
        subject_reference="ORD-HC019",
        filename="notice.pdf",
        logical_folder="orders/ORD-HC019",
        version=1,
        sha256_digest="a" * 64,
        mime_type="application/pdf",
        size_bytes=3,
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
        filename="notice.pdf",
        mime_type="application/pdf",
        size_bytes=3,
        sha256_digest="a" * 64,
        expires_at=_NOW + timedelta(hours=24),
    )
    workflow.preview.return_value = ControlledFilePreview(
        candidate=candidate,
        preview_fingerprint=PreviewFingerprint("b" * 64),
        expected_staging_version=ExpectedVersion(2),
        blockers=(),
    )
    workflow.stage.return_value = ControlledFileStagingResult(
        staging_id=_STAGING_ID,
        filename="notice.pdf",
        mime_type="application/pdf",
        size_bytes=3,
        sha256_digest="a" * 64,
        expires_at=_NOW + timedelta(hours=24),
        replayed=False,
    )
    workflow.apply.return_value = ControlledFileApplyReceipt(
        receipt_id=_RECEIPT_ID,
        outcome=ControlledFileApplyOutcome.CREATED,
        readback=readback,
    )
    workflow.readback.return_value = readback
    workflow.list_readbacks.return_value = (readback,)
    workflow.download.return_value = ControlledFileContent(
        object_reference=_FILE_ID,
        filename="notice.pdf",
        content_type="application/pdf",
        content=b"pdf",
        content_sha256="a" * 64,
    )
    workflow.read_receipt.return_value = workflow.apply.return_value
    return workflow


def _client(workflow: Mock) -> TestClient:
    app = FastAPI()
    app.include_router(controlled_files.router)
    app.dependency_overrides[require_persisted_admin] = lambda: AdminPrincipal(
        17, "storage-admin", "檔案管理員", "operator"
    )
    app.dependency_overrides[controlled_files.get_controlled_file_route_workflow] = (
        lambda: workflow
    )
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    return TestClient(app)


def _intent() -> dict[str, object]:
    return {
        "staging_id": _STAGING_ID,
        "owner": "orders",
        "purpose": "order_notice",
        "subject_reference": "ORD-HC019",
        "object_key": "notice",
        "logical_folder": "orders/ORD-HC019",
    }


def test_all_seven_storage_entries_are_active_authenticated_compositions() -> None:
    workflow = _workflow()
    client = _client(workflow)
    preview = client.post(
        "/api/v1/storage/files/preview",
        json=_intent(),
        headers={"X-Correlation-ID": "controlled-files-preview"},
    )
    apply = client.post(
        "/api/v1/storage/files/apply",
        json={**_intent(), "expected_staging_version": 2, "preview_fingerprint": "b" * 64},
        headers={
            "Idempotency-Key": "controlled-file.apply:ord-hc019",
            "X-Correlation-ID": "controlled-files-apply",
        },
    )
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
        headers={"Idempotency-Key": "controlled-file.stage:ord-hc019", "X-Correlation-ID": "controlled-files-stage"},
    )
    listed = client.get("/api/v1/storage/files")
    detail = client.get(f"/api/v1/storage/files/{_FILE_ID}")
    downloaded = client.get(f"/api/v1/storage/files/{_FILE_ID}/download")
    receipt = client.get(f"/api/v1/storage/receipts/{_RECEIPT_ID}")

    assert preview.status_code == apply.status_code == staged.status_code == 200
    assert listed.status_code == detail.status_code == downloaded.status_code == receipt.status_code == 200
    assert preview.json()["data"]["preview_fingerprint"] == "b" * 64
    assert apply.json()["data"]["receipt_id"] == _RECEIPT_ID
    assert detail.json()["data"].get("sha256_digest") is None
    assert receipt.json()["data"]["sha256_digest"] == "a" * 64
    assert downloaded.content == b"pdf"
    assert "attachment" in downloaded.headers["content-disposition"]
    workflow.preview.assert_called_once()
    workflow.apply.assert_called_once()
    assert workflow.apply.call_args.args[0].actor.actor_id == "admin:17"


def test_public_projections_never_expose_storage_locator() -> None:
    workflow = _workflow()
    response = _client(workflow).get("/api/v1/storage/files")

    assert response.status_code == 200
    body = response.text.casefold()
    assert "storage_locator" not in body
    assert "object_reference" not in body
    assert "download_url" not in body
