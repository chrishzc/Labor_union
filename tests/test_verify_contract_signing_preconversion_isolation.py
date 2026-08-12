import pytest

from scripts.verify_contract_signing_preconversion_isolation import _checks, _require_dataset_database


def test_preconversion_isolation_requires_only_a_not_yet_converted_commitment():
    observed = {
        "commitment_count": 1,
        "converted_commitment_count": 0,
        "assignment_count": 0,
        "calendar_schedule_count": 0,
        "payroll_execution_count": 0,
        "subsidy_claim_item_count": 0,
    }

    assert all(check["passed"] for check in _checks(observed))


def test_preconversion_isolation_rejects_any_downstream_execution_root():
    observed = {
        "commitment_count": 1,
        "converted_commitment_count": 0,
        "assignment_count": 0,
        "calendar_schedule_count": 1,
        "payroll_execution_count": 0,
        "subsidy_claim_item_count": 0,
    }

    assert not all(check["passed"] for check in _checks(observed))


def test_preconversion_isolation_rejects_non_validation_database():
    with pytest.raises(ValueError, match="lu_test_dataset"):
        _require_dataset_database("union_db")
