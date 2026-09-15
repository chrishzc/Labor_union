import json
from pathlib import Path


def test_client_contract_dates_are_planned_due_dates_not_receipt_dates():
    root = Path(__file__).resolve().parents[6]
    mapping = json.loads(
        (root / "db/templates/contracts/contract_client_copy.json").read_text(encoding="utf-8")
    )["param_mappings"]

    payment_date_keys = {mapping[cell]["db_key"] for cell in ("C34", "C35", "C36", "C37")}

    assert payment_date_keys == {
        "deposit_due_date",
        "first_payment_due_date",
        "second_payment_due_date",
    }
    assert all("receipt" not in key for key in payment_date_keys)
