"""Server-side client for authenticated LINE administration APIs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class LineAdminApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class LineAdminApiClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
        self.internal_api_key = os.getenv("INTERNAL_API_KEY", "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.internal_api_key)

    @property
    def admin_auth_bypassed(self) -> bool:
        app_env = os.getenv("APP_ENV", "development").strip().lower()
        enabled = os.getenv("ENABLE_ADMIN_AUTH", "true").strip().lower()
        return app_env in {"development", "dev", "local", "test"} and enabled in {
            "0",
            "false",
            "no",
            "off",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        headers = {"X-Internal-API-Key": self.internal_api_key}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if extra_headers:
            headers.update(extra_headers)
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                json=json,
                timeout=8,
            )
        except requests.RequestException as exc:
            raise LineAdminApiError(f"無法連線到 FastAPI：{exc}") from exc

        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not response.ok:
            detail = payload.get("detail") if isinstance(payload, dict) else response.text
            raise LineAdminApiError(str(detail or "API 請求失敗"), status_code=response.status_code)
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    def login(self, username: str, password: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/admin/auth/login",
            json={"username": username, "password": password},
        )

    def me(self, token: str | None) -> dict[str, Any]:
        return self._request("GET", "/api/v1/admin/auth/me", token=token)

    def refresh(self, token: str) -> dict[str, Any]:
        return self._request("POST", "/api/v1/admin/auth/refresh", token=token)

    def logout(self, token: str) -> None:
        self._request("POST", "/api/v1/admin/auth/logout", token=token)

    def health(self, token: str | None) -> dict[str, Any]:
        return self._request("GET", "/api/v1/line/admin/health", token=token)

    def capabilities(self, token: str | None) -> dict[str, Any]:
        return self._request("GET", "/api/v1/line/admin/capabilities", token=token)

    def message_template_state(self, token: str | None) -> dict[str, Any]:
        return self._request("GET", "/api/config/message-templates/state", token=token)

    def create_message_template(
        self,
        token: str | None,
        payload: dict[str, Any],
        *,
        revision: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/config/message-templates",
            token=token,
            json=payload,
            extra_headers={"If-Match": revision},
        )

    def update_message_template(
        self,
        token: str | None,
        template_id: str,
        payload: dict[str, Any],
        *,
        revision: str,
    ) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"/api/config/message-templates/{template_id}",
            token=token,
            json=payload,
            extra_headers={"If-Match": revision},
        )

    def delete_message_template(
        self,
        token: str | None,
        template_id: str,
        *,
        revision: str,
    ) -> None:
        self._request(
            "DELETE",
            f"/api/config/message-templates/{template_id}",
            token=token,
            extra_headers={"If-Match": revision},
        )

    def preview_message_template(
        self,
        token: str | None,
        template: dict[str, Any],
        variables: dict[str, str],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/config/message-templates/preview",
            token=token,
            json={"template": template, "variables": variables},
        )
