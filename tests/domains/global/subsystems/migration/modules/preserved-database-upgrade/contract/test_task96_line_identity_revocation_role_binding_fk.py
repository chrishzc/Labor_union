"""Contract coverage for the Task 96 canonical LINE revocation FK successor."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[8]
MANIFEST_PATH = ROOT / (
    "db/migration_releases/"
    "labor_union_2026_09_01_task96_line_identity_revocation_role_binding_fk_v1.json"
)
DESCRIPTOR_PATH = MANIFEST_PATH.with_name(
    "labor_union_2026_09_01_task96_line_identity_revocation_role_binding_fk_v1.descriptors.json"
)
SQL_PATH = ROOT / "db/schema_parts/1024_task96_line_identity_revocation_role_binding_fk.sql"


def test_task96_revocation_fk_release_targets_canonical_role_binding() -> None:
    manifest = load_migration_release_manifest(MANIFEST_PATH, ROOT)
    descriptor = json.loads(DESCRIPTOR_PATH.read_text(encoding="utf-8"))
    artifact = manifest.schema_artifacts[0].artifact
    foreign_key = descriptor["descriptors"][artifact.name]["foreign_keys"][
        "line_identity_revocation_requests.fk_line_identity_revocation_role_binding"
    ]

    assert manifest.release_id == (
        "labor-union-task96-line-identity-revocation-role-binding-fk-2026-09-01-v1"
    )
    assert artifact.sha256 == hashlib.sha256(SQL_PATH.read_bytes()).hexdigest()
    assert foreign_key["columns"] == ["line_user_id", "subject_type"]
    assert foreign_key["referenced_table"] == "line_identity_role_bindings"
    assert foreign_key["referenced_columns"] == ["line_user_id", "subject_type"]
    assert foreign_key["update_rule"] == "RESTRICT"
    assert foreign_key["delete_rule"] == "RESTRICT"
