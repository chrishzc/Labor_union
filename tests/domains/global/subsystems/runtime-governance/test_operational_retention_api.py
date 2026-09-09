"""Typed root-only API composition for operational retention."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_root
from api.routes import operational_retention
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.runtime_governance.operational_retention import (
    POLICY_REVISION,
    RetentionPreview,
    RetentionReceipt,
    RetentionSourceSnapshot,
)


NOW = datetime(2026, 9, 9, 8, 0, tzinfo=UTC)


def _application() -> Mock:
    app = Mock()
    app.dashboard.return_value = (
        RetentionSourceSnapshot(
            "knowledge-observations",
            "AI 客服技術觀測與舊索引",
            "database",
            "eligible",
            10_000,
            3,
            1,
            NOW,
            500,
            20_000,
            15_000,
            "normal",
        ),
    )
    app.preview.return_value = RetentionPreview(
        POLICY_REVISION,
        "knowledge-observations",
        "expired",
        "到期清理",
        NOW,
        NOW,
        250,
        1,
        500,
        10_000,
        None,
        PreviewFingerprint("a" * 64),
        (),
    )
    app.apply.return_value = RetentionReceipt(
        "retention:test",
        "knowledge-observations",
        "expired",
        POLICY_REVISION,
        "a" * 64,
        "completed",
        1,
        1,
        0,
        500,
        NOW,
        NOW,
        "retention:test",
        None,
    )
    return app


def _client(application: Mock) -> TestClient:
    app = FastAPI()
    app.include_router(operational_retention.router)
    app.dependency_overrides[require_root] = lambda: AdminPrincipal(
        7, "root", "Root", "system_admin", is_root=True
    )
    app.dependency_overrides[operational_retention.operational_retention_application] = lambda: application
    return TestClient(app)


def test_query_and_preview_are_typed_and_preview_does_not_call_apply() -> None:
    application = _application()
    client = _client(application)

    dashboard = client.get("/api/v1/system/storage-retention")
    preview = client.post(
        "/api/v1/system/storage-retention/preview",
        json={
            "source_id": "knowledge-observations",
            "mode": "expired",
            "reason": "到期清理",
            "batch_size": 250,
        },
    )

    assert dashboard.status_code == 200
    assert dashboard.json()["data"]["retention_days"] == 30
    assert preview.status_code == 200
    assert preview.json()["data"]["preview_fingerprint"] == "a" * 64
    application.apply.assert_not_called()


def test_apply_maps_frozen_preview_and_returns_terminal_readback() -> None:
    application = _application()
    client = _client(application)

    response = client.post(
        "/api/v1/system/storage-retention/apply",
        json={
            "source_id": "knowledge-observations",
            "mode": "expired",
            "reason": "到期清理",
            "batch_size": 250,
            "previewed_at_utc": NOW.isoformat(),
            "preview_fingerprint": "a" * 64,
            "idempotency_key": "retention:test",
            "correlation_id": "retention:test",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["outcome"] == "completed"
    assert response.json()["data"]["deleted_count"] == 1
    assert application.apply.call_args.kwargs["actor_id"] == "admin:7"
