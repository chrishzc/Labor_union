"""Protect the 1082 uniqueness replacement and the bounded DDL exception."""

from copy import deepcopy

import pytest

from scripts import migrate_preserved_database_additive_schema as migration


ARTIFACT = "1082_service_date_adjustments.sql"
PREDECESSOR_INDEX = {
    "table_name": "staff_schedule",
    "index_name": "uq_staff_schedule_generation_owner",
    "non_unique": 0,
    "columns": "generation_id,work_date",
}
SUCCESSOR_INDEX = "uq_staff_schedule_effective_generation_day"


@pytest.fixture
def descriptor():
    return migration._canonical_artifact_descriptor(ARTIFACT)


@pytest.fixture
def exact_snapshot(descriptor):
    constraints = []
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
        key_columns.extend({
            **identity,
            "column_name": column,
            "referenced_table_name": contract["referenced_table"],
            "referenced_column_name": referenced,
        } for column, referenced in zip(
            contract["columns"], contract["referenced_columns"], strict=True,
        ))
    constraints.extend({
        "table_name": table,
        "constraint_name": name,
        "constraint_type": "CHECK",
        "check_clause": check,
        "enforced": "YES",
    } for (table, name), check in descriptor["checks"].items())
    return {
        "columns": [
            {"table_name": table, "column_name": name, **contract}
            for table, columns in (descriptor["tables"] | descriptor["parent_columns"]).items()
            for name, contract in columns.items()
        ],
        "indexes": [
            {
                "table_name": table,
                "index_name": name,
                "non_unique": contract["non_unique"],
                "columns": ",".join(contract["columns"]),
            }
            for (table, name), contract in descriptor["indexes"].items()
        ],
        "constraints": constraints,
        "key_columns": key_columns,
        "foreign_keys": foreign_keys,
        "triggers": [],
        "views": [],
    }


def test_only_canonical_predecessor_is_absent(descriptor, exact_snapshot):
    predecessor = {name: [] for name in exact_snapshot}
    predecessor["indexes"] = [PREDECESSOR_INDEX]
    assert migration.local_additive_descriptor_state(predecessor, descriptor, ARTIFACT) == "absent"
    predecessor["indexes"] = []
    assert migration.local_additive_descriptor_state(predecessor, descriptor, ARTIFACT) == "drift"


def test_exact_successor_rejects_old_uniqueness_under_either_name(descriptor, exact_snapshot):
    assert migration.local_additive_descriptor_state(exact_snapshot, descriptor, ARTIFACT) == "exact"
    for name in (PREDECESSOR_INDEX["index_name"], "legacy_schedule_uniqueness"):
        collision = deepcopy(exact_snapshot)
        collision["indexes"].append({**PREDECESSOR_INDEX, "index_name": name})
        assert migration.local_additive_descriptor_state(collision, descriptor, ARTIFACT) == "drift"


def test_missing_successor_objects_are_partial(descriptor, exact_snapshot):
    for collection, key, object_name in (
        ("indexes", "index_name", SUCCESSOR_INDEX),
        ("columns", "column_name", "service_hours_override"),
        ("constraints", "constraint_name", "fk_confirmed_service_day_staff"),
        ("constraints", "constraint_name", "chk_service_date_adjustment_snapshot"),
    ):
        incomplete = deepcopy(exact_snapshot)
        incomplete[collection] = [
            row for row in incomplete[collection] if row[key] != object_name
        ]
        assert migration.local_additive_descriptor_state(incomplete, descriptor, ARTIFACT) == "partial"


def test_additive_allowlist_accepts_only_immutable_1082_index_replacement():
    path = migration.ROOT / "db" / "schema_parts" / ARTIFACT
    statement = migration.split_sql(path.read_text(encoding="utf-8"))[1]
    assert migration._local_classify_statement(statement) == "scheduling_shift_index_widen"
    for forbidden in (
        statement.replace(PREDECESSOR_INDEX["index_name"], "another_index"),
        statement.replace("generation_id,work_date,effective_marker", "generation_id,work_date"),
        "ALTER TABLE staff_schedule DROP INDEX uq_staff_schedule_generation_owner",
        "ALTER TABLE staff_schedule DROP COLUMN work_date",
    ):
        assert forbidden != statement
        with pytest.raises(migration.LocalAdditiveBlocked) as blocked:
            migration._local_classify_statement(forbidden)
        assert blocked.value.code == "forbidden_sql_effect"
