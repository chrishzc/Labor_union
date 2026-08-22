from __future__ import annotations

import pytest

from infrastructure.mysql import mysql_adapter
from ui.pages import shared


def test_ui_oidc_uses_serverless_header_without_replacing_admin_session(monkeypatch):
    monkeypatch.setenv("UI_API_AUTH_MODE", "google_oidc")
    monkeypatch.setenv("UI_API_OIDC_AUDIENCE", "https://api.example.run.app")
    monkeypatch.setattr(shared, "fetch_id_token", lambda request, audience: "google-token")
    monkeypatch.setattr(shared, "resolve_admin_access_token", lambda: "admin-session")

    assert shared.build_admin_headers() == {
        "X-Serverless-Authorization": "Bearer google-token",
        "Authorization": "Bearer admin-session",
    }


def test_ui_oidc_fails_closed_without_audience(monkeypatch):
    monkeypatch.setenv("UI_API_AUTH_MODE", "google_oidc")
    monkeypatch.delenv("UI_API_OIDC_AUDIENCE", raising=False)

    with pytest.raises(RuntimeError, match="UI_API_OIDC_AUDIENCE"):
        shared.build_cloud_run_invocation_headers()


def test_development_bridge_profile_is_forbidden_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "development_gce_iap_reverse_ssh")

    with pytest.raises(RuntimeError, match="forbidden in production"):
        mysql_adapter._database_config_from_environment()


def test_mysql_mtls_requires_complete_material(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("DB_SSL_MODE", "verify_identity")
    monkeypatch.setenv("DB_SSL_CA", "ca.pem")
    monkeypatch.delenv("DB_SSL_CERT", raising=False)
    monkeypatch.delenv("DB_SSL_KEY", raising=False)

    with pytest.raises(RuntimeError, match="MySQL mTLS requires"):
        mysql_adapter._database_config_from_environment()
