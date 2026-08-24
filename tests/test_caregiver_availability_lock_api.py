"""
File: test_caregiver_availability_lock_api.py
Description: 驗證等待訂金檔期鎖 API 將業務阻擋轉成可操作的 typed error。
"""

import pytest
from fastapi import HTTPException

from api.routes.caregiver_availability_locks import _waiting_lock_value_error
from shared_kernel.identities import CorrelationId


def test_waiting_lock_conflict_is_a_typed_conflict_error():
    with pytest.raises(HTTPException) as raised:
        raise _waiting_lock_value_error(
            ValueError('{"conflicts":[{"staff_id":8892}]}'),
            CorrelationId("wp56-occupancy-conflict"),
        )

    assert raised.value.status_code == 409
    assert raised.value.detail["error"]["category"] == "conflict"
    assert raised.value.detail["error"]["code"] == "waiting_lock_conflict"


def test_waiting_lock_commitment_blocker_is_actionable():
    with pytest.raises(HTTPException) as raised:
        raise _waiting_lock_value_error(
            ValueError("active staff service commitment is required"),
            CorrelationId("waiting-lock-commitment-required"),
        )

    assert raised.value.status_code == 409
    assert raised.value.detail["error"]["code"] == "staff_service_commitment_required"
    assert raised.value.detail["error"]["domain_blockers"] == [
        "staff_service_commitment_required"
    ]


def test_waiting_lock_rejects_a_commitment_with_the_wrong_service_day_count():
    with pytest.raises(HTTPException) as raised:
        raise _waiting_lock_value_error(
            ValueError("active staff service commitment days mismatch"),
            CorrelationId("waiting-lock-commitment-days-mismatch"),
        )

    assert raised.value.status_code == 409
    assert raised.value.detail["error"]["code"] == "staff_service_commitment_days_mismatch"
