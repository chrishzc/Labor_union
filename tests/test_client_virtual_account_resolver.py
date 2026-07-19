import pytest

from services.client_virtual_account_resolver import resolve_client_virtual_account


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))

    def fetchall(self):
        return self.rows


@pytest.mark.parametrize(
    ("virtual_account", "expected_case_no"),
    [
        ("99781699115001", "115000001"),
        ("99781699115010", "115000010"),
        ("99781699115100", "115000100"),
        ("99781699000000", "000000000"),
    ],
)
def test_resolves_exact_virtual_account_to_unique_order(virtual_account, expected_case_no):
    cursor = FakeCursor([{"case_no": expected_case_no}])

    result = resolve_client_virtual_account(cursor, virtual_account)

    assert result == {"result": "resolved", "case_no": expected_case_no, "reason": None}
    assert cursor.calls == [
        ("SELECT case_no FROM orders WHERE case_no = %s", (expected_case_no,))
    ]


@pytest.mark.parametrize(
    "value",
    [
        None,
        99781699115001,
        "",
        " 99781699115001",
        "99781699115001 ",
        "9978169911500",
        "997816991150010",
        "99781698115001",
        "99781699１１５００１",
        "99781699115A01",
    ],
)
def test_invalid_format_stays_pending_without_query(value):
    cursor = FakeCursor([])

    result = resolve_client_virtual_account(cursor, value)

    assert result == {
        "result": "pending",
        "case_no": None,
        "reason": "invalid_virtual_account_format",
    }
    assert cursor.calls == []


def test_missing_order_stays_pending():
    cursor = FakeCursor([])

    result = resolve_client_virtual_account(cursor, "99781699115001")

    assert result == {"result": "pending", "case_no": None, "reason": "case_not_found"}
    assert len(cursor.calls) == 1


def test_multiple_order_matches_stay_pending():
    cursor = FakeCursor([{"case_no": "115000001"}, {"case_no": "115000001"}])

    result = resolve_client_virtual_account(cursor, "99781699115001")

    assert result == {"result": "pending", "case_no": None, "reason": "case_not_unique"}


def test_mismatched_database_row_stays_pending_and_never_writes():
    cursor = FakeCursor([("115000002",)])

    result = resolve_client_virtual_account(cursor, "99781699115001")

    assert result == {"result": "pending", "case_no": None, "reason": "case_not_unique"}
    assert all(call[0].startswith("SELECT ") for call in cursor.calls)
