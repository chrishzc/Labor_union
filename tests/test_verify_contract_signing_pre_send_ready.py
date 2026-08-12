from scripts.verify_contract_signing_pre_send_ready import _checks, _require_dataset_database


def test_pre_send_verifier_only_accepts_disposable_dataset_databases():
    assert _require_dataset_database("lu_test_dataset_contract_signing_v4") == "lu_test_dataset_contract_signing_v4"


def test_client_signed_verifier_requires_commitment_without_execution_data():
    observations = {
        "matching_plan": {"status": "proposed", "segment_count": 1},
        "bound_recipients": 2,
        "contract_documents": 4,
        "signing_events": 4,
        "commitments": 1,
        "contract_identity": "client-contract:fixture",
        "execution_assignments": 0,
        "official_schedule_days": 0,
    }

    assert all(check["passed"] for check in _checks(observations))
