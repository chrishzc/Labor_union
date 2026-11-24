"""Bind the zero-entitlement migration to exact Staff Payables metadata."""

import pytest

from scripts import migrate_preserved_database_additive_schema as migration
from scripts.schema_assembly import load_schema_assembly
from shared_kernel.migration_release import load_migration_release_manifest


ARTIFACT = "1084_staff_payable_projection_zero.sql"
MANIFEST = "labor_union_2026_11_24_staff_payable_projection_zero_v1.json"
LEDGER = "114_staff_payout_ledger.sql"
TABLE = "staff_payable_projections"
MONEY = "chk_staff_payable_projection_money"
STATUS = "chk_staff_payable_projection_status"


@pytest.fixture
def predecessor_snapshot():
    descriptor = migration._staff_payable_projection_predecessor_descriptor()
    constraints = [
        {
            "table_name": table,
            "constraint_name": name,
            "constraint_type": "CHECK",
            "check_clause": clause,
            "enforced": "YES",
        }
        for (table, name), clause in descriptor["checks"].items()
    ]
    key_columns = []
    foreign_keys = []
    for (table, name), contract in descriptor["foreign_keys"].items():
        identity = {"table_name": table, "constraint_name": name}
        constraints.append({**identity, "constraint_type": "FOREIGN KEY"})
        foreign_keys.append({
            **identity,
            "update_rule": contract["update_rule"],
            "delete_rule": contract["delete_rule"],
        })
        key_columns.extend(
            {
                **identity,
                "column_name": column,
                "referenced_table_name": contract["referenced_table"],
                "referenced_column_name": referenced,
            }
            for column, referenced in zip(
                contract["columns"], contract["referenced_columns"], strict=True,
            )
        )
    return {
        "columns": [
            {"table_name": TABLE, "column_name": name, **column}
            for name, column in descriptor["tables"][TABLE].items()
        ],
        "indexes": [
            {
                "table_name": table,
                "index_name": name,
                "non_unique": index["non_unique"],
                "columns": ",".join(index["columns"]),
            }
            for (table, name), index in descriptor["indexes"].items()
        ],
        "constraints": constraints,
        "key_columns": key_columns,
        "foreign_keys": foreign_keys,
        "triggers": [],
    }


@pytest.fixture
def manifest():
    return load_migration_release_manifest(
        migration.ROOT / "db/migration_releases" / MANIFEST, migration.ROOT,
    )


def test_versioned_check_is_shared_by_preserve_and_fresh(manifest):
    path, = manifest.schema_paths(migration.ROOT)
    assert path.name == ARTIFACT
    assert migration.DEFAULT_RELEASE_MANIFESTS[-1] == MANIFEST
    assert load_schema_assembly().active_artifact_paths[-1] == path
    assert manifest.schema_artifacts[0].data_effect == "schema_only"
    assert manifest.backfills == ()
    sql, = migration.split_sql(path.read_text(encoding="utf-8"))
    assert migration._local_classify_statement(sql) == "staff_payable_projection_check_widen"
    with pytest.raises(migration.LocalAdditiveBlocked) as error:
        migration._local_classify_statement(
            sql.replace("obligation_amount_ntd >= 0", "obligation_amount_ntd >= -1"),
        )
    assert error.value.code == "forbidden_sql_effect"


@pytest.mark.parametrize(
    "variant,expected",
    [
        ("predecessor", "absent"),
        ("successor", "exact"),
        ("missing", "drift"),
        ("disabled", "drift"),
        ("unknown", "drift"),
        ("status_missing", "drift"),
    ],
)
def test_upgrade_classification(predecessor_snapshot, manifest, variant, expected):
    snapshot = predecessor_snapshot
    descriptor = migration._canonical_artifact_descriptor(ARTIFACT)
    released = manifest.owned_object_descriptors(migration.ROOT)[ARTIFACT]
    assert released["checks"] == descriptor["checks"]
    assert released["parent_columns"] == descriptor["parent_columns"]
    constraints = snapshot["constraints"]
    money = next(row for row in constraints if row["constraint_name"] == MONEY)
    if variant == "successor":
        money["check_clause"] = (
            "obligation_amount_ntd >= 0 AND net_paid_ntd >= 0 "
            "AND balance_ntd = obligation_amount_ntd - net_paid_ntd"
        )
    elif variant == "disabled":
        money["enforced"] = "NO"
    elif variant == "missing":
        constraints.remove(money)
    elif variant == "unknown":
        money["check_clause"] = "obligation_amount_ntd >= 0"
    elif variant == "status_missing":
        constraints[:] = [row for row in constraints if row["constraint_name"] != STATUS]
    assert migration.local_additive_descriptor_state(snapshot, descriptor, ARTIFACT) == expected
    assert migration._release_descriptor_metadata_state(snapshot, ARTIFACT, released) == expected


def test_only_the_declared_successor_replaces_the_original_money_check(monkeypatch):
    successor = migration._canonical_artifact_descriptor(ARTIFACT)
    assert migration._allowed_later_artifact_checks(LEDGER) == {
        (TABLE, MONEY): (successor["checks"][(TABLE, MONEY)],),
    }
    monkeypatch.setattr(
        migration, "SCHEMA_PARTS",
        tuple(path for path in migration.SCHEMA_PARTS if path.name != ARTIFACT),
    )
    assert migration._allowed_later_artifact_checks(LEDGER) == {}
