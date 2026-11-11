"""Historical corrections append receipt states without changing prior ordinals."""
from copy import deepcopy
from scripts import migrate_preserved_database_additive_schema as migration
from scripts.schema_assembly import validate_schema_assembly
from shared_kernel.migration_release import load_migration_release_manifest

ARTIFACT = '1070_historical_order_terms_receipt_status.sql'
OLD = "enum('洽談中','訂單成立','服務中','訂單完成','訂單取消')"
NEW = OLD[:-1] + ",'歷史訂單－服務完成','歷史訂單－帳務完成')"


def snapshot(column_type):
    return {'columns':[{'table_name':'order_terms_apply_receipts','column_name':'lifecycle_status',
        'column_type':column_type,'is_nullable':'NO','column_default':None,'extra':''}],
        'indexes':[], 'constraints':[], 'key_columns':[], 'foreign_keys':[], 'triggers':[], 'show_create_tables':{}, 'views':[]}


def test_exact_predecessor_successor_and_drift():
    name = 'labor_union_2026_11_09_historical_accounting_corrections_v1.json'
    assert name in migration.DEFAULT_RELEASE_MANIFESTS
    release = load_migration_release_manifest(migration.ROOT/'db/migration_releases'/name, migration.ROOT)
    descriptor = migration._canonical_artifact_descriptor(ARTIFACT)
    assert release.owned_object_descriptors(migration.ROOT)[ARTIFACT]['parent_columns'] == descriptor['parent_columns']
    assert release.backfills == ()
    assert validate_schema_assembly() == []
    assert migration.local_additive_descriptor_state(snapshot(OLD),descriptor,ARTIFACT) == 'absent'
    assert migration.local_additive_descriptor_state(snapshot(NEW),descriptor,ARTIFACT) == 'exact'
    wrong = deepcopy(snapshot(NEW)); wrong['columns'][0]['is_nullable'] = 'YES'
    assert migration.local_additive_descriptor_state(wrong,descriptor,ARTIFACT) == 'drift'
    assert migration.local_additive_descriptor_state(snapshot(NEW.replace("'訂單成立','服務中'", "'服務中','訂單成立'")),descriptor,ARTIFACT) == 'drift'
    sql, = migration.split_sql((migration.ROOT/'db/schema_parts'/ARTIFACT).read_text(encoding='utf-8'))
    assert migration._local_classify_statement(sql) == 'alter_add_only'


def test_registry_save_receipts_accept_only_declared_predecessors_and_successors():
    releases = (
        'labor_union_2026_11_11_registry_save_receipts_v1.json',
        'labor_union_2026_11_11_registry_bootstrap_reason_v1.json',
    )
    pending_part = '1071_pending_order_terms_receipt_status.sql'
    bootstrap_part = '1072_case_architecture_bootstrap_reason_optional.sql'
    pending = NEW[:-1] + ",'待補件')"
    for name, part in zip(releases, (pending_part, bootstrap_part), strict=True):
        release = load_migration_release_manifest(migration.ROOT / 'db/migration_releases' / name, migration.ROOT)
        descriptors = release.owned_object_descriptors(migration.ROOT)
        assert set(descriptors) == {part}
        assert not release.backfills
        canonical = migration._canonical_artifact_descriptor(part)
        assert descriptors[part]['parent_columns'] == canonical['parent_columns']
        assert descriptors[part]['checks'] == canonical['checks']
        sql, = migration.split_sql((migration.ROOT / 'db/schema_parts' / part).read_text(encoding='utf-8'))
        assert migration._local_classify_statement(sql) == 'alter_add_only'
    pending_descriptor = migration._canonical_artifact_descriptor(pending_part)
    assert migration.local_additive_descriptor_state(snapshot(NEW), pending_descriptor, pending_part) == 'absent'
    assert migration.local_additive_descriptor_state(snapshot(pending), pending_descriptor, pending_part) == 'exact'
    assert migration.local_additive_descriptor_state(snapshot(OLD), pending_descriptor, pending_part) == 'drift'
    assert migration.local_additive_descriptor_state(
        snapshot(pending), migration._canonical_artifact_descriptor(ARTIFACT), ARTIFACT,
    ) == 'exact'

    table = 'case_architecture_bootstrap_events'
    check = 'chk_case_architecture_bootstrap_text'
    descriptor = migration._canonical_artifact_descriptor(bootstrap_part)
    metadata = snapshot(NEW)
    metadata['columns'] = [
        {'table_name': table, 'column_name': field, **contract}
        for field, contract in descriptor['parent_columns'][table].items()
    ]
    assert migration.local_additive_descriptor_state(metadata, descriptor, bootstrap_part) == 'partial'
    predecessor = migration._canonical_artifact_descriptor('124_case_architecture_bootstrap.sql')
    metadata['constraints'] = [{
        'table_name': table, 'constraint_name': check, 'constraint_type': 'CHECK',
        'enforced': 'YES', 'check_clause': predecessor['checks'][(table, check)],
    }]
    assert migration.local_additive_descriptor_state(metadata, descriptor, bootstrap_part) == 'absent'
    metadata['constraints'][0]['check_clause'] = descriptor['checks'][(table, check)]
    assert migration.local_additive_descriptor_state(metadata, descriptor, bootstrap_part) == 'exact'
    metadata['constraints'][0]['enforced'] = 'NO'
    assert migration.local_additive_descriptor_state(metadata, descriptor, bootstrap_part) == 'drift'
