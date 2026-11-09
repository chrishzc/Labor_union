from unittest.mock import Mock

import pytest
from pymysql.err import OperationalError

from subsystems.finance_import.identity_maps import load_finance_identity_maps


@pytest.mark.parametrize("query", [
    "COALESCE(projection.balance_ntd", "SELECT id,name FROM staff", "SELECT id,name FROM clients",
    "SELECT case_no FROM orders", "SELECT case_no, virtual_account FROM client_legacy_virtual_accounts",
    "SELECT order_row.client_id, client.name, obligation.case_no",
])
def test_identity_query_failure_is_not_a_successful_empty_candidate_set(query):
    cursor = Mock()
    cursor.fetchall.return_value = []

    def execute(statement, *_):
        if query in " ".join(statement.split()):
            raise OperationalError(1054, "synthetic identity query failure")

    cursor.execute.side_effect = execute
    with pytest.raises(OperationalError, match="synthetic identity query failure"):
        load_finance_identity_maps(cursor)


def test_successfully_queried_empty_directory_remains_a_valid_empty_result():
    cursor = Mock()
    cursor.fetchall.return_value = []
    maps = load_finance_identity_maps(cursor)
    assert maps["staff_payout_candidates"] == maps["taishin_client_refund_candidates"] == ()
    assert maps["staff_name_identities"] == maps["client_name_identities"] == {}
    assert maps["known_virtual_accounts"] == frozenset()
