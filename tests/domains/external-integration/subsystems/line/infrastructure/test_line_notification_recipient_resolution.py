"""
File: test_line_notification_recipient_resolution.py
Description: 驗證 line_notification_repository 對 client.bound_case 與自訂範本變數的解析邏輯。
"""

from domains.line.delivery import LineRecipientType
from infrastructure.mysql.line_notification_repository import (
    MySqlLineNotificationRepository,
    _template_variables,
)


class MockCursor:
    def __init__(self, fetchone_result=None):
        self._fetchone_result = fetchone_result
        self.last_query = None
        self.last_params = None

    def execute(self, query, params=None):
        self.last_query = query
        self.last_params = params

    def fetchone(self):
        return self._fetchone_result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockConnection:
    def __init__(self, cursor_result=None):
        self._cursor = MockCursor(cursor_result)

    def cursor(self):
        return self._cursor


def test_resolve_recipient_direct_line_user_id() -> None:
    repo = MySqlLineNotificationRepository(MockConnection())
    facts = {
        "case_no": "CASE-1",
        "line_user_id": "U_DIRECT_12345",
    }
    recipient = repo._resolve_recipient("client.bound_case", facts)
    assert recipient is not None
    assert recipient.recipient_type == LineRecipientType.USER
    assert recipient.identity.value == "U_DIRECT_12345"


def test_resolve_recipient_from_db_lookup() -> None:
    conn = MockConnection({"line_user_id": "U_DB_99999"})
    repo = MySqlLineNotificationRepository(conn)
    facts = {"case_no": "CASE-1"}
    recipient = repo._resolve_recipient("client.bound_case", facts)
    assert recipient is not None
    assert recipient.recipient_type == LineRecipientType.USER
    assert recipient.identity.value == "U_DB_99999"


def test_resolve_recipient_returns_none_when_no_user_found() -> None:
    conn = MockConnection(None)
    repo = MySqlLineNotificationRepository(conn)
    facts = {"case_no": "CASE-UNKNOWN"}
    recipient = repo._resolve_recipient("client.bound_case", facts)
    assert recipient is None


def test_template_variables_extracts_declared_variables() -> None:
    templates = {
        "templates": [
            {
                "id": "TPL-CUSTOM-1",
                "variables": [
                    {"name": "case_no"},
                    {"name": "first_payment_amount"},
                ],
            }
        ]
    }
    facts = {
        "case_no": "CASE-888",
        "first_payment_amount": "NT$ 20,000",
        "unrelated_fact": "should_be_ignored",
    }
    vars_dict = _template_variables(facts, "TPL-CUSTOM-1", templates)
    assert vars_dict == {
        "case_no": "CASE-888",
        "first_payment_amount": "NT$ 20,000",
    }
