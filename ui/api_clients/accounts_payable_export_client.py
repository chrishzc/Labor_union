"""Framework-neutral client for Accounts Payable export."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import requests

from ui.pages.shared import build_admin_headers, resolve_api_base_url


@dataclass(frozen=True)
class AccountsPayableExportArtifact:
    workbook_bytes: bytes
    filename: str


class AccountsPayableExportApiClient:
    def __init__(
        self,
        *,
        timeout: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = resolve_api_base_url().rstrip("/")
        self._headers = build_admin_headers()
        self._timeout = timeout
        self._session = session or requests.Session()

    def query(self, target_month: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/api/v1/finance-reports/accounts-payable?target_month={target_month}",
        )

    def export(self, target_month: str) -> AccountsPayableExportArtifact:
        response = self._session.request(
            "GET",
            f"{self._base_url}/api/v1/finance-reports/accounts-payable/export?target_month={target_month}",
            headers=self._headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        
        # Extract filename from Content-Disposition if present, else fallback
        cd = response.headers.get("Content-Disposition", "")
        filename = f"accounts_payable_{target_month}.xlsx"
        if "filename=" in cd:
            import re
            match = re.search(r'filename="?([^"]+)"?', cd)
            if match:
                filename = match.group(1)
        
        return AccountsPayableExportArtifact(
            workbook_bytes=response.content,
            filename=filename,
        )

    def query_archive(self, year: int) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/api/v1/finance-reports/accounts-payable/archive?year={year}",
        )

    def _request(
        self,
        method: str,
        path: str,
    ) -> dict[str, Any]:
        response = self._session.request(
            method,
            f"{self._base_url}{path}",
            headers=self._headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("success"):
            raise ValueError("API response status was not successful")
        return payload.get("data") or {}

__all__ = ["AccountsPayableExportApiClient", "AccountsPayableExportArtifact"]
