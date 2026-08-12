from __future__ import annotations

from pathlib import Path

import pytest

from scripts.seed_contract_signing_roots import _load_source, _require_database


def test_contract_signing_staff_root_is_declared_as_external_source():
    fact = _load_source(
        Path("validation/external_inputs/contract_signing_staff_master_v1.json")
    )

    assert fact.identity_card == "T100000001"
    assert fact.birthday.isoformat() == "1988-01-15"


def test_contract_signing_root_seed_requires_a_confirmed_disposable_database():
    _require_database(
        "lu_test_dataset_contract_signing_v3",
        "lu_test_dataset_contract_signing_v3",
    )
    with pytest.raises(ValueError, match="confirmation"):
        _require_database("lu_test_dataset_contract_signing_v3", "different")
