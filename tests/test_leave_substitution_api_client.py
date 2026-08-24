"""
File: test_leave_substitution_api_client.py
Description: 驗證請假代班 Streamlit client 可匯入並嚴格解析既有 Global typed error。
"""

from __future__ import annotations

import pytest

from ui.api_clients.leave_substitution_api_client import (
    LeaveSubstitutionApiClient,
    LeaveSubstitutionApiError,
)


class _Response:
    ok = False
    status_code = 409

    def json(self) -> dict[str, object]:
        return {
            "detail": {
                "error": {
                    "category": "domain_blocked",
                    "code": "coverage_incomplete",
                    "message": "服務日未覆蓋。",
                    "field_errors": [],
                    "domain_blockers": ["coverage_incomplete"],
                    "retryable": False,
                    "correlation_id": "calendar-test",
                    "current_version": 3,
                }
            }
        }


class _Session:
    def request(self, *args: object, **kwargs: object) -> _Response:
        return _Response()


def test_leave_substitution_client_imports_and_preserves_typed_error() -> None:
    client = LeaveSubstitutionApiClient(
        base_url="http://api.test",
        headers={},
        session=_Session(),  # type: ignore[arg-type]
    )

    with pytest.raises(LeaveSubstitutionApiError, match="服務日未覆蓋"):
        client.assignments("C-1")
