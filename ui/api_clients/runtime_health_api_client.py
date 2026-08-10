"""Typed Streamlit client for persisted runtime health, alert targets, and audit."""

from __future__ import annotations

from typing import Any

from ui.api_clients.line_api_client import LineAdminApiClient


class RuntimeHealthApiClient:
    def __init__(self, transport: LineAdminApiClient) -> None:
        self._transport = transport

    def health_status(self, token: str | None) -> list[dict[str, Any]]:
        return self._transport.request("GET", "/api/v1/runtime/health-status", token=token)

    def health_events(self, token: str | None, limit: int = 100) -> list[dict[str, Any]]:
        return self._transport.request(
            "GET", "/api/v1/runtime/health-events", token=token, params={"limit": limit}
        )

    def alert_targets(self, token: str | None) -> list[dict[str, Any]]:
        return self._transport.request("GET", "/api/v1/runtime/line-alert-targets", token=token)

    def add_admin_target(
        self,
        token: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._transport.request(
            "POST", "/api/v1/runtime/line-alert-targets/admin", token=token, json=payload
        )

    def admin_alert_candidates(self, token: str | None) -> list[dict[str, Any]]:
        return self._transport.request(
            "GET", "/api/v1/runtime/line-alert-targets/admin-candidates", token=token
        )

    def set_target_enabled(
        self,
        token: str | None,
        target_id: int,
        enabled: bool,
    ) -> dict[str, Any]:
        return self._transport.request(
            "PATCH",
            f"/api/v1/runtime/line-alert-targets/{target_id}",
            token=token,
            json={"enabled": enabled},
        )

    def audit_records(
        self,
        token: str | None,
        *,
        action_prefix: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        page = self._transport.request(
            "GET",
            "/api/v1/admin/audits",
            token=token,
            params={"action_prefix": action_prefix, "page_size": limit},
        )
        return list(page["items"])


__all__ = ["RuntimeHealthApiClient"]
