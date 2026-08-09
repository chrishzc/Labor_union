"""Typed client for the current Scheduling projection query."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.scheduling_current import (
    SchedulingCurrentProjectionView,
    SchedulingCurrentTypedErrorView,
)


@dataclass(slots=True)
class SchedulingCurrentApiError(RuntimeError):
    status_code: int | None
    error: SchedulingCurrentTypedErrorView

    def __str__(self) -> str:
        return self.error.message


class SchedulingCurrentApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str],
        timeout: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = _base_url(base_url)
        self._headers = {str(key): str(value) for key, value in headers.items()}
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._timeout = float(timeout)
        self._session = session or requests.Session()

    def query(
        self,
        staff_id: int,
        range_start: date,
        range_end: date,
        *,
        correlation_id: str = "scheduling-current-ui-query",
    ) -> SchedulingCurrentProjectionView:
        if not isinstance(staff_id, int) or isinstance(staff_id, bool) or staff_id < 1:
            raise ValueError("staff_id must be a positive integer")
        if not isinstance(range_start, date) or not isinstance(range_end, date):
            raise ValueError("query dates are required")
        if range_end < range_start:
            raise ValueError("range_end must not precede range_start")
        try:
            response = self._session.get(
                f"{self._base_url}/api/v1/scheduling/staff/{staff_id}/current-calendar",
                headers={**self._headers, "X-Correlation-ID": correlation_id},
                params={
                    "range_start": range_start.isoformat(),
                    "range_end": range_end.isoformat(),
                },
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise _transport_error() from error
        if not response.ok:
            raise _http_error(response)
        return _valid_projection(response)


def _valid_projection(response) -> SchedulingCurrentProjectionView:
    try:
        envelope = BaseResponse[SchedulingCurrentProjectionView].model_validate(
            response.json()
        )
    except (TypeError, ValidationError, ValueError) as error:
        raise _invalid_response(response.status_code) from error
    if not envelope.success or envelope.data is None:
        raise _invalid_response(response.status_code)
    return envelope.data


def _http_error(response) -> SchedulingCurrentApiError:
    try:
        detail = response.json().get("detail")
        error = detail.get("error") if isinstance(detail, dict) else None
        return SchedulingCurrentApiError(
            response.status_code,
            SchedulingCurrentTypedErrorView.model_validate(error),
        )
    except (AttributeError, TypeError, ValidationError, ValueError):
        return _invalid_response(response.status_code)


def _transport_error() -> SchedulingCurrentApiError:
    return SchedulingCurrentApiError(
        None,
        SchedulingCurrentTypedErrorView(
            category="unavailable",
            code="scheduling_current_transport_error",
            message="無法連線至目前排班 API。",
            correlation_id="scheduling-current-ui-query",
            retryable=True,
        ),
    )


def _invalid_response(status_code: int | None) -> SchedulingCurrentApiError:
    return SchedulingCurrentApiError(
        status_code,
        SchedulingCurrentTypedErrorView(
            category="internal",
            code="scheduling_current_invalid_response",
            message="目前排班 API 回傳格式不正確。",
            correlation_id="scheduling-current-ui-query",
        ),
    )


def _base_url(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("base_url is required")
    return value.strip().rstrip("/")


__all__ = ["SchedulingCurrentApiClient", "SchedulingCurrentApiError"]
