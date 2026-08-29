"""
File: test_historical_order_review_remediation_repository.py
Description: 驗證歷史訂單更正 repository 的 replay 查詢使用明確 owner 欄位。
"""

from infrastructure.mysql.historical_order_review_remediation_repository import (
    MySqlHistoricalOrderReviewRemediationRepository,
)
from shared_kernel.identities import IdempotencyKey


class _Cursor:
    def __init__(self) -> None:
        self.sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, _params) -> None:
        self.sql = sql

    def fetchone(self):
        return None


class _Connection:
    def __init__(self) -> None:
        self.value = _Cursor()

    def cursor(self):
        return self.value


def test_replay_query_qualifies_receipt_command_fingerprint() -> None:
    connection = _Connection()
    repository = MySqlHistoricalOrderReviewRemediationRepository(
        connection,
        adoption_workflow=object(),
    )

    assert repository.find_receipt(IdempotencyKey("historical-review:test")) is None
    assert "SELECT receipt.command_fingerprint" in connection.value.sql
