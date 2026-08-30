"""Task 97 regression for the retired anomaly necessity migration entries."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_persisted_admin
from api.main import app
from subsystems.access.authentication_session import AdminPrincipal


_PREFIX = "/api/v1/admin/anomaly-necessity-migration"
_ERROR_CODE = "anomaly_necessity_migration_retired"


def _principal() -> AdminPrincipal:
    return AdminPrincipal(
        9,
        "migration-operator",
        "Migration Operator",
        "system_admin",
        capabilities=frozenset({"system.administration"}),
    )


def test_all_legacy_entries_are_stable_typed_410_without_writer_composition() -> None:
    app.dependency_overrides[require_persisted_admin] = _principal
    try:
        client = TestClient(app)
        responses = (
            (
                client.get(f"{_PREFIX}/alerts"),
                "replacement_identifier:GET /api/v1/anomalies",
            ),
            (
                client.post(
                    f"{_PREFIX}/alerts/legacy-fingerprint/preview",
                    json={"ignored": "legacy payload"},
                ),
                "replacement_identifier:owner_action_from:GET "
                "/api/v1/anomalies/{issue_key}/actions/{action_key}",
            ),
            (
                client.post(
                    f"{_PREFIX}/alerts/legacy-fingerprint/apply",
                    json={"ignored": "legacy payload"},
                ),
                "replacement_identifier:owner_action_from:GET "
                "/api/v1/anomalies/{issue_key}/actions/{action_key}",
            ),
        )
    finally:
        app.dependency_overrides.pop(require_persisted_admin, None)

    for response, replacement in responses:
        assert response.status_code == 410
        error = response.json()["detail"]["error"]
        assert error["code"] == _ERROR_CODE
        assert error["category"] == "domain_blocked"
        assert error["retryable"] is False
        assert replacement in error["domain_blockers"]
        assert "removal_gate:blocked_external_caller_evidence" in error[
            "domain_blockers"
        ]


def test_retired_entries_remain_runtime_registered() -> None:
    schema = app.openapi()
    paths = schema["paths"]
    assert f"{_PREFIX}/alerts" in paths
    assert f"{_PREFIX}/alerts/{{alert_fingerprint}}/preview" in paths
    assert f"{_PREFIX}/alerts/{{alert_fingerprint}}/apply" in paths
