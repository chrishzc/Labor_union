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
