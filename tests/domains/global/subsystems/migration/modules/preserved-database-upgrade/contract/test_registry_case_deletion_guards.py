"""Root case guard migration must recognize only complete, exact definitions."""
from copy import deepcopy
import pytest
from scripts import migrate_preserved_database_additive_schema as m
from scripts.compact_fresh_schema import load_compact_plan
from scripts.schema_assembly import load_schema_assembly

ARTIFACT = "1060_registry_case_deletion_guards.sql"
SIGNING_ARTIFACT = "1080_registry_case_deletion_signing_guards.sql"

def snapshot(which):
    catalog = m._registry_guard_metadata()
    return {"triggers": [{"trigger_name": name, **body} for name, body in catalog[which].items()]}

def test_exact_predecessor_successor_partial_and_drift():
    before, after = snapshot("predecessor_triggers"), snapshot("successor_triggers")
    assert m._registry_guard_snapshot(before, ARTIFACT)[1] == "absent"
    assert m._registry_guard_snapshot(after, ARTIFACT)[1] == "exact"
    mixed = deepcopy(after); mixed["triggers"][0] = before["triggers"][0]
    assert m._registry_guard_snapshot(mixed, ARTIFACT)[1] == "partial"
    missing = deepcopy(after); missing["triggers"].pop()
    assert m._registry_guard_snapshot(missing, ARTIFACT)[1] == "partial"
    drift = deepcopy(after); drift["triggers"][0]["action_statement"] += " unsafe"
    assert m._registry_guard_snapshot(drift, ARTIFACT)[1] == "drift"

def test_only_exact_guards_normalize_for_historical_release_checks():
    after = snapshot("successor_triggers"); saved = deepcopy(after)
    normalized, state = m._registry_guard_snapshot(after, "111_client_finance_ledger.sql")
    assert state is None and after == saved
    assert normalized["triggers"] == snapshot("predecessor_triggers")["triggers"]
    changed = deepcopy(after); changed["triggers"][0]["action_statement"] += " unsafe"
    normalized, _ = m._registry_guard_snapshot(changed, "111_client_finance_ledger.sql")
    assert normalized["triggers"][0] == changed["triggers"][0]

def test_guard_release_and_trigger_effect_classification():
    statements = m.split_sql((m.ROOT / "db/schema_parts" / ARTIFACT).read_text(encoding="utf-8"))
    assert len(statements) == 2 * len(m._registry_guard_metadata()["successor_triggers"])
    assert {m._local_classify_statement(s) for s in statements} == {"drop_trigger_if_exists", "create_trigger"}
    safe = "CREATE TRIGGER t BEFORE DELETE ON example FOR EACH ROW BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='create insert update are diagnostic words'; END"
    assert m._local_classify_statement(safe) == "create_trigger"
    for verb in ("INSERT INTO ledger VALUES (1)", "DELETE FROM ledger", "UPDATE ledger SET v=1"):
        with pytest.raises(m.LocalAdditiveBlocked): m._local_classify_statement("CREATE TRIGGER t BEFORE DELETE ON example FOR EACH ROW BEGIN " + verb + "; END")


def test_group_history_delete_guards_compose_with_registry_guards_without_hiding_drift():
    artifact = "1078_line_order_group_history_delete_guards.sql"
    before = snapshot("successor_triggers")
    contracts = m._line_group_history_guard_metadata()["successor_triggers"]
    after = {"triggers": [
        {"trigger_name": row["trigger_name"], **contracts[row["trigger_name"]]}
        if row["trigger_name"] in contracts else row
        for row in before["triggers"]
    ]}
    metadata = {"columns": [], "indexes": [], "constraints": [], "key_columns": [],
                "foreign_keys": [], "show_create_tables": {}, "views": []}
    assert m._owned_classification({**metadata, **before})[artifact] == "absent"
    assert m._owned_classification({**metadata, **after})[artifact] == "exact"
    assert m._registry_guard_snapshot(after, artifact)[1] == "exact"
    assert m._registry_guard_snapshot(after, ARTIFACT)[1] == "exact"

    mixed = deepcopy(after)
    target = next(index for index, row in enumerate(before["triggers"]) if row["trigger_name"] in contracts)
    mixed["triggers"][target] = before["triggers"][target]
    assert m._registry_guard_snapshot(mixed, artifact)[1] == "partial"
    mixed["triggers"][target] = {**mixed["triggers"][target], "action_statement": "unrecognized definition"}
    assert m._registry_guard_snapshot(mixed, artifact)[1] == "drift"

    statements = m.split_sql((m.ROOT / "db/schema_parts" / artifact).read_text(encoding="utf-8"))
    assert len(statements) == 4
    assert {m._local_classify_statement(statement) for statement in statements} == {"drop_trigger_if_exists", "create_trigger"}


def test_signing_guard_release_matches_fresh_and_preserves_latest_guard_conditions():
    assert m._local_ordered_upgrade_entries()[-1]["artifact"]["name"] == SIGNING_ARTIFACT
    assert load_schema_assembly().active_artifact_paths[-1].name == SIGNING_ARTIFACT
    assert load_compact_plan()["release_id"] == "labor-union-validation-schema-registry-case-deletion-signing-v1"
    successor, latest, _, _ = m._registry_case_deletion_signing_metadata()
    descriptor = m._canonical_artifact_descriptor(SIGNING_ARTIFACT)
    assert successor == descriptor["triggers"]
    assert set(successor) == set(latest)
    for name, expected in successor.items():
        action = expected["action_statement"]
        assert "signed_received" not in action and "contract_completed" not in action
        assert "registry_delete/v1" in action and "admin_command_receipts" in action
        for context in ("@line_order_group_history_delete_key", "@line_delivery_retention_key"):
            assert (context in action) == (context in latest[name]["action_statement"])
    statements = m.split_sql((m.ROOT / "db/schema_parts" / SIGNING_ARTIFACT).read_text(encoding="utf-8"))
    assert len(statements) == 2 * len(successor)
    assert {m._local_classify_statement(statement) for statement in statements} == {"drop_trigger_if_exists", "create_trigger"}


def test_signing_guard_recognizes_predecessors_and_preserves_historical_classification():
    successor, latest, before, original = m._registry_case_deletion_signing_metadata()
    for predecessor in (latest, before, original):
        previous = {"triggers": [{"trigger_name": name, **meta} for name, meta in predecessor.items()]}
        assert m._registry_guard_snapshot(previous, SIGNING_ARTIFACT)[1] == "absent"
    after = {"triggers": [{"trigger_name": name, **meta} for name, meta in successor.items()]}
    saved = deepcopy(after)
    for artifact in (SIGNING_ARTIFACT, ARTIFACT, m._LINE_GROUP_HISTORY_DELETE_ARTIFACT, m._LINE_DELIVERY_RETENTION_ARTIFACT):
        assert m._registry_guard_snapshot(after, artifact)[1] == "exact"
    assert after == saved
    missing = {"triggers": after["triggers"][1:]}
    assert m._registry_guard_snapshot(missing, SIGNING_ARTIFACT)[1] == "partial"
    name = after["triggers"][0]["trigger_name"]
    mixed = {"triggers": [{"trigger_name": name, **latest[name]}, *after["triggers"][1:]]}
    assert m._registry_guard_snapshot(mixed, SIGNING_ARTIFACT)[1] == "partial"
    drift = deepcopy(after)
    drift["triggers"][0]["action_statement"] += " unsafe"
    assert m._registry_guard_snapshot(drift, SIGNING_ARTIFACT)[1] == "drift"
    assert m._registry_guard_snapshot(drift, ARTIFACT)[1] == "drift"
