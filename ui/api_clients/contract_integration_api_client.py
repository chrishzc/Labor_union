"""Typed Streamlit client for verified external-contract evidence administration."""

from __future__ import annotations

from typing import Any

from ui.api_clients.line_api_client import LineAdminApiClient


class ContractIntegrationApiClient:
    def __init__(self, transport: LineAdminApiClient) -> None:
        self._transport = transport

    def evidence(
        self,
        token: str | None,
        *,
        provider_contract_id: str | None = None,
        processing_status: str | None = None,
        cursor: int | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._transport.request(
            "GET",
            "/api/v1/contract-integration/evidence",
            token=token,
            params={
                "provider_contract_id": provider_contract_id,
                "processing_status": processing_status,
                "cursor": cursor,
                "limit": limit,
            },
        )

    def map_evidence(
        self,
        token: str | None,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        return self._transport.request(
            "POST",
            "/api/v1/contract-integration/mappings",
            token=token,
            json=payload,
            extra_headers={
                "Idempotency-Key": idempotency_key,
                "X-Correlation-ID": correlation_id,
            },
        )


__all__ = ["ContractIntegrationApiClient"]
