"""
File: test_contract_external_signing_api.py
Description: 驗證外部簽約 API 的 closed headers、安全 view、persisted actor 與 PDF 回應。
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from api.dependencies.admin_auth import require_persisted_admin
from api.dependencies.contract_external_signing import _preview_token_secret
from api.routes import contract_external_signing as route
from domains.contract_signing.external_signing import (
    ExternalSigningSessionFacts,
    ExternalSigningState,
    StaffSigningReportTarget,
)
from subsystems.access.authentication_session import AdminPrincipal


CASE_NO = "CASE-EXT-1"
UUID = "0123456789abcdef0123456789abcdef"
SESSION_ID = f"ces_{UUID}"
RECEIPT_ID = f"cesr_{UUID}"
KEY = f"contract-external.staff:{UUID}"


class FakeReports:
    def __init__(self) -> None:
        self.command = None

    def apply_manual_staff_report(self, command):
        self.command = command
        return SimpleNamespace(replayed=False)


class FakeControlledFiles:
    def __init__(self) -> None:
        self.command = None

    def stage(self, command):
        self.command = command
        return SimpleNamespace(
            staging_id=f"cfs_{UUID}",
            filename=command.filename,
            mime_type=command.mime_type,
            size_bytes=len(command.content),
            expires_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
        )


class FakeFinalDocuments:
    def preview(self, command):
        return SimpleNamespace(
            preview_token="cp_" + "A" * 43,
            expected_staging_version=1,
            filename="signed.pdf",
            mime_type="application/pdf",
            size_bytes=18,
            blockers=(),
        )

    def readback(self, case_no):
        return SimpleNamespace(
            case_no=case_no,
            final_document_id="cfd_" + UUID,
            file_id="cf_" + UUID,
            version=1,
            filename="signed.pdf",
            mime_type="application/pdf",
            size_bytes=18,
            status="completed",
            applied_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
        )


class FakeApplication:
    def __init__(self) -> None:
        self.reports = FakeReports()
        self.controlled_files = FakeControlledFiles()
        self.final_documents = FakeFinalDocuments()
        self.facts = ExternalSigningSessionFacts(
            SESSION_ID,
            CASE_NO,
            41,
            "a" * 64,
            (StaffSigningReportTarget(71, "staff:9", 81),),
            (),
            "client:3",
            82,
            None,
            False,
            ExternalSigningState.STAFF_REPORTING,
            0,
        )

    def query_case(self, case_no):
        assert case_no == CASE_NO
        return {
            "case_no": case_no,
            "session_id": SESSION_ID,
            "state": "staff_reporting",
            "status_version": 0,
            "matching_plan_id": 41,
            "commitment_id": None,
            "unsigned_document": {
                "document_version_id": 81,
                "filename": "unsigned.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 18,
                "storage_locator": "/private/contracts/unsigned.pdf",
            },
            "staff_targets": [{
                "matching_segment_id": 71,
                "staff_subject_reference": "staff:9",
                "document_version_id": 81,
                "reported": False,
            }],
            "client_target": {
                "client_subject_reference": "client:3",
                "document_version_id": 82,
                "reported": False,
            },
            "document_set_fingerprint": "a" * 64,
        }

    def load_facts(self, case_no):
        return self.facts if case_no == CASE_NO else None

    def read_receipt(self, case_no, receipt_id):
        return {
            "receipt_id": receipt_id,
            "command_type": "record_staff_report",
            "schema_version": "contract-external-signing-receipt.v1",
            "session_id": SESSION_ID,
            "outcome_state": "recorded",
            "resulting_status_version": 1,
            "resulting_state": "staff_reports_complete",
            "matching_segment_id": 71,
            "final_document_id": None,
            "replayed": False,
            "applied_at": datetime(2026, 8, 26, tzinfo=timezone.utc),
            "storage_locator": "/private/receipts/receipt.json",
            "command_fingerprint": "b" * 64,
        }

    def download_unsigned(self, case_no, version, actor, correlation):
        assert actor.actor_id == "admin:7"
        return SimpleNamespace(
            document_version_id=version,
            content=b"%PDF-1.4\n%%EOF",
            filename="unsigned.pdf",
        )


def _client(application: FakeApplication) -> TestClient:
    app = FastAPI()
    app.include_router(route.router)
    principal = AdminPrincipal(7, "admin", "管理員", "system_admin", is_root=True)
    app.dependency_overrides[require_persisted_admin] = lambda: principal
    app.dependency_overrides[route._application] = lambda: application
    return TestClient(app)


def test_query_returns_only_react_contract_fields() -> None:
    response = _client(FakeApplication()).get(
        f"/api/v1/orders/{CASE_NO}/contract-external-signing"
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data) == {
        "case_no", "session_id", "state", "status_version", "matching_plan_id",
        "commitment_id", "unsigned_document", "staff_targets", "client_target",
    }
    serialized = response.text.lower()
    assert all(term not in serialized for term in ("locator", "digest", "fingerprint", "url", "path"))


def test_manual_staff_report_uses_persisted_admin_and_closed_receipt_identity() -> None:
    application = FakeApplication()
    response = _client(application).post(
        f"/api/v1/orders/{CASE_NO}/contract-external-signing/staff-segments/71/completion-reports",
        headers={
            "Idempotency-Key": KEY,
            "X-Receipt-ID": RECEIPT_ID,
            "X-Correlation-ID": "corr-1",
        },
        json={
            "expected_status_version": 0,
            "expected_document_version_id": 81,
            "confirmation_method": "phone",
            "reason": "電話確認完成",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["receipt_id"] == RECEIPT_ID
    serialized = response.text.lower()
    assert all(term not in serialized for term in ("locator", "fingerprint", "digest", "path", "url"))
    assert application.reports.command.actor.actor_id == "admin:7"
    assert application.reports.command.attestation.evidence_reference == f"manual-evidence:{RECEIPT_ID}"


def test_receipt_identity_mismatch_fails_before_workflow() -> None:
    application = FakeApplication()
    response = _client(application).post(
        f"/api/v1/orders/{CASE_NO}/contract-external-signing/staff-segments/71/completion-reports",
        headers={
            "Idempotency-Key": KEY,
            "X-Receipt-ID": "cesr_ffffffffffffffffffffffffffffffff",
            "X-Correlation-ID": "corr-2",
        },
        json={
            "expected_status_version": 0,
            "expected_document_version_id": 81,
            "confirmation_method": "paper",
            "reason": "紙本確認",
        },
    )

    assert response.status_code == 422
    assert application.reports.command is None


def test_unsigned_download_is_pdf_and_no_store() -> None:
    response = _client(FakeApplication()).get(
        f"/api/v1/orders/{CASE_NO}/contract-external-signing/unsigned-pdf",
        headers={
            "X-Expected-Document-Version": "81",
            "X-Correlation-ID": "corr-download",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-contract-document-version"] == "81"
    assert response.headers["x-correlation-id"] == "corr-download"


@pytest.mark.parametrize(
    "preview_token",
    [
        "cp_" + "A" * 42,
        "cp_" + "A" * 44,
        "cp_" + "A" * 42 + "+",
        "cp_" + "A" * 42 + "/",
    ],
)
def test_final_apply_body_rejects_noncanonical_preview_tokens(preview_token: str) -> None:
    with pytest.raises(ValidationError):
        route.FinalApplyBody.model_validate({
            "staging_id": f"cfs_{UUID}",
            "expected_status_version": 0,
            "expected_staging_version": 1,
            "preview_token": preview_token,
        })


@pytest.mark.parametrize(
    ("command_type", "outcome_state", "resulting_state", "matching_segment_id", "final_document_id"),
    [
        ("record_staff_report", "completed", "staff_reports_complete", 71, None),
        ("record_client_report", "recorded", "staff_reports_complete", None, None),
        ("apply_final_signed_contract", "recorded", "completed", None, f"cfd_{UUID}"),
    ],
)
def test_public_receipt_rejects_impossible_command_state_unions(
    command_type: str,
    outcome_state: str,
    resulting_state: str,
    matching_segment_id: int | None,
    final_document_id: str | None,
) -> None:
    value = FakeApplication().read_receipt(CASE_NO, RECEIPT_ID)
    value.update({
        "command_type": command_type,
        "outcome_state": outcome_state,
        "resulting_state": resulting_state,
        "matching_segment_id": matching_segment_id,
        "final_document_id": final_document_id,
    })

    with pytest.raises(ValidationError):
        route._public_receipt(value)


@pytest.mark.parametrize(
    ("command_type", "outcome_state", "resulting_state", "matching_segment_id", "final_document_id"),
    [
        ("record_staff_report", "recorded", "staff_reports_complete", 71, None),
        ("record_client_report", "recorded", "client_reported_final_pdf_pending", None, None),
        ("apply_final_signed_contract", "completed", "completed", None, f"cfd_{UUID}"),
    ],
)
def test_public_receipt_accepts_every_legitimate_command_state_union(
    command_type: str,
    outcome_state: str,
    resulting_state: str,
    matching_segment_id: int | None,
    final_document_id: str | None,
) -> None:
    value = FakeApplication().read_receipt(CASE_NO, RECEIPT_ID)
    value.update({
        "command_type": command_type,
        "outcome_state": outcome_state,
        "resulting_state": resulting_state,
        "matching_segment_id": matching_segment_id,
        "final_document_id": final_document_id,
    })

    assert route._public_receipt(value)["command_type"] == command_type


def test_final_staging_and_preview_hide_controlled_file_internals() -> None:
    application = FakeApplication()
    client = _client(application)
    staging = client.post(
        f"/api/v1/orders/{CASE_NO}/contract-external-signing/final-document/staging",
        headers={"Idempotency-Key": "contract-final.stage:" + UUID, "X-Correlation-ID": "corr-stage"},
        files={"document": ("signed.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    )
    preview = client.post(
        f"/api/v1/orders/{CASE_NO}/contract-external-signing/final-document/preview",
        json={"staging_id": f"cfs_{UUID}", "expected_status_version": 0},
    )

    assert staging.status_code == 200
    assert set(staging.json()["data"]) == {
        "staging_id", "filename", "mime_type", "size_bytes", "expires_at",
    }
    assert application.controlled_files.command.actor.actor_id == "admin:7"
    assert preview.status_code == 200
    assert set(preview.json()["data"]) == {
        "preview_token", "staging_id", "expected_staging_version", "filename",
        "mime_type", "size_bytes", "blockers", "can_apply",
    }


def test_final_readback_uses_only_opaque_identities() -> None:
    response = _client(FakeApplication()).get(
        f"/api/v1/orders/{CASE_NO}/contract-external-signing/final-document/readback"
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data) == {
        "case_no", "session_id", "final_document_id", "controlled_file_id",
        "version_number", "filename", "mime_type", "size_bytes", "status",
        "integrity_verified", "applied_at",
    }
    assert data["integrity_verified"] is True


def test_production_requires_configured_preview_secret(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("CONTRACT_FINAL_PREVIEW_TOKEN_SECRET", raising=False)

    try:
        _preview_token_secret()
    except RuntimeError as error:
        assert "required" in str(error)
    else:
        raise AssertionError("production must fail closed without preview token secret")
