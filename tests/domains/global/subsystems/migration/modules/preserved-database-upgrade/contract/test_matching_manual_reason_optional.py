"""Only the exact obsolete manual-reason CHECK may be retired, without row changes."""
from copy import deepcopy
from pathlib import Path
import pytest

from scripts import migrate_preserved_database_additive_schema as migration
from scripts.schema_assembly import load_schema_assembly
from shared_kernel.migration_release import load_migration_release_manifest

ROOT = Path(__file__).resolve().parents[8]
ARTIFACT = '1061_matching_manual_reason_optional.sql'


def _snapshot():
    descriptor = migration._canonical_artifact_descriptor(ARTIFACT)
    reason = descriptor['parent_columns']['matching_response_events']['reason']
    return descriptor, dict(columns=[dict(table_name='matching_response_events', column_name='reason', **reason)],
        indexes=[], constraints=[], key_columns=[], foreign_keys=[], triggers=[], views=[], show_create_tables={})


def test_optional_reason_release_fresh_alias_and_parent_descriptor_are_bound():
    manifest = ROOT / 'db/migration_releases/labor_union_2026_10_29_matching_manual_reason_optional_v1.json'
    release = load_migration_release_manifest(manifest, ROOT)
    descriptor = release.owned_object_descriptors(ROOT)[ARTIFACT]
    assert descriptor['parent_columns'] == migration._canonical_artifact_descriptor(ARTIFACT)['parent_columns']
    fresh = ROOT / 'db/schema_parts/239_matching_manual_reason_optional.sql'
    assert fresh.read_bytes() == (ROOT / 'db/schema_parts' / ARTIFACT).read_bytes()
    assert fresh in load_schema_assembly().active_artifact_paths
    assert any(entry['artifact']['name'] == ARTIFACT for entry in migration._local_ordered_upgrade_entries())
    statements = migration.split_sql(fresh.read_text(encoding='utf-8'))
    assert len(statements) == 1
    assert migration._local_classify_statement(statements[0]) == 'alter_add_only'
    assert 'DROP CHECK chk_matching_response_manual_reason' in statements[0]
    with pytest.raises(migration.LocalAdditiveBlocked):
        migration._local_classify_statement('ALTER TABLE matching_response_events DROP CHECK chk_matching_response_target;')


def test_constraint_retirement_distinguishes_exact_predecessor_successor_and_drift():
    descriptor, snapshot = _snapshot()
    state = lambda value: migration.local_additive_descriptor_state(value, descriptor, ARTIFACT)
    assert state(snapshot) == 'exact'
    old = deepcopy(snapshot)
    old['constraints'] = [dict(table_name='matching_response_events', constraint_name='chk_matching_response_manual_reason',
        constraint_type='CHECK', enforced='YES', check_clause="response_source='line' OR CHAR_LENGTH(TRIM(reason)) > 0")]
    assert state(old) == 'absent'
    for key, value in [('check_clause', "CHAR_LENGTH(reason) > 1"), ('enforced', 'NO'), ('constraint_type', 'UNIQUE')]:
        drift = deepcopy(old)
        drift['constraints'][0][key] = value
        assert state(drift) == 'drift'
    changed = deepcopy(snapshot)
    changed['columns'][0]['column_type'] = 'varchar(255)'
    assert state(changed) == 'drift'
    missing = deepcopy(snapshot)
    missing['columns'] = []
    assert state(missing) == 'partial'
