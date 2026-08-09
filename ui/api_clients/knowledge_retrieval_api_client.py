"""Typed Streamlit client for reviewed knowledge, indexes, jobs, and cited answers."""

from __future__ import annotations

from typing import Any

from ui.api_clients.line_api_client import LineAdminApiClient


class KnowledgeRetrievalApiClient:
    def __init__(self, transport: LineAdminApiClient) -> None:
        self._transport = transport

    def items(
        self,
        token: str | None,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._get(
            token,
            "/api/v1/knowledge/items",
            {"lifecycle_status": status, "limit": limit},
        )

    def item(self, token: str | None, item_id: int) -> dict[str, Any]:
        return self._get(token, f"/api/v1/knowledge/items/{item_id}")

    def jobs(
        self,
        token: str | None,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._get(
            token,
            "/api/v1/knowledge/jobs",
            {"processing_status": status, "limit": limit},
        )

    def indexes(self, token: str | None, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._get(token, "/api/v1/knowledge/indexes", {"limit": limit})

    def answer(self, token: str | None, request_id: int) -> dict[str, Any]:
        return self._get(token, f"/api/v1/knowledge/questions/{request_id}")

    def ingest(self, token: str | None, payload: dict[str, Any], *, headers: dict[str, str]):
        return self._post(token, "/api/v1/knowledge/items", payload, headers)

    def transition(
        self,
        token: str | None,
        item_id: int,
        action: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        if action not in {"review", "publish", "retire"}:
            raise ValueError("不支援的知識狀態操作")
        return self._post(token, f"/api/v1/knowledge/items/{item_id}/{action}", payload, headers)

    def build_index(self, token: str | None, *, headers: dict[str, str]) -> dict[str, Any]:
        return self._post(token, "/api/v1/knowledge/indexes", {}, headers)

    def ask(
        self,
        token: str | None,
        question: str,
        *,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        return self._post(token, "/api/v1/knowledge/questions", {"question": question}, headers)

    def retry_job(
        self,
        token: str | None,
        job_id: int,
        *,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        return self._post(token, f"/api/v1/knowledge/jobs/{job_id}/retry", {}, headers)

    def _get(
        self,
        token: str | None,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        return self._transport.request("GET", path, token=token, params=params)

    def _post(
        self,
        token: str | None,
        path: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> Any:
        return self._transport.request(
            "POST", path, token=token, json=payload, extra_headers=headers
        )


__all__ = ["KnowledgeRetrievalApiClient"]
