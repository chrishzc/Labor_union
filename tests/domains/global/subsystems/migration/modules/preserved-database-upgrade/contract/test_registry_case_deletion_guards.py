"""Root case guard migration must recognize only complete, exact definitions."""
from copy import deepcopy
import pytest
from scripts import migrate_preserved_database_additive_schema as m

ARTIFACT = "1060_registry_case_deletion_guards.sql"

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
