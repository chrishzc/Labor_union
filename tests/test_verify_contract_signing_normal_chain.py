from scripts.verify_contract_signing_normal_chain import _checks


def test_normal_chain_verifier_requires_the_complete_contract_to_execution_lineage():
    observed = {
        "archive_digest_count": 4,
        "staff_signed_count": 1,
        "client_signed_count": 1,
        "commitment_count": 1,
        "converted_commitment_count": 1,
        "settled_deposit_count": 1,
        "assignment_count": 1,
        "schedule_day_count": 5,
    }

    assert all(check["passed"] for check in _checks(observed, {"contract_identity": "client-contract:digest"}))


def test_normal_chain_verifier_rejects_execution_without_a_converted_commitment():
    observed = {
        "archive_digest_count": 4,
        "staff_signed_count": 1,
        "client_signed_count": 1,
        "commitment_count": 1,
        "converted_commitment_count": 0,
        "settled_deposit_count": 1,
        "assignment_count": 1,
        "schedule_day_count": 5,
    }

    assert not all(check["passed"] for check in _checks(observed, {"contract_identity": "client-contract:digest"}))
