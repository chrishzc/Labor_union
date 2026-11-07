"""Pure metadata/text checks: no SQL, cursor, DB or provider execution."""
from copy import deepcopy
from pathlib import Path
import ast
import hashlib
import inspect
import runpy

import pytest
from scripts import migrate_preserved_database_additive_schema as migration
from scripts.build_validation_schema_release import verify_release
from scripts.compact_fresh_schema import load_compact_plan
from scripts.verify_validation_schema_manifest import load_manifest
from shared_kernel.migration_release import load_migration_release_manifest

ROOT = Path(__file__).resolve().parents[8]
ARTIFACT = "1073_contract_document_render_snapshot.sql"
ORIGINAL = "166_contract_signing_workflow.sql"
TABLE = "contract_document_versions"
CHECK = (TABLE, "chk_contract_document_render_source")
MANIFEST = ROOT / "db/migration_releases/labor_union_2026_11_06_controlled_purpose_media_reference_v1.json"
NEW_COLUMNS = {
    "render_source_kind", "render_source_snapshot", "render_source_snapshot_sha256",
    "render_source_sha256", "render_source_size_bytes",
}
# Reuse the adjacent pure metadata fixture; the module only defines tests/functions.
_snapshot = runpy.run_path(str(Path(__file__).with_name(
    "test_controlled_purpose_media_reference_schema.py"
)))["_snapshot"]


