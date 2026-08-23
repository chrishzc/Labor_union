"""
File: runtime_health_api_client.py
Description: 驗證 runtime health 與 LINE 告警對象的 typed API payload。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError


class _ClosedView(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeHealthRecordView(_ClosedView):
    check_name: str
    component: str
    status: str
    raw_status: str
    message: str
    response_ms: int | None
    consecutive_failures: int
    consecutive_successes: int
    checked_at: datetime
    status_changed_at: datetime
    details: dict[str, object] | None = None


class RuntimeHealthEventView(_ClosedView):
    event_id: int = Field(gt=0)
    check_name: str
    component: str
    transition_type: str
    before_status: str | None
    resulting_status: str
    message: str
    occurred_at: datetime


class AlertTargetView(_ClosedView):
    target_id: int = Field(gt=0)
    target_kind: str
    display_label: str
    state: str
    minimum_status: str
    current_version: str
    updated_at: datetime


class AlertAdminCandidateView(_ClosedView):
    candidate_id: int = Field(gt=0)
    display_label: str
    line_linked: bool


class AlertTargetMutationReceipt(_ClosedView):
    receipt_id: str
    command_family: str
    operation: str
    target_id: int = Field(gt=0)
    previous_state: str
    resulting_state: str
    current_version: str
    replayed: bool
    correlation_id: str
    committed_at: datetime


class RuntimeAuditRecordView(_ClosedView):
    audit_id: int = Field(gt=0)
    occurred_at: datetime
    actor_label_masked: str | None = None
    action_family: Literal[
        "authentication",
        "account_security",
        "session",
        "mfa",
        "system",
        "other",
    ]
    target_label_masked: str | None = None
    ip_address_masked: str | None = None
    outcome: Literal["success", "denied", "failed", "unknown"]
    reason_code: str | None = None


class RuntimeAuditPageView(_ClosedView):
    items: list[RuntimeAuditRecordView]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=1)


_View = TypeVar("_View", bound=BaseModel)


class RuntimeHealthApiClient:
    def __init__(self, transport: LineAdminApiClient) -> None:
        self._transport = transport

    def health_status(self, token: str | None) -> list[RuntimeHealthRecordView]:
        return _validate_list(
            self._transport.request("GET", "/api/v1/runtime/health-status", token=token),
            RuntimeHealthRecordView,
            "runtime_health_invalid_response",
        )

    def health_events(
        self, token: str | None, limit: int = 100
    ) -> list[RuntimeHealthEventView]:
        return _validate_list(
            self._transport.request(
                "GET",
                "/api/v1/runtime/health-events",
                token=token,
                params={"limit": limit},
            ),
            RuntimeHealthEventView,
            "runtime_health_invalid_response",
        )

    def alert_targets(self, token: str | None) -> list[AlertTargetView]:
        return _validate_list(
            self._transport.request(
                "GET", "/api/v1/runtime/line-alert-targets", token=token
            ),
            AlertTargetView,
            "runtime_alert_target_invalid_response",
        )

    def add_admin_target(
        self,
        token: str | None,
        admin_user_id: int,
        minimum_status: str,
        *,
        reason: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> AlertTargetMutationReceipt:
        payload = {
            "admin_user_id": admin_user_id,
            "minimum_status": minimum_status,
            "reason": reason,
            "idempotency_key": idempotency_key,
            "correlation_id": correlation_id,
        }
        return self._mutate(
            "POST",
            "/api/v1/runtime/line-alert-targets/admin",
            token=token,
            payload=payload,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

    def admin_alert_candidates(
        self, token: str | None
    ) -> list[AlertAdminCandidateView]:
        return _validate_list(
            self._transport.request(
                "GET",
                "/api/v1/runtime/line-alert-targets/admin-candidates",
                token=token,
            ),
            AlertAdminCandidateView,
            "runtime_alert_target_invalid_response",
        )

    def set_target_enabled(
        self,
        token: str | None,
        target_id: int,
        *,
        expected_version: str,
        enabled: bool,
        reason: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> AlertTargetMutationReceipt:
        payload = {
            "expected_version": expected_version,
            "enabled": enabled,
            "reason": reason,
            "idempotency_key": idempotency_key,
            "correlation_id": correlation_id,
        }
        return self._mutate(
            "PATCH",
            f"/api/v1/runtime/line-alert-targets/{target_id}",
            token=token,
            payload=payload,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

    def reset_group_target(
        self,
        token: str | None,
        *,
        expected_version: str,
        reason: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> AlertTargetMutationReceipt:
        payload = {
            "expected_version": expected_version,
            "reason": reason,
            "idempotency_key": idempotency_key,
            "correlation_id": correlation_id,
        }
        return self._mutate(
            "POST",
            "/api/v1/runtime/line-alert-targets/group/reset",
            token=token,
            payload=payload,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

    def audit_records(
        self,
        token: str | None,
        *,
        action_prefix: str | None = None,
        limit: int = 100,
    ) -> list[RuntimeAuditRecordView]:
        try:
            page = RuntimeAuditPageView.model_validate(
                self._transport.request(
                    "GET",
                    "/api/v1/admin/audits",
                    token=token,
                    params={"action_prefix": action_prefix, "page_size": limit},
                )
            )
        except (TypeError, ValidationError) as error:
            raise _invalid_response("runtime_audit_invalid_response") from error
        return page.items

    def _mutate(
        self,
        method: str,
        path: str,
        *,
        token: str | None,
        payload: dict[str, Any],
        idempotency_key: str,
        correlation_id: str,
    ) -> AlertTargetMutationReceipt:
        value = self._transport.request(
            method,
            path,
            token=token,
            json=payload,
            extra_headers={
                "Idempotency-Key": idempotency_key,
                "X-Correlation-ID": correlation_id,
            },
        )
        try:
            return AlertTargetMutationReceipt.model_validate(value)
        except (ValidationError, TypeError, ValueError) as error:
            raise _invalid_response("runtime_alert_target_invalid_receipt") from error


def _validate_list(
    value: object, model: type[_View], code: str
) -> list[_View]:
    if not isinstance(value, list):
        raise _invalid_response(code)
    try:
        return [model.model_validate(item) for item in value]
    except (ValidationError, TypeError, ValueError) as error:
        raise _invalid_response(code) from error


def _invalid_response(code: str) -> LineAdminApiError:
    return LineAdminApiError(
        "伺服器回傳格式不正確，未顯示未驗證資料。",
        category="internal",
        code=code,
        retryable=False,
    )


__all__ = [
    "AlertAdminCandidateView",
    "AlertTargetMutationReceipt",
    "AlertTargetView",
    "RuntimeHealthApiClient",
    "RuntimeHealthEventView",
    "RuntimeHealthRecordView",
]
