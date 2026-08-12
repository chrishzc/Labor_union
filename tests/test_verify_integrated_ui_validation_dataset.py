import pytest

from scripts.verify_integrated_ui_validation_dataset import _checks, _require_dataset_database


def test_integrated_verifier_rejects_non_validation_database():
    with pytest.raises(ValueError, match="lu_test_dataset"):
        _require_dataset_database("union_db")


def test_integrated_verifier_requires_every_normal_chain_projection():
    observed = {
        "order": {"status": "訂單成立", "contract_identity": "client-contract:hash"},
        "signing": {"documents": 4, "sent": 2, "signed_received": 2},
        "commitment_days": 5,
        "availability_lock": {"status": "converted", "is_active": None},
        "assignment": {"count": 1, "status": "planned", "staff_id": 8892},
        "official_days": 5,
        "client_obligation": {"amount_due_ntd": 0, "status": "settled"},
        "staff_obligation": {"amount_due_ntd": 12000, "status": "open"},
    }

    assert all(item["passed"] for item in _checks(observed))
