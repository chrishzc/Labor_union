from scripts.verify_finance_manual_review_scenario import _checks


def test_finance_manual_review_verifier_requires_open_repair_and_owner_correction():
    observed = {
        "events": [
            {"classification_type": "non_business_review", "disposition": "manual_review"},
            {"classification_type": "client_receipt", "disposition": "create"},
        ],
    }

    assert all(check["passed"] for check in _checks(observed))
