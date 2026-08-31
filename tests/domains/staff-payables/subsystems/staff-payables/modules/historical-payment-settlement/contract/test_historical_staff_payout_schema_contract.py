from __future__ import annotations

from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from scripts.schema_assembly import load_schema_assembly
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "pyproject.toml").is_file()
)
PART_NAME = "1020_historical_owner_payment_settlement.sql"
MANIFEST_PATH = (
    ROOT
    / "db/migration_releases/labor_union_2026_08_31_historical_owner_payment_settlement_v1.json"
)


def test_staff_historical_payout_release_is_hash_bound_and_terminal() -> None:
    manifest = load_migration_release_manifest(MANIFEST_PATH, ROOT)
    assert manifest.schema_paths(ROOT) == (
        (ROOT / "db/schema_parts" / PART_NAME).resolve(),
    )
    assert manifest.backfills == ()
    assert load_schema_assembly().active_artifact_paths[-1].name == PART_NAME

    released = manifest.owned_object_descriptors(ROOT)[PART_NAME]
    canonical = migration._canonical_artifact_descriptor(PART_NAME)
    staff_tables = {
        name for name in canonical["tables"] if name.startswith("historical_staff_")
    }
    assert staff_tables == {
        "historical_staff_payout_events",
        "historical_staff_payout_obligation_links",
        "historical_staff_payout_projections",
        "historical_staff_payout_source_outbox",
    }
    assert {name for name in released["tables"] if name.startswith("historical_staff_")} == staff_tables
    for kind in ("indexes", "foreign_keys", "checks"):
        assert released[kind] == canonical[kind]
    assert released["triggers"] == set(canonical["triggers"])


def test_staff_historical_payout_keeps_exact_staff_owner_evidence() -> None:
    sql = (ROOT / "db/schema_parts" / PART_NAME).read_text(encoding="utf-8")
    assert "payer_role ENUM('union') NOT NULL" in sql
    assert "payee_role ENUM('staff') NOT NULL" in sql
    assert "payment_date IS NULL AND CHAR_LENGTH(TRIM(payment_date_unknown_reason)) > 0" in sql
    assert "REFERENCES historical_order_adoption_receipts(id)" in sql
    assert "REFERENCES staff_obligations(obligation_identity)" in sql
    assert "CREATE TABLE IF NOT EXISTS staff_payables_apply_receipts" not in sql
    assert "finance_import_row_id" not in sql
