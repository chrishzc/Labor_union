"""Typed read client for the Scheduling matching workbench."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from api.routes.caregiver_segment_availability import (
    CaregiverSegmentAvailabilityResponse,
    CaregiverSegmentAvailabilitySearchRequest,
    SingleCaregiverEligibilityRequest,
)
from api.schemas.base import BaseResponse
from api.schemas.candidate_contact_pool import CandidateContactPoolView
from api.schemas.matches import (
    ActiveMatchingPlanStateView,
    FormalPlanContactStateView,
)


T = TypeVar("T", bound=BaseModel)


@dataclass(slots=True)
class MatchingReadApiError(RuntimeError):
    """A transport, HTTP, or response-contract failure at the UI boundary."""

    status_code: int | None
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class MatchingReadApiClient:
    """Read-only Matching endpoints with closed response validation."""

    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str],
        timeout: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._base_url = base_url.strip().rstrip("/")
        self._headers = {str(key): str(value) for key, value in headers.items()}
        self._timeout = float(timeout)
        self._session = session or requests.Session()

    def active_plan(self, case_no: str) -> ActiveMatchingPlanStateView:
        return self._request(
            "GET",
            f"/api/v1/orders/{_case_no(case_no)}/matching-plans/active",
            ActiveMatchingPlanStateView,
        )

    def contact_state(self, case_no: str, plan_id: int) -> FormalPlanContactStateView:
        if not isinstance(plan_id, int) or isinstance(plan_id, bool) or plan_id < 1:
            raise ValueError("plan_id must be a positive integer")
        return self._request(
            "GET",
            f"/api/v1/orders/{_case_no(case_no)}/matching-plans/{plan_id}/contact-state",
            FormalPlanContactStateView,
        )

    def candidate_contact_pool(self, case_no: str) -> CandidateContactPoolView:
        return self._request(
            "GET",
            f"/api/v1/orders/{_case_no(case_no)}/candidate-contact-pool",
            CandidateContactPoolView,
        )

    def search_availability(
        self,
        case_no: str,
        *,
        segment_count: int,
        segment_drafts: list[Mapping[str, Any]],
        as_of: date,
        filters: Mapping[str, Any] | None = None,
    ) -> CaregiverSegmentAvailabilityResponse:
        request = CaregiverSegmentAvailabilitySearchRequest.model_validate(
            {
                "segment_count": segment_count,
                "segment_drafts": segment_drafts,
                "as_of": as_of,
                "filters": filters or {},
            }
        )
        return self._request(
            "POST",
            f"/api/v1/orders/{_case_no(case_no)}/caregiver-segment-availability/search",
            CaregiverSegmentAvailabilityResponse,
            payload=request.model_dump(mode="json"),
        )

    def check_single_eligibility(
        self,
        case_no: str,
        *,
        start_date: date,
        end_date: date,
        as_of: date,
    ) -> CaregiverSegmentAvailabilityResponse:
        request = SingleCaregiverEligibilityRequest(
            start_date=start_date,
            end_date=end_date,
            as_of=as_of,
        )
        return self._request(
            "POST",
            f"/api/v1/orders/{_case_no(case_no)}/caregiver-single-eligibility/check",
            CaregiverSegmentAvailabilityResponse,
            payload=request.model_dump(mode="json"),
        )

    def _request(
        self,
        method: str,
        path: str,
        response_type: type[T],
        *,
        payload: Mapping[str, Any] | None = None,
    ) -> T:
        try:
            response = self._session.request(
                method,
                f"{self._base_url}{path}",
                headers=self._headers,
                json=dict(payload) if payload is not None else None,
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise MatchingReadApiError(
                None,
                "matching_read_transport_error",
                "無法連線至月嫂配對查詢 API。",
            ) from error
        if not response.ok:
            raise _http_error(response)
        try:
            envelope = BaseResponse[response_type].model_validate(response.json())
            if not envelope.success or envelope.data is None:
                raise ValueError("response envelope is not successful")
            return envelope.data
        except (TypeError, ValidationError, ValueError) as error:
            raise MatchingReadApiError(
                response.status_code,
                "matching_read_invalid_response",
                "月嫂配對查詢 API 回傳格式不正確。",
            ) from error


def _http_error(response: Any) -> MatchingReadApiError:
    try:
        body = response.json()
        detail = body.get("detail") if isinstance(body, dict) else None
        error = detail.get("error") if isinstance(detail, dict) else None
        if isinstance(error, dict):
            return MatchingReadApiError(
                response.status_code,
                str(error.get("code", "matching_read_request_failed")),
                str(error.get("message", "月嫂配對查詢失敗。")),
            )
    except (AttributeError, TypeError, ValueError):
        pass
    return MatchingReadApiError(
        response.status_code,
        "matching_read_request_failed",
        "月嫂配對查詢失敗。",
    )


def _case_no(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("case_no is required")
    return value.strip()


__all__ = ["MatchingReadApiClient", "MatchingReadApiError"]
