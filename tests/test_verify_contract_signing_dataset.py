from __future__ import annotations

import pytest

from scripts.verify_contract_signing_dataset import _checks, _require_dataset_database


def test_contract_signing_verifier_accepts_only_disposable_dataset_databases():
    assert _require_dataset_database("lu_test_dataset_contract_signing_v2") == "lu_test_dataset_contract_signing_v2"

    with pytest.raises(ValueError, match="lu_test_dataset"):
        _require_dataset_database("union_db")


def test_contract_signing_verifier_requires_clean_precontract_baseline():
    table_counts = {
        "contract_document_versions": 0,
        "contract_signing_events": 0,
        "precontract_service_commitments": 0,
        "precontract_service_commitment_days": 0,
        "precontract_service_commitment_events": 0,
    }
    order = {"status": "洽談中", "contract_identity": None}

    assert all(item["passed"] for item in _checks(table_counts, order))
