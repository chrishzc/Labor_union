"""Pure source-parser compatibility checks; no cursor or database execution."""

import pytest

from domains.finance_import.cancellation_code import resolve_finance_cancellation_code
from subsystems.client_finance.virtual_account_resolution import build_client_virtual_account
from subsystems.finance_import.case_manual_supplement import _bank_references


@pytest.mark.parametrize("bank", ["sinopac", "taishin"])
@pytest.mark.parametrize("case_no", ["115000001", "A115001"])
def test_manual_receipt_reference_is_readable_by_existing_owner_parser(bank, case_no):
    account = build_client_virtual_account(case_no)
    assert account is not None
    references = _bank_references(bank, "", account, "")
    result = resolve_finance_cancellation_code({
        "format_id": bank, "bank_references": references, "cancellation_code": account,
    })
    assert result["cancellation_code"] == account
    assert references["source"] == "manual_supplement"
    assert references["reason"] == ""


def test_sinopac_parser_requires_the_original_reference_column():
    account = build_client_virtual_account("A115001")
    assert resolve_finance_cancellation_code({
        "format_id": "sinopac", "bank_references": {"source": "manual_supplement"},
        "cancellation_code": account,
    })["cancellation_code"] is None
