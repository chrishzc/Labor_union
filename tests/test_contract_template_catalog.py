from __future__ import annotations

import json
from pathlib import Path

import pytest

from subsystems.contract_signing.template_catalog import load_approved_template


@pytest.mark.parametrize("template_key", ["contract_staff_service", "contract_client_copy"])
def test_approved_contract_template_has_stable_artifact_and_mapping_digests(template_key):
    template = load_approved_template(template_key)

    assert template.template_key == template_key
    assert len(template.template_sha256) == 64
    assert len(template.mapping_sha256) == 64
    assert template.template_filename.endswith(".xlsx")


def test_unapproved_contract_template_cannot_be_loaded():
    with pytest.raises(ValueError, match="not approved"):
        load_approved_template("arbitrary-local-file")


def test_client_template_uses_precontract_dates_not_execution_dates():
    mapping_path = Path("db/templates/contracts/contract_client_copy.json")
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    expected_keys = {
        "B7": "contract_signed_date",
        "B24": "committed_service_start_date",
        "D24": "committed_service_end_date",
        "B185": "contract_signed_date",
    }
    actual_keys = {
        cell: mapping["param_mappings"][cell]["db_key"]
        for cell in expected_keys
    }
    assert actual_keys == expected_keys
