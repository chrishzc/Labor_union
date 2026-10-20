"""The additive registration release must bind actual four-column metadata."""
from copy import deepcopy
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest

ROOT = Path(__file__).resolve().parents[8]
ARTIFACT = '1052_nas_registration_approval.sql'
MANIFEST = ROOT/'db/migration_releases/labor_union_2026_10_19_nas_registration_approval_v1.json'


def test_canonical_registry_and_released_descriptor_are_identical():
    entries = migration._local_ordered_upgrade_entries()
    assert entries[-1]['artifact']['name'] == ARTIFACT
    released = load_migration_release_manifest(MANIFEST,ROOT).owned_object_descriptors(ROOT)[ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    assert released['parent_columns'] == canonical['parent_columns']
    assert set(canonical['parent_columns']['provisional_client_registrations']) == {
        'application_payload','application_version','approved_by_actor','approved_at_utc'}
    steps=migration.split_sql((ROOT/'db/schema_parts'/ARTIFACT).read_text(encoding='utf-8'))
    assert len(steps)==1 and migration._local_classify_statement(steps[0])=='alter_add_only'


def test_registration_column_states_reject_partial_and_drift():
    canonical=migration._canonical_artifact_descriptor(ARTIFACT)
    empty=dict(columns=[],indexes=[],constraints=[],key_columns=[],foreign_keys=[],triggers=[],views=[],show_create_tables={})
    assert migration.local_additive_descriptor_state(empty,canonical,ARTIFACT)=='absent'
    exact=deepcopy(empty)
    exact['columns']=[dict(table_name='provisional_client_registrations',column_name=name,**contract)
        for name,contract in canonical['parent_columns']['provisional_client_registrations'].items()]
    assert migration.local_additive_descriptor_state(exact,canonical,ARTIFACT)=='exact'
    partial=deepcopy(exact); partial['columns'].pop()
    assert migration.local_additive_descriptor_state(partial,canonical,ARTIFACT)=='partial'
    drift=deepcopy(exact);drift['columns'][1]['column_default']='0'
    assert migration.local_additive_descriptor_state(drift,canonical,ARTIFACT)=='drift'
    drift=deepcopy(exact);drift['columns'][2]['collation_name']='utf8mb4_0900_ai_ci'
    assert migration.local_additive_descriptor_state(drift,canonical,ARTIFACT)=='drift'
