"""Protect zero initial obligations without admitting unchanged later events."""

import json
import os
from pathlib import Path

import pytest

from scripts import migrate_preserved_database_additive_schema as migration
from scripts import collect_local_additive_engine_evidence as collector
from scripts.schema_assembly import load_schema_assembly
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[8]
ARTIFACT = "1046_client_zero_obligation_establishment.sql"
MANIFEST = "labor_union_2026_09_29_client_zero_obligation_establishment_v1.json"
KEY = ("client_obligation_events", "chk_client_obligation_event_amount")


def _snapshot(clause):
    return {
        "columns": [], "indexes": [], "key_columns": [], "foreign_keys": [],
        "triggers": [], "views": [], "show_create_tables": {},
        "constraints": [{
            "table_name": KEY[0], "constraint_name": KEY[1],
            "constraint_type": "CHECK", "check_clause": clause, "enforced": "YES",
        }],
    }


def test_release_is_hash_bound_schema_only_and_selected_by_both_paths():
    manifest = load_migration_release_manifest(ROOT / "db/migration_releases" / MANIFEST, ROOT)
    assert migration.DEFAULT_RELEASE_MANIFESTS[-1] == MANIFEST
    assert manifest.schema_paths(ROOT) == ((ROOT / "db/schema_parts" / ARTIFACT).resolve(),)
    assert manifest.backfills == ()
    raw = json.loads((ROOT / "db/migration_releases" / MANIFEST).read_text(encoding="utf-8"))
    assert raw["artifacts"][0]["data_effect"] == "schema_only"
    assert load_schema_assembly().active_artifact_paths[-1].name == ARTIFACT
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    released = manifest.owned_object_descriptors(ROOT)[ARTIFACT]
    assert released["checks"] == canonical["checks"]
    sql = (ROOT / "db/schema_parts" / ARTIFACT).read_text(encoding="utf-8")
    statements = migration.split_sql(sql)
    assert len(statements) == 1
    assert migration._local_classify_statement(statements[0]) == (
        "client_zero_obligation_establishment_check_widen"
    )
    with pytest.raises(migration.LocalAdditiveBlocked):
        migration._local_classify_statement(statements[0].replace("after_amount_ntd >= 0", "after_amount_ntd >= -1"))


def test_predecessor_successor_and_unknown_constraint_are_distinguished():
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    predecessor = migration._canonical_artifact_descriptor("111_client_finance_ledger.sql")
    manifest = load_migration_release_manifest(ROOT / "db/migration_releases" / MANIFEST, ROOT)
    released = manifest.owned_object_descriptors(ROOT)[ARTIFACT]
    for clause, expected in (
        (predecessor["checks"][KEY], "absent"),
        (canonical["checks"][KEY], "exact"),
        ("after_amount_ntd >= 0", "drift"),
    ):
        snapshot = _snapshot(clause)
        assert migration.local_additive_descriptor_state(snapshot, canonical, ARTIFACT) == expected
        assert migration._release_descriptor_metadata_state(snapshot, ARTIFACT, released) == expected


def test_missing_or_unenforced_constraint_fails_closed():
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    snapshot = _snapshot(canonical["checks"][KEY])
    snapshot["constraints"][0]["enforced"] = "NO"
    assert migration.local_additive_descriptor_state(snapshot, canonical, ARTIFACT) == "drift"
    snapshot["constraints"] = []
    snapshot["columns"] = [{"table_name": KEY[0]}]
    assert migration.local_additive_descriptor_state(snapshot, canonical, ARTIFACT) == "partial"
    snapshot["columns"] = []
    assert migration.local_additive_descriptor_state(snapshot, canonical, ARTIFACT) == "absent"


def test_selected_release_reads_the_immutable_predecessor_outside_its_write_set(monkeypatch):
    predecessor = migration._canonical_artifact_descriptor("111_client_finance_ledger.sql")
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    monkeypatch.setattr(migration, "SCHEMA_PARTS", tuple(
        path for path in migration.SCHEMA_PARTS if path.name == ARTIFACT
    ))
    assert migration.local_additive_descriptor_state(
        _snapshot(predecessor["checks"][KEY]), canonical, ARTIFACT
    ) == "absent"


