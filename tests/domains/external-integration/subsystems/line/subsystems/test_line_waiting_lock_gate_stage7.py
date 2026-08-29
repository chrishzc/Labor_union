"""Stage 7 waiting-deposit lock requires the customer acceptance root fact."""

import pytest

from subsystems.scheduling.availability_lock_acquisition_workflow import (
    _require_customer_matching_acceptance,
)


class _Cursor:
    def __init__(self, row) -> None:
        self.row = row
        self.executed = None

    def execute(self, statement, parameters):
        self.executed = (statement, parameters)

    def fetchone(self):
        return self.row


def test_waiting_lock_accepts_latest_customer_acceptance() -> None:
    cursor = _Cursor({"response_value": "accepted"})

    _require_customer_matching_acceptance(cursor, 10)

    assert cursor.executed[1] == (10,)


@pytest.mark.parametrize("row", [None, {"response_value": "declined"}])
def test_waiting_lock_rejects_missing_or_non_acceptance(row) -> None:
    with pytest.raises(ValueError, match="has not accepted"):
        _require_customer_matching_acceptance(_Cursor(row), 10)
