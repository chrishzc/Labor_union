"""Verify obsolete LINE review endpoints cannot bypass typed authorization."""

import pytest
from fastapi import HTTPException

from line import line_bot


LEGACY_REVIEW_ENDPOINTS = (
    line_bot.get_rebind_requests,
    line_bot.approve_rebind_request,
    line_bot.reject_rebind_request,
    line_bot.list_staff_review_requests,
)


@pytest.mark.parametrize("endpoint", LEGACY_REVIEW_ENDPOINTS)
def test_legacy_review_endpoints_are_gone(endpoint):
    with pytest.raises(HTTPException) as error:
        endpoint()

    assert error.value.status_code == 410
    assert error.value.detail == {
        "code": "line_review_api_retired",
        "replacement": "/api/v1/line/identity/reviews",
    }


@pytest.mark.parametrize(
    "endpoint",
    (line_bot.approve_staff_review_request, line_bot.reject_staff_review_request),
)
def test_legacy_staff_review_actions_are_gone(endpoint):
    with pytest.raises(HTTPException) as error:
        endpoint("staff_verification", "41")

    assert error.value.status_code == 410
    assert error.value.detail == {
        "code": "line_review_api_retired",
        "replacement": "/api/v1/line/identity/reviews",
    }
