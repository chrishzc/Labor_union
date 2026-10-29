"""Saved group invitation release is additive, exact and fail closed on drift."""
from copy import deepcopy
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from scripts.schema_assembly import load_schema_assembly
from shared_kernel.migration_release import load_migration_release_manifest

ROOT = Path(__file__).resolve().parents[8]
ARTIFACT = '1053_line_order_group_invitation_url.sql'
MANIFEST = ROOT/'db/migration_releases/labor_union_2026_10_22_line_order_group_invitation_url_v1.json'


def test_release_registry_fresh_assembly_and_descriptor_match_the_additive_sql():
    preserve_parts = [entry['artifact']['name'] for entry in migration._local_ordered_upgrade_entries()]
    preserve_index = preserve_parts.index(ARTIFACT)
    assert preserve_parts[preserve_index:preserve_index + 3] == [
        ARTIFACT, '1054_scheduling_service_start.sql', '1055_government_subsidy_periods.sql',
    ]
    fresh_parts = [path.name for path in load_schema_assembly().active_artifact_paths]
    fresh_index = fresh_parts.index(ARTIFACT)
    assert fresh_parts[fresh_index:fresh_index + 3] == [
        ARTIFACT, '1054_scheduling_service_start.sql', '233_government_subsidy_periods.sql',
    ]
    released = load_migration_release_manifest(MANIFEST, ROOT).owned_object_descriptors(ROOT)[ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    assert released['parent_columns'] == canonical['parent_columns']
    steps = migration.split_sql((ROOT/'db/schema_parts'/ARTIFACT).read_text(encoding='utf-8'))
    assert len(steps) == 1 and migration._local_classify_statement(steps[0]) == 'alter_add_only'


def test_nullable_private_url_accepts_only_absent_or_exact_metadata():
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    snapshot = dict(columns=[], indexes=[], constraints=[], key_columns=[], foreign_keys=[], triggers=[], views=[], show_create_tables={})
    assert migration.local_additive_descriptor_state(snapshot, canonical, ARTIFACT) == 'absent'
    contract = canonical['parent_columns']['line_order_group_bindings']['invitation_url']
    snapshot['columns'] = [dict(table_name='line_order_group_bindings', column_name='invitation_url', **contract)]
    assert migration.local_additive_descriptor_state(snapshot, canonical, ARTIFACT) == 'exact'
    for key, value in [('column_type','varchar(255)'),('is_nullable','NO'),('collation_name','utf8mb4_unicode_ci')]:
        drift = deepcopy(snapshot)
        drift['columns'][0][key] = value
        assert migration.local_additive_descriptor_state(drift, canonical, ARTIFACT) == 'drift'
