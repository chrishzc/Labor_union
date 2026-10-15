"""Retirement accepts historical presence/absence without weakening retained facts."""

from copy import deepcopy

from scripts import migrate_preserved_database_additive_schema as migration


def snapshot(columns=()):
    return {"columns": list(columns), "indexes": [], "constraints": [], "key_columns": [],
            "foreign_keys": [], "triggers": [], "show_create_tables": {}, "views": []}


def test_retired_artifact_presence_or_absence_requires_no_upgrade_and_keeps_descriptor():
    artifact = "147_access_capability_grants.sql"
    descriptor = migration._canonical_artifact_descriptor(artifact)
    before = deepcopy(descriptor)
    assert migration.local_additive_descriptor_state(snapshot(), descriptor, artifact) == "exact"
    historical = snapshot([{"table_name": "access_control_apply_receipts", "column_name": "idempotency_key"}])
    assert migration.local_additive_descriptor_state(historical, descriptor, artifact) == "exact"
    assert descriptor == before


def test_mixed_retirement_projection_still_checks_retained_columns():
    column = {"column_type": "varchar(191)", "is_nullable": "NO", "column_default": None, "extra": ""}
    descriptor = {"tables": {}, "parent_columns": {
        "government_payers": {"payer_identity": column},
        "government_payer_receiving_accounts": {"payer_identity": column}},
        "indexes": {}, "foreign_keys": {}, "checks": {}, "triggers": {}, "views": {}}
    before = deepcopy(descriptor)
    row = {"table_name": "government_payers", "column_name": "payer_identity", **column}
    classify = lambda state: migration.local_additive_descriptor_state(state, descriptor, "synthetic_mixed_retirement.sql")
    assert classify(snapshot([row])) == "exact"
    assert classify(snapshot()) == "absent"
    assert classify(snapshot([{**row, "column_type": "varchar(50)"}])) == "drift"
    assert descriptor == before
