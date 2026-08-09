"""Stage 10 acceptance for canonical UI callers and retired legacy writers."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[3]


def test_canonical_mode_retires_legacy_identity_and_review_routes(
    monkeypatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LINE_WEBHOOK_RUNTIME_MODE", "canonical")
    monkeypatch.setenv("LINE_WORKER_RUNTIME_MODE", "canonical")
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("PRESERVE_DATA_REHEARSAL_READ_ONLY", "true")
    from api.main import app

    with TestClient(app) as client:
        legacy_identity = client.get("/api/line/config")
        legacy_review = client.get("/api/v1/line/review-requests")

    assert legacy_identity.status_code == 410
    assert legacy_identity.json()["detail"]["replacement"].startswith("/api/v1/line/identity")
    assert legacy_review.status_code == 410
    assert legacy_review.json()["detail"]["code"] == "legacy_line_review_route_retired"


def test_line_management_ui_uses_only_canonical_identity_review_routes() -> None:
    client_source = (ROOT / "ui/api_clients/line_api_client.py").read_text(encoding="utf-8")
    component_source = (ROOT / "ui/components/line_review_manager.py").read_text(
        encoding="utf-8"
    )

    assert "/api/v1/line/identity/reviews" in client_source
    assert "/api/v1/line/review-requests" not in client_source
    assert "expected_version" in client_source
    assert "idempotency_key" in client_source
    assert "operation_headers" in component_source


def test_canonical_worker_entrypoint_does_not_import_legacy_worker_eagerly() -> None:
    source = (ROOT / "scripts/run_line_worker.py").read_text(encoding="utf-8")
    import_prefix = source.split("def main", 1)[0]

    assert "from line.worker import" not in import_prefix
