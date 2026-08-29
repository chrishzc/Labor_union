"""
File: test_staff_subject_binding_ssot.py
Description: 驗證 Staff LIFF 僅以有效 canonical LINE binding 解析月嫂身分。
"""

from infrastructure.mysql.customer_service_repository import (
    MySqlCustomerServiceRepository,
)


class _Cursor:
    def __init__(self) -> None:
        self.sql = ""
        self.parameters = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, sql, parameters) -> None:
        self.sql = sql
        self.parameters = parameters

    def fetchone(self):
        return None


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _Cursor:
        return self._cursor


def test_staff_subject_requires_active_canonical_binding() -> None:
    cursor = _Cursor()
    repository = MySqlCustomerServiceRepository(_Connection(cursor))

    assert repository.staff_subject("U-canonical") is None

    assert cursor.parameters == ("U-canonical",)
    assert "FROM line_identity_bindings b" in cursor.sql
    assert "b.subject_type='staff'" in cursor.sql
    assert "b.binding_status='bound'" in cursor.sql
    assert "s.line_user_id" not in cursor.sql
    assert "UNION ALL" not in cursor.sql
