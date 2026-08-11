"""Typed bounded client for administrative LINE identity bindings."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError


class _StrictView(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LineIdentityBindingView(_StrictView):
    line_user_id: str
    status: str
    version: int
    subject_type: str
    subject_reference: str
    subject_name: str
    updated_at: datetime | None = None
    revocation_request_id: int | None = None
    revocation_status: str | None = None
    revoked_at: datetime | None = None


class LineIdentityBindingPageView(_StrictView):
    items: list[LineIdentityBindingView]
    total: int
    page: int
    page_size: int


class LineIdentityRevocationPreviewView(_StrictView):
    binding: LineIdentityBindingView
    default_menu_publication_id: int | None = None
    provider_menu_id: str | None = None
    blockers: list[str]


class LineIdentityReplacementPreviewView(_StrictView):
    binding: LineIdentityBindingView
    target_subject_reference: str
    target_subject_name: str
    blockers: list[str]


class LineIdentityRevocationRequestView(_StrictView):
    request_id: int
    line_user_id: str
    subject_type: str
    subject_reference: str
    status: str
    pending_binding_version: int
    publication_id: int
    provider_menu_id: str
    requested_by_actor_id: str
    reason: str
    attempt_count: int
    last_error_code: str | None = None
    last_error_message: str | None = None


class LineIdentityBindingApiClient:
    def __init__(self, transport: LineAdminApiClient) -> None:
        self._transport = transport

    def bindings(self, token: str | None, filters: dict[str, Any]):
        payload = self._transport.request(
            "GET",
            "/api/v1/line/identity-bindings",
            token=token,
            params={key: value for key, value in filters.items() if value not in {None, ""}},
        )
        return self._parse(LineIdentityBindingPageView, payload)

    def replacement_preview(self, token, line_user_id, target_reference):
        payload = self._transport.request(
            "POST",
            f"/api/v1/line/identity-bindings/{line_user_id}/replacement/preview",
            token=token,
            params={"target_subject_reference": target_reference},
        )
        return self._parse(LineIdentityReplacementPreviewView, payload)

    def replacement_apply(self, token, line_user_id, payload):
        result = self._transport.request(
            "POST",
            f"/api/v1/line/identity-bindings/{line_user_id}/replacement/apply",
            token=token,
            json=payload,
        )
        return self._parse(LineIdentityBindingView, result)

    def revocation_preview(self, token, line_user_id):
        payload = self._transport.request(
            "POST",
            f"/api/v1/line/identity-bindings/{line_user_id}/revocation/preview",
            token=token,
        )
        return self._parse(LineIdentityRevocationPreviewView, payload)

    def revocation_apply(self, token, line_user_id, payload):
        result = self._transport.request(
            "POST",
            f"/api/v1/line/identity-bindings/{line_user_id}/revocation/apply",
            token=token,
            json=payload,
        )
        return self._parse(LineIdentityRevocationRequestView, result)

    def revocation_action(self, token, request_id, action, reason):
        result = self._transport.request(
            "POST",
            f"/api/v1/line/identity-bindings/revocations/{request_id}/{action}",
            token=token,
            json={"reason": reason},
        )
        return self._parse(LineIdentityRevocationRequestView, result)

    @staticmethod
    def _parse(model_type, payload):
        try:
            return model_type.model_validate(payload)
        except ValidationError as error:
            raise LineAdminApiError(
                "LINE 身分 API 回傳格式不符合契約",
                category="schema",
                code="line_identity_binding_response_invalid",
            ) from error


__all__ = [
    "LineIdentityBindingApiClient",
    "LineIdentityBindingPageView",
    "LineIdentityBindingView",
    "LineIdentityReplacementPreviewView",
    "LineIdentityRevocationPreviewView",
    "LineIdentityRevocationRequestView",
]
