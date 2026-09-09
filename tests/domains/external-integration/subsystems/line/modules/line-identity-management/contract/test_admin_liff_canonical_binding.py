"""Regression coverage for canonical admin bindings used by staff LIFF entrypoints."""

from domains.line.identities import LineUserId
from infrastructure.mysql.line_identity_owner_adapters import (
    MySqlAdminIdentityOwnerAdapter,
)


class _CanonicalOnlyCursor:
    def __init__(self) -> None:
        self.sql = ""
        self.parameters = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, sql, parameters) -> None:
        self.sql = sql
        self.parameters = tuple(parameters)

    def fetchone(self):
        if "JOIN line_identity_role_bindings b" not in self.sql:
            return None
        return {"id": 1, "display_name": "Union Admin", "role": "system_admin"}


class _Connection:
    def __init__(self, cursor: _CanonicalOnlyCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _CanonicalOnlyCursor:
        return self._cursor


def test_admin_liff_accepts_canonical_binding_when_legacy_binding_is_absent() -> None:
    cursor = _CanonicalOnlyCursor()
    line_user_id = LineUserId("U-canonical-admin")

    linked_admin = MySqlAdminIdentityOwnerAdapter(
        _Connection(cursor)
    ).get_linked_admin(line_user_id)

    assert linked_admin is not None
    assert linked_admin.admin_user_id == 1
    assert linked_admin.line_user_id == line_user_id
    assert cursor.parameters == (line_user_id.value,)
    assert "JOIN line_identity_role_bindings b" in cursor.sql
    assert "JOIN line_identity_bindings b" not in cursor.sql
    assert "b.subject_type='admin'" in cursor.sql
    assert "b.binding_status='bound'" in cursor.sql
    assert "a.enabled=1" in cursor.sql
