"""Framework-neutral HTTP client for the administration alert center."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

import requests
from pydantic import TypeAdapter, ValidationError

from api.schemas.finance_alert_center import (
    AlertActionViewModel,
    AlertCenterResponse,
    AlertDetailViewModel,
    AlertFamily,
    AlertListViewModel,
    AlertQuery,
    ClaimAlertCommand,
    ResolveAlertCommand,
    ScanAlertsCommand,
    ScanSummaryViewModel,
    TypedErrorCode,
    TypedErrorViewModel,
)


class FinanceAlertCenterApiError(RuntimeError):
    """One stable typed API or transport failure."""

    def __init__(self, error: TypedErrorViewModel, *, status_code: int | None = None):
        super().__init__(error.message)
        self.error = error
        self.status_code = status_code


T = TypeVar("T")


class FinanceAlertCenterApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str],
        timeout: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        canonical_base_url = str(base_url or "").strip().rstrip("/")
        if not canonical_base_url:
            raise ValueError("base_url is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._base_url = canonical_base_url
        self._headers = {str(key): str(value) for key, value in headers.items()}
        self._timeout = float(timeout)
        self._session = session or requests.Session()

    @staticmethod
    def _family_path(family: AlertFamily) -> str:
        if family == AlertFamily.FINANCE:
            return "/api/v1/finance-alerts"
        if family == AlertFamily.SYSTEM:
            return "/api/v1/system-alerts"
        raise ValueError("unsupported alert family")

    @staticmethod
    def _status_error_code(status_code: int) -> TypedErrorCode:
        return {
            400: TypedErrorCode.VALIDATION_ERROR,
            401: TypedErrorCode.UNAUTHORIZED,
            403: TypedErrorCode.FORBIDDEN,
            404: TypedErrorCode.NOT_FOUND,
            409: TypedErrorCode.CONFLICT,
            422: TypedErrorCode.VALIDATION_ERROR,
            502: TypedErrorCode.UNAVAILABLE,
            503: TypedErrorCode.UNAVAILABLE,
            504: TypedErrorCode.UNAVAILABLE,
        }.get(status_code, TypedErrorCode.INTERNAL_ERROR)

    @classmethod
    def _parse_http_error(
        cls,
        response: requests.Response,
    ) -> FinanceAlertCenterApiError:
        try:
            body = response.json()
        except ValueError:
            body = None
        detail = body.get("detail") if isinstance(body, Mapping) else None
        error_value = body.get("error") if isinstance(body, Mapping) else None
        candidate = detail if isinstance(detail, Mapping) else error_value
        if isinstance(candidate, Mapping):
            try:
                error = TypedErrorViewModel.model_validate(candidate)
                return FinanceAlertCenterApiError(
                    error, status_code=response.status_code
                )
            except ValidationError:
                pass
        field_errors = None
        if isinstance(detail, list):
            parsed_fields = []
            for item in detail:
                if not isinstance(item, Mapping):
                    continue
                location = item.get("loc") or []
                field = ".".join(str(part) for part in location) or "request"
                message = str(item.get("msg") or "invalid value")
                parsed_fields.append({"field": field, "message": message})
            field_errors = parsed_fields or None
        error = TypedErrorViewModel(
            code=cls._status_error_code(response.status_code),
            message=(
                str(detail)
                if isinstance(detail, str) and detail.strip()
                else "警示中心 API 請求失敗"
            ),
            field_errors=field_errors,
            retryable=response.status_code in {502, 503, 504},
        )
        return FinanceAlertCenterApiError(error, status_code=response.status_code)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        payload: Mapping[str, Any] | None = None,
        response_type: Any,
    ) -> Any:
        try:
            response = self._session.request(
                method,
                f"{self._base_url}{path}",
                headers=dict(self._headers),
                params=dict(params) if params is not None else None,
                json=dict(payload) if payload is not None else None,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise FinanceAlertCenterApiError(
                TypedErrorViewModel(
                    code=TypedErrorCode.UNAVAILABLE,
                    message="警示中心 API 暫時無法連線",
                    retryable=True,
                )
            ) from exc
        if not response.ok:
            raise self._parse_http_error(response)
        try:
            body = response.json()
            envelope = AlertCenterResponse[response_type].model_validate(body)
        except (ValueError, ValidationError, TypeError) as exc:
            raise FinanceAlertCenterApiError(
                TypedErrorViewModel(
                    code=TypedErrorCode.INTERNAL_ERROR,
                    message="警示中心 API 回應格式不正確",
                    retryable=False,
                ),
                status_code=response.status_code,
            ) from exc
        if not envelope.success or envelope.error is not None or envelope.data is None:
            raise FinanceAlertCenterApiError(
                envelope.error
                or TypedErrorViewModel(
                    code=TypedErrorCode.INTERNAL_ERROR,
                    message="警示中心 API 未回傳資料",
                    retryable=False,
                ),
                status_code=response.status_code,
            )
        return envelope.data

    def list_alerts(self, query: AlertQuery) -> AlertListViewModel:
        params = query.model_dump(
            mode="json",
            exclude={"family"},
            exclude_none=True,
        )
        return self._request(
            "GET",
            self._family_path(query.family),
            params=params,
            response_type=AlertListViewModel,
        )

    def get_alert(
        self,
        *,
        family: AlertFamily,
        alert_id: int,
    ) -> AlertDetailViewModel:
        if isinstance(alert_id, bool) or not isinstance(alert_id, int) or alert_id < 1:
            raise ValueError("alert_id must be a positive integer")
        value = self._request(
            "GET",
            f"{self._family_path(family)}/{alert_id}",
            response_type=AlertDetailViewModel,
        )
        return TypeAdapter(AlertDetailViewModel).validate_python(value)

    def resolve_alert(
        self,
        command: ResolveAlertCommand,
        *,
        family: AlertFamily,
    ) -> AlertActionViewModel:
        return self._request(
            "POST",
            f"{self._family_path(family)}/{command.alert_id}/resolve",
            payload={
                "operator": command.operator,
                "reason": command.reason,
            },
            response_type=AlertActionViewModel,
        )

    def claim(
        self,
        command: ClaimAlertCommand,
        *,
        family: AlertFamily,
    ) -> AlertActionViewModel:
        return self._request(
            "POST",
            f"{self._family_path(family)}/{command.alert_id}/claim",
            payload={"operator": command.operator},
            response_type=AlertActionViewModel,
        )

    def claim_alert(
        self,
        command: ClaimAlertCommand,
        *,
        family: AlertFamily,
    ) -> AlertActionViewModel:
        return self.claim(command, family=family)

    def scan(self, command: ScanAlertsCommand) -> ScanSummaryViewModel:
        return self._request(
            "POST",
            f"{self._family_path(command.family)}/scan",
            response_type=ScanSummaryViewModel,
        )

    def scan_alerts(self, command: ScanAlertsCommand) -> ScanSummaryViewModel:
        return self.scan(command)


__all__ = [
    "FinanceAlertCenterApiClient",
    "FinanceAlertCenterApiError",
]
