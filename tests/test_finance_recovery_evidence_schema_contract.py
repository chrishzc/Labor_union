"""
File: test_finance_recovery_evidence_schema_contract.py
Description: 驗證財務追償 evidence release 的 hash、descriptor 與 fresh assembly 順序。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "db/schema_parts/1007_finance_recovery_evidence.sql"
MANIFEST_PATH = ROOT / "db/migration_releases/labor_union_2026_08_26_finance_recovery_evidence_v1.json"
DESCRIPTOR_PATH = ROOT / "db/migration_releases/labor_union_2026_08_26_finance_recovery_evidence_v1.descriptors.json"
ASSEMBLY_PATH = ROOT / "db/schema_assembly/labor_union_fresh_schema_v1.json"

TABLES = {
    "client_over_refund_recovery_events",
    "client_over_refund_recovery_matchings",
    "staff_overpayment_recovery_events",
    "staff_overpayment_recovery_matchings",
}


def test_release_is_schema_only_and_registered_before_its_successor() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    descriptor = json.loads(DESCRIPTOR_PATH.read_text(encoding="utf-8"))
    assembly = json.loads(ASSEMBLY_PATH.read_text(encoding="utf-8"))

    assert manifest["release_id"] == "labor-union-finance-recovery-evidence-2026-08-26-v1"
    assert manifest["artifacts"][0]["sha256"] == hashlib.sha256(SQL_PATH.read_bytes()).hexdigest()
    assert manifest["artifacts"][0]["data_effect"] == "schema_only"
    assert manifest["backfills"] == []
    assert manifest["descriptor_artifact"]["sha256"] == hashlib.sha256(
        DESCRIPTOR_PATH.read_bytes()
    ).hexdigest()
    assert descriptor["release_id"] == manifest["release_id"]
    assert descriptor["descriptors"][SQL_PATH.name]["tables"] == {}
    evidence_part = "db/schema_parts/1007_finance_recovery_evidence.sql"
    successor_part = "db/schema_parts/1008_historical_order_adoption_noop_constraint.sql"
    assert evidence_part in assembly["active_bootstrap"]
    assert assembly["active_bootstrap"].index(evidence_part) < assembly["active_bootstrap"].index(
        successor_part
    )


def test_descriptor_covers_every_altered_parent_column_and_check() -> None:
    descriptor = migration._canonical_artifact_descriptor(SQL_PATH.name)

    assert set(descriptor["parent_columns"]) == TABLES
    assert all(
        columns == {
            "evidence_reference": {
                "column_type": "varchar(500)",
                "is_nullable": "YES",
                "column_default": None,
                "extra": "",
            }
        }
        for columns in descriptor["parent_columns"].values()
    )
    assert {table for table, _ in descriptor["checks"]} == TABLES


def test_schema_requires_nonblank_evidence_when_present() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")

    assert sql.count("ADD COLUMN evidence_reference VARCHAR(500) NULL") == 4
    assert sql.count("CHAR_LENGTH(TRIM(evidence_reference)) > 0") == 4
