"""Typed HTTP client for Scheduling staff matching preferences."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.staff_matching_preferences import (
    DefinitionPreviewView,
    ProfilePreviewView,
    StaffPreferenceApplyReceiptView,
    StaffPreferenceDefinitionInput,
    StaffPreferenceDefinitionView,
    StaffPreferenceProfileInput,
    StaffPreferenceProfileView,
)


@dataclass(slots=True)
class StaffMatchingPreferencesApiError(RuntimeError):
    status_code: int | None
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class StaffMatchingPreferencesApiClient:
    def __init__(self, *, base_url: str, headers: Mapping[str, str]) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = dict(headers)

    def definitions(self) -> list[StaffPreferenceDefinitionView]:
        return self._request("GET", "/definitions", list[StaffPreferenceDefinitionView])

    def profile(self, staff_id: int) -> StaffPreferenceProfileView:
        return self._request("GET", f"/staff/{staff_id}", StaffPreferenceProfileView)

    def preview_definition(self, key: str, definition: StaffPreferenceDefinitionInput):
        return self._request(
            "POST", f"/definitions/{key}/preview", DefinitionPreviewView,
            json={"definition": definition.model_dump(mode="json")},
        )

    def apply_definition(self, key, definition, expected_version, fingerprint, reason, command_id):
        return self._request(
            "POST", f"/definitions/{key}/apply", StaffPreferenceApplyReceiptView,
            json={"definition": definition.model_dump(mode="json"), "expected_version": expected_version,
                  "preview_fingerprint": fingerprint, "reason": reason},
            command_id=command_id,
        )

    def preview_profile(self, staff_id: int, profile: StaffPreferenceProfileInput):
        return self._request(
            "POST", f"/staff/{staff_id}/preview", ProfilePreviewView,
            json=profile.model_dump(mode="json"),
        )

    def apply_profile(self, staff_id, profile, expected_version, fingerprint, reason, command_id):
        return self._request(
            "POST", f"/staff/{staff_id}/apply", StaffPreferenceApplyReceiptView,
            json={**profile.model_dump(mode="json"), "expected_version": expected_version,
                  "preview_fingerprint": fingerprint, "reason": reason},
            command_id=command_id,
        )

    # Kept cohesive because transport, envelope validation and typed error conversion form one boundary.
    def _request(self, method: str, path: str, model: Any, *, json=None, command_id=None):
        headers = {**self._headers, "X-Correlation-ID": command_id or "staff-preference-ui"}
        if command_id:
            headers["Idempotency-Key"] = command_id
        try:
            response = requests.request(
                method, self._base_url + "/api/v1/scheduling/staff-matching-preferences" + path,
                headers=headers, json=json, timeout=15,
            )
        except requests.RequestException as error:
            raise StaffMatchingPreferencesApiError(None, "transport_error", "無法連線至月嫂偏好 API。") from error
        if not response.ok:
            raise _preference_http_error(response)
        try:
            envelope = BaseResponse[model].model_validate(response.json())
        except (TypeError, ValidationError, ValueError) as error:
            raise StaffMatchingPreferencesApiError(response.status_code, "invalid_response", "月嫂偏好 API 回傳格式不正確。") from error
        if not envelope.success or envelope.data is None:
            raise StaffMatchingPreferencesApiError(response.status_code, "invalid_response", "月嫂偏好 API 回應狀態不正確。")
        return envelope.data


def _preference_http_error(response) -> StaffMatchingPreferencesApiError:
    try:
        detail = response.json().get("detail")
        if isinstance(detail, dict):
            return StaffMatchingPreferencesApiError(
                response.status_code, str(detail.get("code", "request_rejected")),
                str(detail.get("message", "月嫂偏好操作被拒絕。")),
            )
    except (AttributeError, TypeError, ValueError):
        pass
    return StaffMatchingPreferencesApiError(response.status_code, "request_rejected", "月嫂偏好操作被拒絕。")


__all__ = ["StaffMatchingPreferencesApiClient", "StaffMatchingPreferencesApiError"]
