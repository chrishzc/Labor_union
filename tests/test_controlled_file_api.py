"""Verify the legacy controlled-files public entries fail closed at HTTP 410."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_persisted_admin
from api.routes import controlled_files
from subsystems.access.authentication_session import AdminPrincipal


_REPLACEMENT_IDENTIFIER = (
    "subsystems.controlled_files.reference_finalize.ControlledFileReferenceService"
)
_REMOVAL_GATE = "blocked_media_successor_schema_and_runtime_gate"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(controlled_files.router)
    app.dependency_overrides[require_persisted_admin] = lambda: AdminPrincipal(
        17, "storage-admin", "檔案管理員", "operator"
    )
    return TestClient(app)


@pytest.mark.parametrize(
    ("method", "path", "route_identity"),
    [
        ("post", "/api/v1/storage/staging", "POST /api/v1/storage/staging"),
        (
            "post",
            "/api/v1/storage/files/preview",
            "POST /api/v1/storage/files/preview",
        ),
        (
            "post",
            "/api/v1/storage/files/apply",
            "POST /api/v1/storage/files/apply",
        ),
        ("get", "/api/v1/storage/files", "GET /api/v1/storage/files"),
        (
            "get",
            "/api/v1/storage/files/cf_any-value",
            "GET /api/v1/storage/files/{file_id}",
        ),
        (
            "get",
            "/api/v1/storage/files/cf_any-value/download",
            "GET /api/v1/storage/files/{file_id}/download",
        ),
        (
            "get",
            "/api/v1/storage/receipts/cfr_any-value",
            "GET /api/v1/storage/receipts/{receipt_id}",
        ),
    ],
)
def test_legacy_controlled_file_entry_is_stable_typed_gone(
    method: str, path: str, route_identity: str
) -> None:
    response = getattr(_client(), method)(path)

    assert response.status_code == 410
    error = response.json()["detail"]["error"]
    assert error["category"] == "not_found"
    assert error["code"] == "controlled_file_public_route_retired"
    assert error["domain_blockers"] == [
        f"replacement_identifier:{_REPLACEMENT_IDENTIFIER}",
        f"removal_gate:{_REMOVAL_GATE}",
    ]
    assert error["retryable"] is False
    assert error["correlation_id"] == f"controlled-files-retired:{route_identity}"


def test_retired_controlled_file_routes_do_not_keep_workflow_or_storage_access() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "api" / "routes" / "controlled_files.py"
    ).read_text(encoding="utf-8")

    assert "get_controlled_file_workflow" not in source
    assert "ControlledFileWorkflow" not in source
    assert ".commit(" not in source
    assert ".rollback(" not in source
    assert "storage_locator" not in source
