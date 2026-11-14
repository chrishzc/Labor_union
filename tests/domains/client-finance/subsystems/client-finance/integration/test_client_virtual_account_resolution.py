import sqlite3

import pytest

from subsystems.client_finance.virtual_account_resolution import (
    build_client_virtual_account,
    resolve_case_virtual_account,
    resolve_client_virtual_account,
    resolve_client_virtual_account_suffix,
    resolve_formula_case_virtual_account,
)


class _Cursor:
    def __init__(self, *result_sets):
        self.result_sets = list(result_sets)
        self.executions = []

    def execute(self, statement, parameters):
        self.executions.append((statement, parameters))

    def fetchall(self):
        return self.result_sets.pop(0) if self.result_sets else []


def test_memo_suffix_uses_imported_virtual_account_mapping_before_formula():
    cursor = _Cursor([{"case_no": "114000018"}])
    result = resolve_client_virtual_account_suffix(cursor, "115001")
    assert result == {"result": "resolved", "case_no": "114000018", "reason": None}
    assert len(cursor.executions) == 1
    assert cursor.executions[0][1] == ("99781699115001",)


def test_memo_suffix_uses_existing_case_when_no_imported_mapping_exists():
    cursor = _Cursor([], [{"case_no": "116000001"}])
    assert resolve_client_virtual_account_suffix(cursor, "116001")["case_no"] == "116000001"
    assert cursor.executions[-1][1] == ("116000001",)


@pytest.mark.parametrize("suffix", [None, 115001, "11500", "1150010", "１１５００１"])
def test_invalid_memo_suffix_does_not_query_cases(suffix):
    cursor = _Cursor()
    assert resolve_client_virtual_account_suffix(cursor, suffix)["result"] == "pending"
    assert cursor.executions == []


def test_builds_contract_virtual_account_from_canonical_case_number():
    assert build_client_virtual_account("115000157") == "99781699115157"


@pytest.mark.parametrize(("case_no", "account"), [
    ("A115001", "99781699115501"), ("A115002", "99781699115502"),
    ("A116001", "99781699116501"), ("A115499", "99781699115999"),
])
def test_non_citizen_virtual_account_uses_year_and_sequence_plus_500(case_no, account):
    assert build_client_virtual_account(case_no) == account
    assert resolve_client_virtual_account(_Cursor([], [{"case_no": case_no}]), account) == {
        "result": "resolved", "case_no": case_no, "reason": None,
    }


def test_non_citizen_suffix_does_not_treat_case_digits_as_virtual_account_suffix():
    assert resolve_client_virtual_account_suffix(_Cursor([], [{"case_no": "A115001"}]), "115001")["result"] == "pending"
    assert resolve_client_virtual_account_suffix(_Cursor([], [{"case_no": "A115001"}]), "115501")["case_no"] == "A115001"


def test_non_citizen_formula_never_overrides_imported_mapping_or_ambiguous_cases():
    assert resolve_client_virtual_account(_Cursor([{"case_no": "114000018"}]), "99781699115501")["case_no"] == "114000018"
    assert resolve_client_virtual_account(_Cursor([], [{"case_no": "116000501"}, {"case_no": "A116001"}]),
                                        "99781699116501")["reason"] == "case_not_unique"


@pytest.mark.parametrize("case_no", [None, "CASE-1", "115001234", "１１５０００１５７"])
def test_virtual_account_builder_rejects_unrepresentable_case_number(case_no):
    assert build_client_virtual_account(case_no) is None


@pytest.mark.parametrize("value", [None, 99781699114001, "9978169911400X", "99781699114001 "])
def test_invalid_virtual_account_does_not_query_orders(value):
    cursor = _Cursor([])

    assert resolve_client_virtual_account(cursor, value) == {
        "result": "pending",
        "case_no": None,
        "reason": "invalid_virtual_account_format",
    }
    assert cursor.executions == []


def test_resolves_virtual_account_to_roc_year_and_padded_sequence():
    cursor = _Cursor([], [{"case_no": "116000001"}])

    assert resolve_client_virtual_account(cursor, "99781699116001") == {
        "result": "resolved",
        "case_no": "116000001",
        "reason": None,
    }
    assert [params for _, params in cursor.executions] == [
        ("99781699116001",), ("116000001",),
    ]


