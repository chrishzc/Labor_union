"""Typed Streamlit client for the Global Operations status view."""

from __future__ import annotations

from pydantic import ValidationError

from api.schemas.system_status import PerformanceSnapshotResponse
from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError


class SystemStatusApiError(RuntimeError):
    """The system-status boundary returned an unavailable or invalid response."""


class SystemStatusApiClient:
    def __init__(self, transport: LineAdminApiClient) -> None:
        self._transport = transport

    def performance_snapshot(
        self,
        token: str | None,
    ) -> PerformanceSnapshotResponse:
        try:
            payload = self._transport.request(
                "GET",
                "/api/v1/system/status/performance-snapshot",
                token=token,
            )
            return PerformanceSnapshotResponse.model_validate(payload)
        except (LineAdminApiError, ValidationError, TypeError, ValueError) as error:
            raise SystemStatusApiError("無法讀取系統效能摘要。") from error


__all__ = ["SystemStatusApiClient", "SystemStatusApiError"]
