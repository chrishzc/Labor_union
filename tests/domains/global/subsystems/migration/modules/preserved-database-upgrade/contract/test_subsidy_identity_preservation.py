"""Current upgrades preserve formal identities, including when legacy history exists."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest

ROOT = Path(__file__).resolve().parents[8]
MANIFEST = ROOT / 'db/migration_releases/labor_union_2026_11_05_subsidy_identity_preservation_v5.json'
LEGACY = ROOT / 'db/migration_releases/labor_union_2026_10_29_subsidy_policy_replay_v4.json'


def test_default_upgrade_excludes_the_retired_identity_and_refund_rewrite():
    assert 'subsidy-period-policy-v1' not in {item.backfill_id for item in migration.RELEASE_MANIFEST.backfills}
    assert MANIFEST.name in migration.DEFAULT_RELEASE_MANIFESTS
    assert LEGACY.name not in migration.DEFAULT_RELEASE_MANIFESTS
    assert 'twins-payroll-rate-snapshots-v1' in {item.backfill_id for item in migration.RELEASE_MANIFEST.backfills}


@pytest.mark.parametrize('include_backfills', [False, True])
def test_explicit_legacy_selection_is_blocked_before_changing_the_catalog(monkeypatch, include_backfills):
    for name in ('RELEASE_MANIFEST', 'SCHEMA_PARTS', 'OWNED_OBJECTS', 'MANIFEST_DRIVEN_RELEASE'):
        monkeypatch.setattr(migration, name, getattr(migration, name))
    original = migration.RELEASE_MANIFEST
    with pytest.raises(migration.UpgradeBlocked, match='subsidy_identity_backfill_retired'):
        migration.configure_release_manifests((LEGACY,), include_backfills=include_backfills)
    assert migration.RELEASE_MANIFEST is original


def test_stale_runner_selection_cannot_execute_the_legacy_script(monkeypatch, tmp_path):
    historical = load_migration_release_manifest(LEGACY, ROOT)
    monkeypatch.setattr(migration, 'RELEASE_MANIFEST', SimpleNamespace(backfills=historical.backfills))
    monkeypatch.setattr(migration, '_candidate_preddl_dump', lambda *_args, **_kw: pytest.fail('retired backfill must stop before backup or DB access'))
    monkeypatch.setattr(migration.subprocess, 'run', lambda *_args, **_kw: pytest.fail('retired backfill must never execute'))
    with pytest.raises(migration.UpgradeBlocked, match='subsidy_identity_backfill_retired'):
        migration._run_manifest_backfills(object(), 'lu_test_identity', tmp_path / 'operation.json', mysql_container=None)


def test_legacy_backfill_receipt_cannot_approve_a_candidate_in_current_upgrade(monkeypatch, tmp_path):
    receipt = tmp_path / 'old-operation.json'
    migration.write_receipt(receipt, {'status': 'backfilled', 'backfills': [{'backfill_id': 'subsidy-period-policy-v1'}]})
    monkeypatch.setattr(migration, '_schema_snapshot', lambda *_args, **_kw: pytest.fail('retired receipt must stop before DB access'))
    with pytest.raises(migration.UpgradeBlocked, match='subsidy_identity_backfill_retired'):
        migration.verify_candidate(object(), 'lu_test_source', 'lu_test_candidate', receipt)


def test_current_release_keeps_exact_schema_and_historical_artifacts():
    current = load_migration_release_manifest(MANIFEST, ROOT)
    historical = load_migration_release_manifest(LEGACY, ROOT)
    assert current.schema_artifacts == historical.schema_artifacts
    assert current.backfills == ()
    assert current.owned_object_descriptors(ROOT) == historical.owned_object_descriptors(ROOT)
    current_payload = json.loads(MANIFEST.read_text(encoding='utf-8'))
    descriptor = ROOT / current_payload['descriptor_artifact']['relative_path']
    assert b'\r\n' not in MANIFEST.read_bytes() and b'\r\n' not in descriptor.read_bytes()
    before = json.loads(LEGACY.read_text(encoding='utf-8'))
    assert before['backfills'][0]['artifact']['sha256'] == '2d2ddfebf56f6ed092cd856a97ba47d2dd46b216ee45d992064e20d7c4cb65ab'
