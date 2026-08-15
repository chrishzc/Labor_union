"""
File: test_schema_assembly.py
Description: 驗證唯一 fresh schema catalog 的分類、順序與 fail-closed 契約。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.schema_assembly import (
    DEFAULT_ASSEMBLY_PATH,
    load_schema_assembly,
)
from scripts.verify_validation_schema_manifest import (
    load_manifest,
    selected_schema_parts,
)


def test_fresh_catalog_classifies_every_part_and_excludes_migration_only_parts() -> None:
    assembly = load_schema_assembly()
    artifact_names = [path.name for path in assembly.active_artifact_paths]

    assert set(assembly.classifications.values()) <= {
        "active-bootstrap", "migration-only", "retired",
    }
    assert assembly.classifications[
        "db/schema_parts/153_retire_empty_legacy_field_inventory.sql"
    ] == "migration-only"
    assert "153_retire_empty_legacy_field_inventory.sql" not in artifact_names
    assert artifact_names.index("186_line_identity_management.sql") < artifact_names.index(
        "179_line_identity_canonical_menu_publication.sql"
    )


def test_validation_manifest_reads_the_same_catalog_selection() -> None:
    assembly = load_schema_assembly()

    assert selected_schema_parts(load_manifest()) == list(assembly.active_artifact_paths)


def test_catalog_rejects_duplicate_active_artifact(tmp_path: Path) -> None:
    catalog = json.loads(DEFAULT_ASSEMBLY_PATH.read_text(encoding="utf-8"))
    catalog["active_bootstrap"].append(catalog["active_bootstrap"][0])
    catalog_path = tmp_path / "duplicate.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    with pytest.raises(ValueError, match="contains duplicates"):
        load_schema_assembly(catalog_path)


def test_catalog_rejects_an_unclassified_live_schema_part(tmp_path: Path) -> None:
    catalog = json.loads(DEFAULT_ASSEMBLY_PATH.read_text(encoding="utf-8"))
    catalog["active_bootstrap"].pop()
    catalog_path = tmp_path / "missing-part.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    with pytest.raises(ValueError, match="does not classify every schema part"):
        load_schema_assembly(catalog_path)


def test_catalog_rejects_a_removed_artifact_without_retirement_contract(
    tmp_path: Path,
) -> None:
    catalog = json.loads(DEFAULT_ASSEMBLY_PATH.read_text(encoding="utf-8"))
    catalog["retirement_contracts"].pop(
        "db/schema_parts/153_retire_empty_legacy_field_inventory.sql"
    )
    catalog_path = tmp_path / "missing-retirement-contract.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    with pytest.raises(ValueError, match="retirement contracts differ"):
        load_schema_assembly(catalog_path)


def test_validation_manifest_rejects_a_catalog_digest_mismatch() -> None:
    manifest = load_manifest()
    manifest["schema_assembly"] = {
        **manifest["schema_assembly"],
        "sha256": "0" * 64,
    }

    with pytest.raises(ValueError, match="digest differs"):
        selected_schema_parts(manifest)
