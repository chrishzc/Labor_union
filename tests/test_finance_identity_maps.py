import pytest

from subsystems.finance_import.identity_maps import load_finance_identity_maps


class Cursor:
    def __init__(self, subsidy_rows=None, refund_rows=None, staff_rows=None, receipt_rows=None):
        self.responses = iter([subsidy_rows or [], refund_rows or [], staff_rows or [], receipt_rows or []])
        self.current = []
        self.executed = []

    def execute(self, sql):
        self.executed.append(" ".join(sql.split()))
        self.current = next(self.responses)

    def fetchall(self):
        return list(self.current)


def test_maps_general_refund_and_subsidy_return_accounts_separately():
    cursor = Cursor(
        subsidy_rows=[{"client_id": 7, "refund_account_no": "001234"}],
        refund_rows=[
            {"client_id": 3, "refund_account_no": "001234"},
            {"client_id": 3, "refund_account_no": "001234"},
        ],
    )

    result = load_finance_identity_maps(cursor)

    assert result["client_refund_accounts"] == {"001234": [3]}
    assert result["client_subsidy_return_accounts"] == {"001234": [7]}
    assert "JOIN orders order_row ON order_row.case_no=obligation.case_no" in cursor.executed[0]
    assert "obligation.obligation_type='subsidy_return'" in cursor.executed[0]
    assert "obligation.obligation_type IN ('refund','adjustment')" in cursor.executed[1]


def test_staff_mapping_keeps_every_registered_account():
    cursor = Cursor(staff_rows=[
        {"staff_id": 9, "account_no": "10001"},
        {"staff_id": 9, "account_no": "10002"},
    ])

    assert load_finance_identity_maps(cursor)["staff_accounts"] == {"10001": [9], "10002": [9]}
    assert "is_primary" not in cursor.executed[2]


def test_account_normalization_is_limited_to_nfkc_and_surrounding_whitespace():
    cursor = Cursor(
        refund_rows=[{"client_id": 1, "refund_account_no": "  ００１２－３４  "}],
        staff_rows=[{"staff_id": 2, "account_no": "　００１２－３４　"}],
    )

    result = load_finance_identity_maps(cursor)

    assert result["client_refund_accounts"] == {"0012-34": [1]}
    assert result["staff_accounts"] == {"0012-34": [2]}


@pytest.mark.parametrize("invalid_id", [0, "7", True])
def test_invalid_client_identity_is_rejected(invalid_id):
    cursor = Cursor(refund_rows=[{"client_id": invalid_id, "refund_account_no": "A"}])

    with pytest.raises(ValueError, match="client_id"):
        load_finance_identity_maps(cursor)


def test_queries_are_read_only_and_do_not_use_names():
    cursor = Cursor(
        subsidy_rows=[{"client_id": 1, "refund_account_no": "A", "name": "客戶"}],
        refund_rows=[{"client_id": 2, "refund_account_no": "B", "name": "客戶"}],
        staff_rows=[{"staff_id": 3, "account_no": "C", "name": "服務人員"}],
    )

    load_finance_identity_maps(cursor)

    assert len(cursor.executed) == 4
    assert all(sql.startswith("SELECT") for sql in cursor.executed)


def test_receipt_candidates_expose_name_account_and_open_amount_as_evidence():
    cursor = Cursor(
        receipt_rows=[
            {
                "client_id": 4,
                "name": "王小美",
                "refund_account_no": "001234",
                "amount_due_ntd": 3000,
            },
            {
                "client_id": 4,
                "name": "王小美",
                "refund_account_no": "001234",
                "amount_due_ntd": 5000,
            },
        ],
    )

    result = load_finance_identity_maps(cursor)

    assert result["client_receipt_candidates"] == (
        {
            "client_id": 4,
            "name": "王小美",
            "account": "001234",
            "open_amounts": (3000, 5000),
        },
    )
    assert "client.name" in cursor.executed[3]
