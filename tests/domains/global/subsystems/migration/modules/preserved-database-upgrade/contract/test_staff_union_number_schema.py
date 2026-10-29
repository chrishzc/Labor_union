"""Manual Staff numbers require exact text uniqueness and preservation-safe metadata."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from scripts.schema_assembly import validate_schema_assembly
from shared_kernel.migration_release import load_migration_release_manifest

ROOT = Path(__file__).resolve().parents[8]
MANIFEST = ROOT / 'db/migration_releases/labor_union_2026_10_13_staff_union_number_v1.json'
ARTIFACT = '1050_staff_union_number.sql'


def snapshot(*, columns=(), indexes=()):
    return {'columns': list(columns), 'indexes': list(indexes), 'constraints': [],
            'key_columns': [], 'foreign_keys': [], 'triggers': [], 'show_create_tables': {}, 'views': []}


def test_release_is_additive_hash_bound_and_connected_to_fresh_and_preserve():
    release = json.loads(MANIFEST.read_text(encoding='utf-8'))
    assert release['backfills'] == []
    assert release['artifacts'][0]['data_effect'] == 'schema_only'
    for item in (release['artifacts'][0], release['descriptor_artifact']):
        assert hashlib.sha256((ROOT / item['relative_path']).read_bytes()).hexdigest() == item['sha256']
    assert validate_schema_assembly() == []
    release_index = migration.DEFAULT_RELEASE_MANIFESTS.index(MANIFEST.name)
    assert migration.DEFAULT_RELEASE_MANIFESTS[release_index:release_index + 6] == (
        MANIFEST.name,
        'labor_union_2026_10_14_candidate_weekly_information_v1.json',
        'labor_union_2026_10_19_nas_registration_approval_v1.json',
        'labor_union_2026_10_22_line_order_group_invitation_url_v1.json',
        'labor_union_2026_10_23_scheduling_service_start_v1.json',
        'labor_union_2026_10_27_government_subsidy_periods_hash_v2.json',
    )
    fresh = (ROOT / 'db/schema_parts/231_staff_union_number.sql').read_text(encoding='utf-8')
    bridge = (ROOT / 'db/schema_parts' / ARTIFACT).read_text(encoding='utf-8')
    assert fresh == bridge
    statements = migration.split_sql(bridge)
    assert len(statements) == 1
    assert migration._local_classify_statement(statements[0]) == 'alter_add_only'
    assert all(word not in bridge.upper() for word in ('UPDATE ', 'INSERT ', 'DELETE ', 'DROP '))


def test_descriptor_detects_missing_index_and_collation_drift():
    released = load_migration_release_manifest(MANIFEST, ROOT).owned_object_descriptors(ROOT)[ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    assert released['parent_columns'] == canonical['parent_columns']
    assert migration.local_additive_descriptor_state(snapshot(), canonical, ARTIFACT) == 'absent'
    column = {'table_name': 'staff', 'column_name': 'union_no', **canonical['parent_columns']['staff']['union_no']}
    index = {'table_name': 'staff', 'index_name': 'uq_staff_union_no', 'non_unique': 0, 'columns': 'union_no'}
    exact = snapshot(columns=[column], indexes=[index])
    assert migration.local_additive_descriptor_state(exact, canonical, ARTIFACT) == 'exact'
    assert migration.local_additive_descriptor_state(snapshot(columns=[column]), canonical, ARTIFACT) == 'partial'
    for field, value in [('collation_name', 'utf8mb4_unicode_ci'), ('character_set_name', 'latin1'), ('column_type', 'varchar(20)'), ('is_nullable', 'NO')]:
        drift = deepcopy(exact)
        drift['columns'][0][field] = value
        assert migration.local_additive_descriptor_state(drift, canonical, ARTIFACT) == 'drift'
    drift = deepcopy(exact)
    drift['indexes'][0]['non_unique'] = 1
    assert migration.local_additive_descriptor_state(drift, canonical, ARTIFACT) == 'drift'
