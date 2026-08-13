"""Typed HTTP client for Scheduling staff unavailability."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.staff_availability import (
    StaffAvailabilityApplyBody,
    StaffAvailabilityIntentBody,
    StaffAvailabilityPreviewView,
    StaffAvailabilityReceiptView,
    StaffUnavailabilityBlockView,
)


@dataclass(slots=True)
class StaffAvailabilityApiError(RuntimeError):
    status_code: int | None
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class StaffAvailabilityApiClient:
    def __init__(self, *, base_url: str, headers: Mapping[str, str]) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = dict(headers)

    def query(self, staff_id: int, range_start: date, range_end: date):
        return self._request(
            "GET", staff_id, "", list[StaffUnavailabilityBlockView],
            params={"range_start": range_start.isoformat(), "range_end": range_end.isoformat()},
        )

    def preview(self, staff_id: int, intent: StaffAvailabilityIntentBody):
        return self._request(
            "POST", staff_id, "/preview", StaffAvailabilityPreviewView,
            json=intent.model_dump(mode="json"),
        )

    def apply(self, staff_id, intent, expected_version, fingerprint, command_id):
        body = StaffAvailabilityApplyBody(
            **intent.model_dump(), expected_version=expected_version,
            preview_fingerprint=fingerprint,
        )
        return self._request(
            "POST", staff_id, "/apply", StaffAvailabilityReceiptView,
            json=body.model_dump(mode="json"), command_id=command_id,
        )

    # Kept cohesive because transport, envelope validation and typed error conversion form one boundary.
    def _request(self, method, staff_id, suffix, model, *, params=None, json=None, command_id=None):
        headers = {**self._headers, "X-Correlation-ID": command_id or "staff-availability-ui"}
        if command_id:
            headers["Idempotency-Key"] = command_id
        url = f"{self._base_url}/api/v1/scheduling/staff/{staff_id}/availability-blocks{suffix}"
        try:
            response = requests.request(
                method, url, headers=headers, params=params, json=json, timeout=15,
            )
        except requests.RequestException as error:
            raise StaffAvailabilityApiError(None, "transport_error", "無法連線至不可服務期間 API。") from error
        if not response.ok:
            raise _availability_http_error(response)
        try:
            envelope = BaseResponse[model].model_validate(response.json())
        except (TypeError, ValidationError, ValueError) as error:
            raise StaffAvailabilityApiError(response.status_code, "invalid_response", "不可服務期間 API 回傳格式不正確。") from error
        if not envelope.success or envelope.data is None:
            raise StaffAvailabilityApiError(response.status_code, "invalid_response", "不可服務期間 API 回應狀態不正確。")
        return envelope.data


def _availability_http_error(response) -> StaffAvailabilityApiError:
    try:
        detail = response.json().get("detail")
        error = detail.get("error") if isinstance(detail, dict) else None
        if isinstance(error, dict):
            return StaffAvailabilityApiError(
                response.status_code, str(error.get("code", "request_rejected")),
                str(error.get("message", "不可服務期間操作被拒絕。")),
            )
    except (AttributeError, TypeError, ValueError):
        pass
    return StaffAvailabilityApiError(response.status_code, "request_rejected", "不可服務期間操作被拒絕。")


__all__ = ["StaffAvailabilityApiClient", "StaffAvailabilityApiError"]
