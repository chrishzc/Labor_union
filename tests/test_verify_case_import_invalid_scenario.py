from scripts.verify_case_import_invalid_scenario import _checks


def test_invalid_case_import_verifier_requires_a_masked_open_review_root():
    observed = {
        "review": {
            "identifier": "client-***-0001",
            "source_payload": '{"query_no":null,"validation_marker":"missing_query_no"}',
            "issue_codes": '["missing_query_no"]',
            "outbox_count": 1,
        },
        "root_counts": {"clients": 1, "orders": 1, "client_finance_accounts": 1},
    }

    assert all(check["passed"] for check in _checks(observed))