def test_release_binds_closed_source_and_preserves_original_contracts():
    release = load_migration_release_manifest(MANIFEST, ROOT)
    released = release.owned_object_descriptors(ROOT)[ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    assert {k: v for k, v in released.items() if k != "triggers"} == {
        k: v for k, v in canonical.items() if k != "triggers"
    }
    assert released["triggers"] == set(canonical["triggers"])
    assert release.backfills == ()
    fields = canonical["parent_columns"][TABLE]
    assert fields["render_source_kind"] == {
        "column_type": "enum('legacy_archived','render_snapshot')",
        "is_nullable": "NO", "column_default": "legacy_archived", "extra": "",
    }
    assert fields["render_source_snapshot"]["column_type"] == "json"
    assert fields["render_source_size_bytes"]["column_type"] == "bigint unsigned"
    assert fields["media_asset_id"] == {
        "column_type": "bigint", "is_nullable": "YES", "column_default": None, "extra": "",
    }
    original = migration._canonical_artifact_descriptor(ORIGINAL)
    assert set(fields) == set(original["tables"][TABLE]) | NEW_COLUMNS
    assert len(fields) == 22
    assert canonical["foreign_keys"] == {key: value for key, value in original["foreign_keys"].items() if key[0] == TABLE}
    assert len(canonical["foreign_keys"]) == 6
    assert len(canonical["checks"]) == 4
    assert len(canonical["triggers"]) == 2
    for key, clause in original["checks"].items():
        if key[0] == TABLE:
            assert canonical["checks"][key] == clause


def test_metadata_accepts_only_exact_legacy_or_complete_snapshot_parent():
    descriptor = migration._canonical_artifact_descriptor(ARTIFACT)
    state = lambda value: migration.local_additive_descriptor_state(value, descriptor, ARTIFACT)
    current = _snapshot(descriptor)
    assert state(current) == "exact"
    predecessor = deepcopy(descriptor)
    for name in NEW_COLUMNS:
        predecessor["parent_columns"][TABLE].pop(name)
    predecessor["parent_columns"][TABLE]["media_asset_id"]["is_nullable"] = "NO"
    predecessor["checks"].pop(CHECK)
    assert state(_snapshot(predecessor)) == "absent"
    for name, field, value in (
        ("media_asset_id", "column_type", "bigint unsigned"),
        ("media_asset_id", "is_nullable", "NO"),
        ("render_source_kind", "column_default", "render_snapshot"),
        ("render_source_snapshot", "column_type", "longtext"),
        ("render_source_size_bytes", "column_type", "bigint"),
    ):
        damaged = deepcopy(current)
        next(row for row in damaged["columns"] if row["column_name"] == name)[field] = value
        assert state(damaged) == "drift"
    for missing in (CHECK[1], "fk_contract_document_media_asset"):
        damaged = deepcopy(current)
        damaged["constraints"] = [row for row in damaged["constraints"] if row["constraint_name"] != missing]
        assert state(damaged) == "partial"
    damaged = deepcopy(current)
    damaged["triggers"] = damaged["triggers"][1:]
    assert state(damaged) == "partial"
    damaged = deepcopy(current)
    damaged["columns"] = [row for row in damaged["columns"] if row["column_name"] != "render_source_snapshot"]
    assert state(damaged) == "drift"
    damaged = deepcopy(current)
    next(row for row in damaged["constraints"] if row["constraint_name"] == CHECK[1])["check_clause"] = "media_asset_id IS NULL"
    assert state(damaged) == "drift"


def test_166_projection_accepts_selected_successor_and_retains_guards():
    original = migration._canonical_artifact_descriptor(ORIGINAL)
    assert migration._canonical_artifact_metadata_state(_snapshot(original), ORIGINAL) == "exact"
    successor = migration._canonical_artifact_descriptor(ARTIFACT)
    current = deepcopy(original)
    current["tables"][TABLE] = successor["parent_columns"][TABLE]
    current["checks"].update(successor["checks"])
    now = _snapshot(current)
    assert migration._canonical_artifact_metadata_state(now, ORIGINAL) == "exact"
    assert migration.local_additive_descriptor_state(now, original, ORIGINAL) == "exact"
    next(row for row in now["triggers"] if row["trigger_name"] == "trg_contract_document_versions_before_update")["action_statement"] = "BEGIN SET @unsafe=1; END"
    assert migration._canonical_artifact_metadata_state(now, ORIGINAL) == "drift"


def test_single_exact_alter_and_current_text_bind_same_snapshot_contract():
    statement, = migration.split_sql((ROOT / "db/schema_parts" / ARTIFACT).read_text())
    assert migration._local_classify_statement(statement) == "contract_render_snapshot_source_successor"
    with pytest.raises(migration.LocalAdditiveBlocked, match="noncanonical"):
        migration._local_classify_statement(statement.replace("BIGINT NULL", "BIGINT NOT NULL"))
    assert "DROP " not in statement.upper()
    for value in ("contract-render-source.v1", "canonical-xlsx-zip.v1", "$.source.matching_plan_id", "$.source.matching_segment_id", "$.source.facts_snapshot_sha256"):
        assert value in statement
    assert "JSON_LENGTH(render_source_snapshot) = 4" in statement
    assert "JSON_LENGTH(JSON_EXTRACT(render_source_snapshot, '$.source')) = 9" in statement
    assert "render_source_size_bytes IS NULL" in statement
    assert "render_source_size_bytes IS NOT NULL AND render_source_size_bytes > 0" in statement
    assert verify_release(load_manifest()) == []
    assert load_manifest()["schema_parts"]["terminal_artifact"] == ARTIFACT
    create, = (step["sql"] for step in load_compact_plan()["steps"] if step["sql"].startswith(f"CREATE TABLE `{TABLE}`"))
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    checks = migration._show_create_check_clauses(create)
    assert migration._normalize_check_contract(checks[CHECK]) == migration._normalize_check_contract(canonical["checks"][CHECK])
    assert "`media_asset_id` bigint DEFAULT NULL" in create
    assert "DEFAULT 'legacy_archived'" in create


def _mysql8_render_source_fixture():
    """Portable CHECK fixture using the two CAST spellings captured by MySQL 8."""
    create, = (step["sql"] for step in load_compact_plan()["steps"]
               if step["sql"].startswith(f"CREATE TABLE `{TABLE}`"))
    for column in ("matching_plan_id", "matching_segment_id"):
        original = f"CAST({column} AS CHAR)"
        assert create.count(original) == 1
        create = create.replace(original, f"cast(`{column}` as char charset utf8mb4)")
    return create, migration._show_create_check_clauses(create)[CHECK]


@pytest.mark.parametrize("context", [ARTIFACT, ORIGINAL])
@pytest.mark.parametrize("show_create", [False, True])
def test_mysql8_owned_check_rendering_uses_classifier_and_show_create_priority(context, show_create):
    successor = migration._canonical_artifact_descriptor(ARTIFACT)
    create, clause = _mysql8_render_source_fixture()
    # No global charset removal: the ordinary normalizer still distinguishes it.
    assert migration._normalize_check_contract(clause) != migration._normalize_check_contract(successor["checks"][CHECK])
    descriptor = migration._canonical_artifact_descriptor(context)
    current = deepcopy(descriptor)
    if context == ORIGINAL:
        current["tables"][TABLE] = successor["parent_columns"][TABLE]
        current["checks"].update(successor["checks"])
    snapshot = _snapshot(current)
    row = next(row for row in snapshot["constraints"] if row["constraint_name"] == CHECK[1])
    row["check_clause"] = "FALSE" if show_create else clause
    if show_create:
        snapshot["show_create_tables"][TABLE] = create
    assert migration.local_additive_descriptor_state(snapshot, descriptor, context) == "exact"


@pytest.mark.parametrize("old,new", [
    ("charset utf8mb4", "charset latin1"),
    ("charset utf8mb4", "charset utf8mb3"),
    ("charset utf8mb4", "charset ascii"),
    ("as char charset", "as char(20) charset"),
    ("cast(`matching_plan_id` as char", "cast(`matching_segment_id` as char"),
    ("cast(`matching_plan_id` as char charset utf8mb4)",
     "cast(`matching_plan_id` as char charset utf8mb4) COLLATE utf8mb4_bin"),
    ("'$.source.matching_plan_id'", "'$.source.another_id'"),
    ("'$.source.matching_plan_id'", "'cast(matching_plan_id as char charset utf8mb4)'"),
    ("'contract-render-source.v1'", "'contract-render-source.v2'"),
    ("render_source_size_bytes > 0", "render_source_size_bytes >= 0"),
    ("AND render_source_size_bytes IS NOT NULL", ""),
    # Only the complete observed two-CAST rendering is admitted.
    ("cast(`matching_plan_id` as char charset utf8mb4)", "cast(`matching_plan_id` as char)"),
])
@pytest.mark.parametrize("show_create", [False, True])
def test_mysql8_rendering_does_not_hide_material_check_changes(old, new, show_create):
    descriptor = migration._canonical_artifact_descriptor(ARTIFACT)
    create, clause = _mysql8_render_source_fixture()
    assert old in clause
    snapshot = _snapshot(descriptor)
    row = next(row for row in snapshot["constraints"] if row["constraint_name"] == CHECK[1])
    row["check_clause"] = descriptor["checks"][CHECK] if show_create else clause.replace(old, new, 1)
    if show_create:
        snapshot["show_create_tables"][TABLE] = create.replace(old, new, 1)
    assert migration.local_additive_descriptor_state(snapshot, descriptor, ARTIFACT) == "drift"


@pytest.mark.parametrize("damage,expected", [
    ("missing_check", "partial"), ("not_enforced", "drift"),
    ("missing_column", "drift"), ("wrong_column_type", "drift"),
    ("missing_fk", "partial"), ("missing_guard", "partial"),
    ("changed_guard", "drift"), ("other_check", "drift"),
])
def test_mysql8_rendering_retains_original_metadata_guards(damage, expected):
    descriptor = migration._canonical_artifact_descriptor(ARTIFACT)
    snapshot = _snapshot(descriptor)
    _, clause = _mysql8_render_source_fixture()
    row = next(row for row in snapshot["constraints"] if row["constraint_name"] == CHECK[1])
    row["check_clause"] = clause
    if damage == "missing_check":
        snapshot["constraints"].remove(row)
    elif damage == "not_enforced":
        row["enforced"] = "NO"
    elif damage == "missing_column":
        snapshot["columns"] = [row for row in snapshot["columns"] if row["column_name"] != "render_source_snapshot"]
    elif damage == "wrong_column_type":
        next(row for row in snapshot["columns"] if row["column_name"] == "matching_plan_id")["column_type"] = "int"
    elif damage == "missing_fk":
        snapshot["constraints"] = [row for row in snapshot["constraints"] if row["constraint_name"] != "fk_contract_document_media_asset"]
    elif damage == "missing_guard":
        snapshot["triggers"] = snapshot["triggers"][1:]
    elif damage == "changed_guard":
        snapshot["triggers"][0]["action_statement"] = "BEGIN SET @changed=1; END"
    else:
        next(row for row in snapshot["constraints"] if row["constraint_name"] == "chk_contract_document_source")["check_clause"] = "TRUE"
    assert migration.local_additive_descriptor_state(snapshot, descriptor, ARTIFACT) == expected


def test_mysql8_variant_is_bound_to_owner_key_and_complete_expected_contract():
    descriptor = migration._canonical_artifact_descriptor(ARTIFACT)
    _, clause = _mysql8_render_source_fixture()
    snapshot = _snapshot(descriptor)
    next(row for row in snapshot["constraints"] if row["constraint_name"] == CHECK[1])["check_clause"] = clause
    assert migration.local_additive_descriptor_state(snapshot, descriptor, "another-owner") == "drift"
    assert migration._render_source_check_server_variants(ARTIFACT, ("another_table", CHECK[1]), descriptor["checks"][CHECK]) == ()
    assert migration._render_source_check_server_variants(ARTIFACT, (TABLE, "another_check"), descriptor["checks"][CHECK]) == ()
    descriptor["checks"][CHECK] = "media_asset_id IS NULL"
    assert migration._render_source_check_server_variants(ARTIFACT, CHECK, descriptor["checks"][CHECK]) == ()
    assert migration.local_additive_descriptor_state(snapshot, descriptor, ARTIFACT) == "drift"


def test_applied_drift_journal_remains_unmodified_and_exact_skip_stays_before_ddl_selection():
    statement, = migration.split_sql((ROOT / "db/schema_parts" / ARTIFACT).read_text())
    receipt = {"candidate_database": "synthetic-candidate", "schema_steps": [{
        "part": ARTIFACT, "index": 1, "status": "applied",
        "verification_status": "pending_part_completion", "after_part_state": "drift",
        "statement_sha256": hashlib.sha256(statement.encode()).hexdigest(),
    }]}
    original = deepcopy(receipt)
    assert ARTIFACT not in migration._receipt_resumable_partial_artifacts(receipt, "synthetic-candidate")
    assert receipt == original
    # Source-only proof: apply_schema's exact branch continues before selecting
    # any statements. Do not execute apply_schema or a fake SQL cursor here.
    tree = ast.parse(inspect.getsource(migration.apply_schema))
    loop, = (node for node in ast.walk(tree) if isinstance(node, ast.For)
             and isinstance(node.target, ast.Name) and node.target.id == "part")
    selector = next(i for i, node in enumerate(loop.body)
                    if isinstance(node, ast.Assign) and any(
                        isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                        and call.func.id == "schema_statements_for_state" for call in ast.walk(node)))
    exact, = (node for node in loop.body[:selector] if isinstance(node, ast.If)
              and any(isinstance(compare, ast.Compare)
                      and isinstance(compare.left, ast.Name) and compare.left.id == "before_state"
                      and any(isinstance(value, ast.Constant) and value.value == "exact" for value in compare.comparators)
                      for compare in ast.walk(node.test)))
    assert isinstance(exact.body[-1], ast.Continue)
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr == "execute" for child in exact.body for node in ast.walk(child))
