"""Only the declared optional-note successor may replace the reopen event CHECK."""
from copy import deepcopy
from pathlib import Path
import pytest
from scripts import migrate_preserved_database_additive_schema as migration
from scripts.schema_assembly import load_schema_assembly
from shared_kernel.migration_release import load_migration_release_manifest

ROOT = Path(__file__).resolve().parents[8]
ARTIFACT = '1062_order_reopen_reason_optional.sql'
KEY = ('order_reopen_events', 'chk_order_reopen_event_text')


def snapshot():
    descriptor = migration._canonical_artifact_descriptor(ARTIFACT)
    columns = [dict(table_name=KEY[0], column_name=name, **column)
               for name, column in descriptor['parent_columns'][KEY[0]].items()]
    return descriptor, dict(columns=columns, indexes=[], foreign_keys=[], key_columns=[],
        constraints=[dict(table_name=KEY[0], constraint_name=KEY[1], constraint_type='CHECK',
                          enforced='YES', check_clause=descriptor['checks'][KEY])],
        triggers=[], views=[], show_create_tables={})


def test_release_alias_descriptor_and_exact_sql_are_bound():
    manifest = ROOT / 'db/migration_releases/labor_union_2026_10_29_order_reopen_reason_optional_v1.json'
    release = load_migration_release_manifest(manifest, ROOT)
    owned = release.owned_object_descriptors(ROOT)[ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    assert owned['parent_columns'] == canonical['parent_columns']
    assert owned['checks'][KEY] == migration._normalize_check_contract(canonical['checks'][KEY])
    fresh = ROOT / 'db/schema_parts/240_order_reopen_reason_optional.sql'
    assert fresh.read_bytes() == (ROOT / 'db/schema_parts' / ARTIFACT).read_bytes()
    assert fresh in load_schema_assembly().active_artifact_paths
    assert migration._local_ordered_upgrade_entries()[-1]['artifact']['name'] == ARTIFACT
    statements = migration.split_sql(fresh.read_text(encoding='utf-8'))
    assert len(statements) == 1
    assert migration._local_classify_statement(statements[0]) == 'alter_add_only'
    with pytest.raises(migration.LocalAdditiveBlocked):
        migration._local_classify_statement('ALTER TABLE order_reopen_events DROP CHECK chk_order_reopen_event_text')


def test_exact_predecessor_is_pending_and_successor_is_current():
    descriptor, current = snapshot()
    state = lambda value: migration.local_additive_descriptor_state(value, descriptor, ARTIFACT)
    assert state(current) == 'exact'
    old = deepcopy(current)
    old['constraints'][0]['check_clause'] = migration._canonical_artifact_descriptor('123_order_reopen_workflow.sql')['checks'][KEY]
    assert state(old) == 'absent'
    assert migration._normalize_check_contract(descriptor['checks'][KEY]) in {
        migration._normalize_check_contract(x) for x in migration._allowed_later_artifact_checks('123_order_reopen_workflow.sql')[KEY]}
    for field, value in [('check_clause', 'CHAR_LENGTH(actor)>1'), ('enforced', 'NO'), ('constraint_type', 'UNIQUE')]:
        drift = deepcopy(current); drift['constraints'][0][field] = value
        assert state(drift) == 'drift'
    missing = deepcopy(current); missing['constraints'] = []
    assert state(missing) == 'partial'
    missing = deepcopy(current); missing['columns'] = []
    assert state(missing) == 'partial'
    drift = deepcopy(current); drift['columns'][0]['column_type'] = 'varchar(190)'
    assert state(drift) == 'drift'