def test_cases_with_imported_accounts_cannot_be_resolved_by_their_formula():
    from subsystems.finance_import.identity_maps import _known_case_virtual_accounts

    class SqliteCursor:
        def __init__(self, database):
            self.cursor = database.cursor()

        def execute(self, statement, parameters=()):
            self.cursor.execute(statement.replace("%s", "?"), parameters)

        def fetchall(self):
            return [dict(row) for row in self.cursor.fetchall()]

    with sqlite3.connect(":memory:") as database:
        database.row_factory = sqlite3.Row
        database.executescript("""
            CREATE TABLE orders (case_no TEXT, client_id INTEGER);
            CREATE TABLE client_legacy_virtual_accounts (case_no TEXT, virtual_account TEXT);
            INSERT INTO orders VALUES ('115000001', 1), ('115000002', 2), ('115000003', 3),
                ('116000001', 4), ('116000009', 5), ('A115001', 6), ('115000004', 7);
            INSERT INTO client_legacy_virtual_accounts VALUES
                ('115000001', '99781699115009'),
                ('115000003', '99781699115007'),
                ('115000003', '99781699115008'),
                ('115000004', '99781699116009'),
                ('116000001', '99781699116008'),
                ('A115001', '99781699115006');
        """)
        cursor = SqliteCursor(database)
        assert resolve_client_virtual_account(cursor, "99781699115009")["case_no"] == "115000001"
        assert resolve_client_virtual_account(cursor, "99781699115001")["result"] == "pending"
        assert resolve_client_virtual_account(cursor, "99781699115002")["result"] == "pending"
        assert resolve_client_virtual_account(cursor, "99781699115007")["reason"] == "case_not_unique"
        assert resolve_client_virtual_account(cursor, "99781699115003")["result"] == "pending"
        assert resolve_case_virtual_account(cursor, "115000002")["reason"] == "imported_account_missing"
        assert resolve_case_virtual_account(cursor, "116000001")["virtual_account"] == "99781699116001"
        assert resolve_case_virtual_account(cursor, "A115001")["virtual_account"] == "99781699115006"
        assert resolve_formula_case_virtual_account(cursor, "A115001") == "99781699115501"
        assert resolve_client_virtual_account(cursor, "99781699115006")["case_no"] == "A115001"
        assert resolve_client_virtual_account_suffix(cursor, "115501")["result"] == "pending"
        assert resolve_case_virtual_account(cursor, "116000009")["result"] == "pending"
        assert resolve_client_virtual_account(cursor, "99781699116009")["case_no"] == "115000004"
        known_accounts, _, _, case_suffixes = _known_case_virtual_accounts(cursor)
        assert known_accounts == {"99781699115009", "99781699116001", "99781699115006", "99781699116009"}
        assert case_suffixes["A115001"] == "115006"
        assert "116000009" not in case_suffixes


@pytest.mark.parametrize(
    ("generated_matches", "reason"),
    [([], "case_not_found"), ([{"case_no": "other"}], "case_not_found")],
)
def test_virtual_account_requires_one_matching_canonical_case(generated_matches, reason):
    assert resolve_client_virtual_account(_Cursor([], generated_matches), "99781699114001") == {
        "result": "pending",
        "case_no": None,
        "reason": reason,
    }


def test_resolves_an_imported_legacy_account_to_its_order():
    assert resolve_client_virtual_account(
        _Cursor([{"case_no": "114000018"}]), "99781699114033"
    ) == {"result": "resolved", "case_no": "114000018", "reason": None}


def test_imported_account_wins_when_formula_points_to_a_different_case():
    assert resolve_client_virtual_account(
        _Cursor([{"case_no": "114000018"}], [{"case_no": "114000033"}]),
        "99781699114033",
    ) == {"result": "resolved", "case_no": "114000018", "reason": None}


def test_same_case_from_both_rules_is_not_ambiguous():
    assert resolve_client_virtual_account(
        _Cursor([{"case_no": "114000033"}], [{"case_no": "114000033"}]),
        "99781699114033",
    ) == {"result": "resolved", "case_no": "114000033", "reason": None}


def test_multiple_imported_cases_stay_pending_without_formula_fallback():
    cursor = _Cursor(
        [{"case_no": "114000018"}, {"case_no": "114000019"}],
        [{"case_no": "114000033"}],
    )

    assert resolve_client_virtual_account(cursor, "99781699114033") == {
        "result": "pending",
        "case_no": None,
        "reason": "case_not_unique",
    }
    assert len(cursor.executions) == 1


def test_case_projection_prefers_its_unique_imported_account():
    cursor = _Cursor([{"virtual_account": "99781699114991"}], [{"case_no": "114000033"}])

    assert resolve_case_virtual_account(cursor, "114000033") == {
        "result": "resolved",
        "virtual_account": "99781699114991",
        "reason": None,
    }


def test_case_projection_rejects_multiple_imported_accounts_without_formula_fallback():
    cursor = _Cursor([
        {"virtual_account": "99781699114991"},
        {"virtual_account": "99781699114992"},
    ])

    assert resolve_case_virtual_account(cursor, "114000033") == {
        "result": "pending",
        "virtual_account": None,
        "reason": "imported_account_not_unique",
    }


def test_case_projection_uses_formula_for_116_cases():
    assert resolve_case_virtual_account(_Cursor([], [{"case_no": "116000033"}]), "116000033") == {
        "result": "resolved",
        "virtual_account": "99781699116033",
        "reason": None,
    }
