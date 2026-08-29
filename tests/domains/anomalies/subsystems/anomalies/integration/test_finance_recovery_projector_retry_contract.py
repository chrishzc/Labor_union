"""
File: test_finance_recovery_projector_retry_contract.py
Description: 驗證三個財務異常 projector 的有界 retry 與 dead-letter claim 契約。
"""

import pytest

from subsystems.anomalies import client_over_refund_recovery_anomaly_consumer as client
from subsystems.anomalies import government_overpayment_anomaly_consumer as government
from subsystems.anomalies import staff_overpayment_recovery_anomaly_consumer as staff


class _Cursor:
    rowcount = 1

    def __init__(self, statements):
        self._statements = statements

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, _params=()):
        self._statements.append(statement)

    def fetchone(self):
        return None


class _Connection:
    def __init__(self):
        self.statements = []
        self.commits = 0

    def cursor(self):
        return _Cursor(self.statements)

    def commit(self):
        self.commits += 1


@pytest.mark.parametrize(
    "claim",
    (government._claim_next_event, client._claim_next_event, staff._claim),
)
def test_dead_letter_event_is_excluded_from_automatic_claim(claim) -> None:
    connection = _Connection()
    assert claim(connection) is None
    assert "attempt_count<3" in connection.statements[0]


@pytest.mark.parametrize(
    "mark_failed",
    (government._mark_failed, client._mark_failed, staff._failed),
)
def test_third_failure_stops_scheduling_automatic_retry(mark_failed) -> None:
    connection = _Connection()
    mark_failed(connection, 9)
    statement = connection.statements[0]
    assert "attempt_count+1>=3" in statement
    assert "THEN NULL" in statement
    assert "status IN ('pending','failed')" in statement
    assert connection.commits == 1
