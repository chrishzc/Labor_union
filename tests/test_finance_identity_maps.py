import pytest

from services.finance_identity_maps import load_finance_identity_maps


class Cursor:
    def __init__(self, client_rows=None, staff_rows=None):
        self.responses = iter([client_rows or [], staff_rows or []])
        self.current = []
        self.executed = []

    def execute(self, sql):
        compact = " ".join(sql.split())
        self.executed.append(compact)
        self.current = next(self.responses)

    def fetchall(self):
        return list(self.current)


def test_loads_only_unsettled_client_obligations_from_beclass_case_join():
    cursor = Cursor(
        client_rows=[
            {"client_payment_id": 7, "refund_account_no": "001234"},
            {"client_payment_id": 3, "refund_account_no": "001234"},
        ]
    )

    result = load_finance_identity_maps(cursor)

    assert result["client_refund_accounts"] == {"001234": [3, 7]}
    sql = cursor.executed[0]
    assert "JOIN beclass_records br ON br.query_no=cp.case_no" in sql
    assert "cp.subsidy_return_receivable > cp.subsidy_return_refunded" in sql
    assert "br.refund_account_no" in sql


def test_staff_mapping_includes_every_registered_account_without_primary_filter():
    cursor = Cursor(
        staff_rows=[
            {"staff_id": 9, "account_no": "10001", "is_primary": 1},
            {"staff_id": 9, "account_no": "10002", "is_primary": 0},
        ]
    )

    result = load_finance_identity_maps(cursor)

    assert result["staff_accounts"] == {"10001": [9], "10002": [9]}
    assert "is_primary" not in cursor.executed[1]


def test_nfkc_and_trim_are_the_only_account_normalization():
    cursor = Cursor(
        client_rows=[
            {"client_payment_id": 1, "refund_account_no": "  ００１２－３４  "},
        ],
        staff_rows=[
            {"staff_id": 2, "account_no": "\u3000００１２－３４\u3000"},
        ],
    )

    result = load_finance_identity_maps(cursor)

    assert result == {
        "client_refund_accounts": {"0012-34": [1]},
        "staff_accounts": {"0012-34": [2]},
    }


def test_leading_zeroes_and_internal_format_are_preserved_without_guessing():
    cursor = Cursor(
        client_rows=[
            {"client_payment_id": 1, "refund_account_no": "001234"},
            {"client_payment_id": 2, "refund_account_no": "1234"},
            {"client_payment_id": 3, "refund_account_no": "00 1234"},
        ]
    )

    result = load_finance_identity_maps(cursor)

    assert result["client_refund_accounts"] == {
        "00 1234": [3],
        "001234": [1],
        "1234": [2],
    }


def test_all_distinct_candidates_for_the_same_account_are_kept_and_sorted():
    cursor = Cursor(
        client_rows=[
            {"client_payment_id": 8, "refund_account_no": "A"},
            {"client_payment_id": 2, "refund_account_no": "A"},
            {"client_payment_id": 8, "refund_account_no": "A"},
        ],
        staff_rows=[
            {"staff_id": 7, "account_no": "A"},
            {"staff_id": 1, "account_no": "A"},
            {"staff_id": 7, "account_no": "A"},
        ],
    )

    result = load_finance_identity_maps(cursor)

    assert result == {
        "client_refund_accounts": {"A": [2, 8]},
        "staff_accounts": {"A": [1, 7]},
    }


@pytest.mark.parametrize("empty", [None, "", "   ", "\u3000"])
def test_empty_accounts_are_ignored_after_normalization(empty):
    cursor = Cursor(
        client_rows=[{"client_payment_id": 1, "refund_account_no": empty}],
        staff_rows=[{"staff_id": 2, "account_no": empty}],
    )

    result = load_finance_identity_maps(cursor)

    assert result == {"client_refund_accounts": {}, "staff_accounts": {}}


def test_numeric_account_is_not_converted_or_zero_padded():
    cursor = Cursor(
        client_rows=[{"client_payment_id": 1, "refund_account_no": 1234}],
        staff_rows=[{"staff_id": 2, "account_no": 5678}],
    )

    result = load_finance_identity_maps(cursor)

    assert result == {"client_refund_accounts": {}, "staff_accounts": {}}


def test_queries_are_strictly_read_only_and_do_not_use_names():
    cursor = Cursor(
        client_rows=[
            {"client_payment_id": 1, "refund_account_no": "A", "name": "客戶"}
        ],
        staff_rows=[{"staff_id": 2, "account_no": "B", "name": "服務人員"}],
    )

    load_finance_identity_maps(cursor)

    assert len(cursor.executed) == 2
    assert all(sql.startswith("SELECT") for sql in cursor.executed)
    assert all("name" not in sql.lower() for sql in cursor.executed)
    assert all(
        keyword not in " ".join(cursor.executed).upper()
        for keyword in ("INSERT ", "UPDATE ", "DELETE ", "REPLACE ")
    )


def test_result_key_and_candidate_order_is_stable():
    cursor = Cursor(
        client_rows=[
            {"client_payment_id": 3, "refund_account_no": "Z"},
            {"client_payment_id": 2, "refund_account_no": "A"},
        ],
        staff_rows=[
            {"staff_id": 4, "account_no": "Z"},
            {"staff_id": 1, "account_no": "A"},
        ],
    )

    result = load_finance_identity_maps(cursor)

    assert list(result["client_refund_accounts"]) == ["A", "Z"]
    assert list(result["staff_accounts"]) == ["A", "Z"]


def test_invalid_identity_id_is_rejected_instead_of_silently_guessed():
    cursor = Cursor(client_rows=[{"client_payment_id": "7", "refund_account_no": "A"}])

    with pytest.raises(ValueError, match="client_payment_id"):
        load_finance_identity_maps(cursor)
