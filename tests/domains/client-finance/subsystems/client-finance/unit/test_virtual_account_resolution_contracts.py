"""Direct contracts for Client Finance virtual-account resolution."""

import pytest

from subsystems.client_finance.virtual_account_resolution import (
    resolve_client_virtual_account,
)


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def execute(self, statement, parameters):
        self.executed.append((statement, parameters))

    def fetchall(self):
        return self.rows


def test_invalid_virtual_account_fails_closed_without_database_access() -> None:
    for invalid in (None, 99781699115042, "", "9978169911504", "99781699ABC042"):
        cursor = _Cursor([])

        result = resolve_client_virtual_account(cursor, invalid)

        assert result == {
            "result": "pending",
            "case_no": None,
            "reason": "invalid_virtual_account_format",
        }
        assert cursor.executed == []


def test_valid_virtual_account_derives_canonical_case_and_uses_bound_parameter() -> None:
    cursor = _Cursor([{"case_no": "115000042"}])

    result = resolve_client_virtual_account(cursor, "99781699115042")

    assert result == {"result": "resolved", "case_no": "115000042", "reason": None}
    assert len(cursor.executed) == 1
    statement, parameters = cursor.executed[0]
    assert "WHERE case_no = %s" in statement
    assert parameters == ("115000042",)


def test_tuple_row_shape_is_supported_when_identity_matches() -> None:
    result = resolve_client_virtual_account(
        _Cursor([("115000007",)]),
        "99781699115007",
    )

    assert result["result"] == "resolved"
    assert result["case_no"] == "115000007"


def test_missing_duplicate_or_identity_drift_remains_pending() -> None:
    cases = (
        ([], "case_not_found"),
        ([{"case_no": "115000042"}, {"case_no": "115000042"}], "case_not_unique"),
        ([{"case_no": "115000999"}], "case_not_unique"),
    )

    for rows, expected_reason in cases:
        result = resolve_client_virtual_account(_Cursor(rows), "99781699115042")
        assert result == {
            "result": "pending",
            "case_no": None,
            "reason": expected_reason,
        }
