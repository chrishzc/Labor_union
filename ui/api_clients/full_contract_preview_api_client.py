"""Typed client for the authenticated Full Contract Query/Preview endpoints."""

from __future__ import annotations

from collections.abc import Mapping
import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.full_contract_preview import FullContractPreviewView


class FullContractPreviewApiError(RuntimeError):
    """Safe, user-facing failure from the typed full-contract preview API."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class FullContractPreviewApiClient:
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
        self._base_url = base_url.strip().rstrip("/")
        self._headers = {str(key): str(value) for key, value in headers.items()}
        self._timeout = timeout
        self._session = session or requests.Session()

    def preview_client(self, case_no: str) -> FullContractPreviewView:
        return self._preview(case_no, "/contract-signing/client/preview")

    def preview_staff(self, case_no: str, assignment_id: int) -> FullContractPreviewView:
        assignment = _positive_id(assignment_id)
        return self._preview(
            case_no,
            f"/contract-signing/staff-segments/{assignment}/preview",
        )

    def _preview(self, case_no: str, suffix: str) -> FullContractPreviewView:
        canonical_case_no = _case_no(case_no)
        try:
            response = self._session.post(
                f"{self._base_url}/api/v1/orders/{canonical_case_no}{suffix}",
                headers=self._headers,
                json={},
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise FullContractPreviewApiError("契約預覽服務暫時無法連線。") from error
        if not response.ok:
            raise _http_error(response)
        try:
            envelope = BaseResponse[FullContractPreviewView].model_validate(response.json())
            if not envelope.success or envelope.data is None:
                raise ValueError("invalid response envelope")
            result = envelope.data
        except (TypeError, ValueError, ValidationError) as error:
            raise FullContractPreviewApiError("契約預覽 API 回傳格式不正確。", status_code=response.status_code) from error
        if result.case_no != canonical_case_no:
            raise FullContractPreviewApiError("契約預覽案件識別不一致。", status_code=409)
        return result

def _http_error(response: requests.Response) -> FullContractPreviewApiError:
    # Keep API internals, locators, and raw response data out of the UI.
    if response.status_code in {401, 403}:
        message = "目前帳號無權檢視這份契約。"
    elif response.status_code == 404:
        message = "找不到指定案件或服務人員指派。"
    elif response.status_code == 409:
        message = "契約資料已變更或目前仍有阻擋項目，請重新預覽。"
    elif response.status_code >= 500:
        message = "契約預覽服務暫時無法使用，請稍後重試。"
    else:
        message = "契約預覽目前無法使用。"
    return FullContractPreviewApiError(message, status_code=response.status_code)


def _case_no(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("case_no is required")
    return value.strip()


def _positive_id(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("assignment_id must be a positive integer")
    return value


__all__ = [
    "FullContractPreviewApiClient",
    "FullContractPreviewApiError",
]
