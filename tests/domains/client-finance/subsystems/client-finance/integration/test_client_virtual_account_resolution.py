import pytest

from subsystems.client_finance.virtual_account_resolution import (
    build_client_virtual_account,
    resolve_case_virtual_account,
    resolve_client_virtual_account,
)


class _Cursor:
    def __init__(self, *result_sets):
        self.result_sets = list(result_sets)
        self.executions = []

    def execute(self, statement, parameters):
        self.executions.append((statement, parameters))

    def fetchall(self):
        return self.result_sets.pop(0) if self.result_sets else []


def test_builds_contract_virtual_account_from_canonical_case_number():
    assert build_client_virtual_account("115000157") == "99781699115157"


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
    cursor = _Cursor([], [{"case_no": "114000001"}])

    assert resolve_client_virtual_account(cursor, "99781699114001") == {
        "result": "resolved",
        "case_no": "114000001",
        "reason": None,
    }
    assert cursor.executions == [
        ("SELECT case_no FROM client_legacy_virtual_accounts WHERE virtual_account = %s ORDER BY case_no", ("99781699114001",)),
        ("SELECT case_no FROM orders WHERE case_no = %s", ("114000001",)),
    ]


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
    cursor = _Cursor([{"virtual_account": "99781699114991"}])

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


def test_case_projection_uses_formula_only_without_an_imported_account():
    assert resolve_case_virtual_account(_Cursor([]), "114000033") == {
        "result": "resolved",
        "virtual_account": "99781699114033",
        "reason": None,
    }
