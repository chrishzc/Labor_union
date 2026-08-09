"""
================================================================================
檔案名稱: ui/api_clients/line_api_client.py
功能說明: Streamlit 專用 LINE API Client，統一帶入內部金鑰與管理員 Session 呼叫 FastAPI
================================================================================
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from ui.pages.shared import resolve_api_base_url, resolve_internal_api_key


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


_STATUS_ERRORS = {
    401: ("unauthorized", "admin_session_invalid", "登入已失效，請重新登入。", False),
    403: ("forbidden", "admin_capability_denied", "目前帳號沒有執行此操作的權限。", False),
    409: ("conflict", "resource_version_conflict", "資料已更新，請重新載入後再操作。", False),
    503: ("unavailable", "service_temporarily_unavailable", "服務暫時無法使用，請稍後重試。", True),
}


class LineAdminApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        category: str = "internal",
        code: str = "line_admin_request_failed",
        correlation_id: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.category = category
        self.code = code
        self.correlation_id = correlation_id
        self.retryable = retryable


def _response_error(status_code: int, payload: Any, response_text: str) -> LineAdminApiError:
    category, fallback_code, fallback_message, retryable = _STATUS_ERRORS.get(
        status_code,
        ("validation" if status_code == 422 else "internal", "line_admin_request_failed", "API 請求失敗", status_code >= 500),
    )
    detail = payload.get("detail") if isinstance(payload, dict) else None
    detail_object = detail if isinstance(detail, dict) else {}
    message = fallback_message if status_code in _STATUS_ERRORS else _detail_message(detail, response_text)
    return LineAdminApiError(
        message,
        status_code=status_code,
        category=category,
        code=str(detail_object.get("code") or fallback_code),
        correlation_id=_correlation_id(payload, detail_object),
        retryable=bool(detail_object.get("retryable", retryable)),
    )


def _detail_message(detail: Any, response_text: str) -> str:
    if isinstance(detail, dict):
        return str(detail.get("message") or detail.get("code") or "API 請求失敗")
    return str(detail or response_text or "API 請求失敗")


def _correlation_id(payload: Any, detail: dict[str, Any]) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = detail.get("correlation_id") or payload.get("correlation_id")
    return str(value) if value else None


class LineAdminApiClient:
    def __init__(self) -> None:
        pass

    @property
    def configured(self) -> bool:
        try:
            return bool(resolve_internal_api_key())
        except RuntimeError:
            return False

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

    def _request_headers(self, token: str | None) -> dict[str, str]:
        headers = {"X-Internal-API-Key": resolve_internal_api_key()}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        headers = self._request_headers(token)
        if extra_headers:
            headers.update(extra_headers)
        try:
            response = requests.request(
                method,
                f"{resolve_api_base_url()}{path}",
                headers=headers,
                json=json,
                params=params,
                timeout=8,
            )
        except requests.RequestException as exc:
            raise LineAdminApiError(
                f"無法連線到 FastAPI：{exc}",
                category="unavailable",
                code="line_admin_transport_unavailable",
                retryable=True,
            ) from exc

        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not response.ok:
            raise _response_error(response.status_code, payload, response.text)
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Expose the shared authenticated transport to bounded domain clients."""
        return self._request(
            method,
            path,
            token=token,
            json=json,
            extra_headers=extra_headers,
            params=params,
        )

    def _request_bytes(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json: dict[str, Any] | None = None,
    ) -> bytes:
        headers = self._request_headers(token)
        try:
            response = requests.request(
                method,
                f"{resolve_api_base_url()}{path}",
                headers=headers,
                json=json,
                timeout=15,
            )
        except requests.RequestException as exc:
            raise LineAdminApiError(
                f"無法連線到 FastAPI：{exc}",
                category="unavailable",
                code="line_admin_transport_unavailable",
                retryable=True,
            ) from exc
        if not response.ok:
            try:
                payload = response.json()
            except ValueError:
                payload = None
            raise _response_error(response.status_code, payload, response.text)
        return response.content

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

    def message_schedule_state(self, token: str | None) -> dict[str, Any]:
        return self._request("GET", "/api/config/message-schedules/state", token=token)

    def update_message_schedules(
        self,
        token: str | None,
        payload: dict[str, Any],
        *,
        revision: str,
    ) -> dict[str, Any]:
        return self._request(
            "PUT",
            "/api/config/message-schedules",
            token=token,
            json=payload,
            extra_headers={"If-Match": revision},
        )

    def line_task_summary(self, token: str | None) -> dict[str, Any]:
        return self._request("GET", "/api/v1/line/tasks/summary", token=token)

    def line_tasks(
        self,
        token: str | None,
        *,
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/line/tasks",
            token=token,
            params={key: value for key, value in filters.items() if value not in {None, ""}},
        )

    def line_task_detail(self, token: str | None, task_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/line/tasks/{task_id}", token=token)

    def line_task_action(
        self,
        token: str | None,
        task_id: int,
        action: str,
        *,
        reason: str = "",
        idempotency_key: str = "",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        if action not in {"cancel", "run-now", "retry"}:
            raise ValueError("不支援的 LINE 任務操作")
        return self._request(
            "POST",
            f"/api/v1/line/tasks/{task_id}/{action}",
            token=token,
            json={
                "reason": reason,
                "idempotency_key": idempotency_key,
                "correlation_id": correlation_id,
            },
        )

    def line_menu_state(self, token: str | None) -> dict[str, Any]:
        return self._request("GET", "/api/config/line-menus/state", token=token)

    def update_line_menus(
        self,
        token: str | None,
        payload: dict[str, Any],
        *,
        revision: str,
    ) -> dict[str, Any]:
        return self._request(
            "PUT",
            "/api/config/line-menus",
            token=token,
            json=payload,
            extra_headers={"If-Match": revision},
        )

    def preview_line_menu(self, token: str | None, menu: dict[str, Any]) -> bytes:
        return self._request_bytes(
            "POST",
            "/api/v1/line/rich-menus/preview",
            token=token,
            json=menu,
        )

    def upload_line_menu_image(
        self,
        token: str | None,
        menu_id: str,
        *,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> dict[str, Any]:
        headers = self._request_headers(token)
        try:
            response = requests.post(
                f"{resolve_api_base_url()}/api/v1/line/rich-menus/{menu_id}/images",
                headers=headers,
                files={"image": (filename, content, content_type)},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise LineAdminApiError(
                f"無法上傳圖片：{exc}",
                category="unavailable",
                code="line_menu_upload_unavailable",
                retryable=True,
            ) from exc
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not response.ok:
            raise _response_error(response.status_code, payload, response.text)
        return payload["data"]

    def publish_line_menu(
        self,
        token: str | None,
        menu_id: str,
        *,
        preview_id: int,
        reason: str = "",
        idempotency_key: str = "",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/line/rich-menus/{menu_id}/publish",
            token=token,
            json={
                "preview_id": preview_id,
                "reason": reason,
                "idempotency_key": idempotency_key,
                "correlation_id": correlation_id,
            },
        )

    def create_line_menu_publish_preview(
        self,
        token: str | None,
        menu_id: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/line/rich-menus/{menu_id}/publish-preview",
            token=token,
        )

    def line_menu_publications(
        self,
        token: str | None,
        *,
        menu_id: str | None = None,
        status: str | None = None,
        page: int = 1,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/line/rich-menus/publications",
            token=token,
            params={
                key: value
                for key, value in {
                    "menu_id": menu_id,
                    "status": status,
                    "page": page,
                    "page_size": 20,
                }.items()
                if value not in {None, ""}
            },
        )

    def retry_line_menu_publication(
        self,
        token: str | None,
        publication_id: int,
        *,
        reason: str = "",
        idempotency_key: str = "",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/line/rich-menus/publications/{publication_id}/retry",
            token=token,
            json={
                "reason": reason,
                "idempotency_key": idempotency_key,
                "correlation_id": correlation_id,
            },
        )

    def liff_config_state(self, token: str | None) -> dict[str, Any]:
        return self._request("GET", "/api/config/liff/state", token=token)

    def validate_liff_config(
        self,
        token: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/config/liff/validate",
            token=token,
            json=payload,
        )

    def update_liff_config(
        self,
        token: str | None,
        payload: dict[str, Any],
        *,
        revision: str,
    ) -> dict[str, Any]:
        return self._request(
            "PUT",
            "/api/config/liff",
            token=token,
            json=payload,
            extra_headers={"If-Match": revision},
        )

    def liff_config_history(self, token: str | None) -> dict[str, Any]:
        return self._request("GET", "/api/config/liff/history", token=token)

    def rollback_liff_config(
        self,
        token: str | None,
        revision_to_restore: str,
        *,
        current_revision: str,
        reason: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/config/liff/rollback/{revision_to_restore}",
            token=token,
            json={"reason": reason},
            extra_headers={"If-Match": current_revision},
        )

    def line_review_summary(self, token: str | None) -> dict[str, Any]:
        return self._request("GET", "/api/v1/line/identity/reviews/summary", token=token)

    def line_reviews(
        self,
        token: str | None,
        *,
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/line/identity/reviews",
            token=token,
            params={
                key: value
                for key, value in filters.items()
                if value not in {None, ""}
            },
        )

    def line_review_detail(
        self,
        token: str | None,
        request_id: int,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/api/v1/line/identity/reviews/{request_id}",
            token=token,
        )

    def line_review_action(
        self,
        token: str | None,
        request_id: int,
        action: str,
        *,
        reason: str,
        expected_version: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if action not in {"approve", "reject"}:
            raise ValueError("不支援的人工審查操作")
        return self._request(
            "POST",
            f"/api/v1/line/identity/reviews/{request_id}/{action}",
            token=token,
            json={
                "expected_version": expected_version,
                "idempotency_key": idempotency_key,
                "reason": reason,
            },
        )

    def order_groups(
        self,
        token: str | None,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/line/order-groups",
            token=token,
            params={"status": status, "limit": limit},
        )

    def order_group_events(
        self,
        token: str | None,
        case_no: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            f"/api/v1/line/order-groups/{case_no}/events",
            token=token,
            params={"limit": limit},
        )

    def customer_service_config(self, token: str | None) -> dict[str, Any]:
        return self._request("GET", "/api/config/customer-service", token=token)

    def update_customer_service_config(
        self,
        token: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "PUT", "/api/config/customer-service", token=token, json=payload
        )