@pytest.mark.parametrize("retired_state,accepted", [("absent", True), ("partial", False), ("drift", False)])
def test_engine_evidence_preserves_the_declared_retired_predecessor_contract(monkeypatch, retired_state, accepted):
    entries = (
        {"release_id": "baseline", "artifact": {"name": "baseline.sql"}, "descriptor": {}},
        {"release_id": "retired", "artifact": {"name": "1031_weekly_report_batches.sql"}, "descriptor": {}},
        {"release_id": "target", "artifact": {"name": ARTIFACT}, "descriptor": {}},
    )
    states = {"baseline.sql": "exact", "1031_weekly_report_batches.sql": retired_state, ARTIFACT: "absent"}
    monkeypatch.setattr(migration, "_local_ordered_upgrade_entries", lambda: entries)
    monkeypatch.setattr(migration, "local_additive_target_state", lambda config, database, artifact, descriptor, **kwargs: {"state": states[artifact]})
    if accepted:
        assert collector._verify_release_boundary(
            None, "lu_test_source", "target", applied=False, snapshot={}
        ) == ["exact", "retired_absent", "absent"]
    else:
        with pytest.raises(collector.EngineEvidenceError, match="predecessor prefix"):
            collector._verify_release_boundary(None, "lu_test_source", "target", applied=False, snapshot={})


def test_earlier_ledger_artifact_accepts_only_the_exact_published_successor():
    earlier = migration._canonical_artifact_descriptor("111_client_finance_ledger.sql")
    successor = migration._canonical_artifact_descriptor(ARTIFACT)
    # Isolate this changed CHECK; the comparator still validates all other owned objects.
    descriptor = {
        "tables": {}, "parent_columns": {}, "indexes": {}, "foreign_keys": {},
        "checks": {KEY: earlier["checks"][KEY]}, "triggers": {},
    }
    assert migration._artifact_metadata_state(
        _snapshot(successor["checks"][KEY]), descriptor, "111_client_finance_ledger.sql"
    ) == "exact"
    assert migration._artifact_metadata_state(
        _snapshot("after_amount_ntd >= 0"), descriptor, "111_client_finance_ledger.sql"
    ) == "drift"


@pytest.mark.integration
@pytest.mark.parametrize("values,accepted", [
    (("established", 0, 0, None, None), True),
    (("established", 0, 100, None, None), True),
    (("recalculated", 100, 200, None, None), True),
    (("reversed", 100, 0, None, None), True),
    (("adjusted", 100, 100, None, "2026-09-29"), True),
    (("established", 100, 100, None, None), False),
    (("established", 0, 0, "2026-09-29", "2026-09-29"), False),
    (("adjusted", 0, 0, None, None), False),
    (("reversed", 0, 0, None, None), False),
    (("recalculated", 0, 0, None, None), False),
    (("established", -1, 0, None, None), False),
    (("established", 0, -1, None, None), False),
])
def test_mysql_evaluates_the_released_check_without_writing_data(values, accepted):
    prefix = "LABOR_UNION_TEST_MYSQL_"
    names = ("HOST", "PORT", "USER", "PASSWORD", "DATABASE")
    if not all(os.getenv(prefix + name) for name in names):
        pytest.skip("Explicit disposable MySQL configuration is required")
    import pymysql

    sql = (ROOT / "db/schema_parts" / ARTIFACT).read_text(encoding="utf-8")
    clause, _ = migration._extract_parenthesized(sql, sql.index("CHECK (") + 6)
    connection = pymysql.connect(
        host=os.environ[prefix + "HOST"], port=int(os.environ[prefix + "PORT"]),
        user=os.environ[prefix + "USER"], password=os.environ[prefix + "PASSWORD"],
        database=os.environ[prefix + "DATABASE"],
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT ({clause}) FROM (SELECT %s AS event_type, %s AS before_amount_ntd, "
                "%s AS after_amount_ntd, CAST(%s AS DATE) AS before_due_date, "
                "CAST(%s AS DATE) AS after_due_date) facts", values,
            )
            assert cursor.fetchone()[0] == int(accepted)
    finally:
        connection.close()
