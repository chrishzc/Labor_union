"""Root case guard migration must recognize only complete, exact definitions."""
from copy import deepcopy
import json
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


@pytest.fixture(scope="module")
def signing_qualification():
    return m._local_discover_qualification(
        release_id="labor-union-registry-case-deletion-signing-2026-11-20-v1", artifact_name=SIGNING_ARTIFACT)


@pytest.fixture
def interrupted_signing_source(monkeypatch, tmp_path, signing_qualification, request):
    source = "lu_test_interrupted_signing"
    release = "labor-union-registry-case-deletion-signing-2026-11-20-v1"
    qualification = signing_qualification
    monkeypatch.setattr(m, "_local_discover_qualification", lambda **_: qualification)
    monkeypatch.setattr(m, "_local_verify_prerequisite_metadata", lambda *_: None)
    related = (ARTIFACT, m._LINE_GROUP_HISTORY_DELETE_ARTIFACT, m._LINE_DELIVERY_RETENTION_ARTIFACT, SIGNING_ARTIFACT)
    monkeypatch.setattr(m, "_upgrade_admission_states", lambda snap: {
        part: m._registry_guard_snapshot(snap, part)[1] for part in related
    })
    predecessor = {}
    for part in related[:-1]:
        for statement in m.split_sql((m.ROOT / "db/schema_parts" / part).read_text(encoding="utf-8")):
            if m._local_classify_statement(statement) == "create_trigger":
                row = m._registry_signing_recovery_trigger(statement)
                predecessor[row["trigger_name"]] = row
    rendering = getattr(request, "param", "canonical")
    if rendering == "restored_crlf":
        for row in predecessor.values():
            row["action_statement"] = row["action_statement"].replace("\n", "\r\n")
    elif rendering == "restored_spacing":
        for row in predecessor.values():
            row["action_statement"] = row["action_statement"].replace("BEGIN\n", "BEGIN  \n")
    baseline = {"columns": [], "indexes": [], "triggers": [predecessor[name] for name in sorted(predecessor)],
                "constraints": [], "key_columns": [], "foreign_keys": [], "show_create_tables": {}, "views": []}
    baseline_sha = m._sha256_bytes(m._canonical_json(baseline))
    statements = m.split_sql((m.ROOT / "db/schema_parts" / SIGNING_ARTIFACT).read_text(encoding="utf-8"))
    rows = {"data_row_counts": {}, "data_fingerprints": {}, "data_fingerprint_sha256": m._local_data_fingerprint({})}
    monkeypatch.setattr(m, "_local_capture_backup_rows", lambda *_: rows)
    identity = {"database": source, "server": "fixture-server", "host": "fixture.invalid", "port": 3306}
    monkeypatch.setattr(m, "server_identity", lambda *_: identity)
    backup_path = tmp_path / "fast_additive" / f"{source}.{release}.backup.receipt.json"
    backup_path.parent.mkdir()
    dump = backup_path.with_suffix(".sql")
    dump_text = m.MYSQL_DUMP_MARKER.decode() + f"\n-- Database: {source}\nDELIMITER ;;\n"
    for row in predecessor.values():
        dump_text += (
            "/*!50003 CREATE*/ /*!50017 DEFINER=`fixture`@`%`*/ /*!50003 TRIGGER "
            f"`{row['trigger_name']}` {row['action_timing']} {row['event_manipulation']} "
            f"ON `{row['event_object_table']}` FOR EACH ROW {row['action_statement']} */;;\n"
        )
    dump_text += "DELIMITER ;\n"
    dump.write_bytes(dump_text.replace("\n", "\r\n").encode())
    qualification = {**qualification, "metadata_backup": {**qualification["metadata_backup"], "data_row_counts": {}}}
    backup = {"kind": "local_additive_source_backup", "release_id": release, **identity,
              "schema_sha256": baseline_sha, "sha256": m._sha256_file(dump), **rows}
    backup_path.write_text(json.dumps(backup), encoding="utf-8")
    previous = m._local_append_event(tmp_path, source, release, "baseline_captured",
        source_database=source, source_schema_sha256=baseline_sha,
        statement_hashes=[m._local_digest(s.encode()) for s in statements],
        data_fingerprint_sha256=rows["data_fingerprint_sha256"])
    replayed = dict(predecessor)
    for ordinal, statement in enumerate(statements[:29], 1):
        fields = {"source_database": source, "source_schema_sha256": baseline_sha, "ordinal": ordinal,
                  "statement_sha256": m._local_digest(statement.encode()), "classification": m._local_classify_statement(statement)}
        previous = m._local_append_event(tmp_path, source, release, "statement_started", previous, **fields)
        if ordinal % 2:
            replayed.pop(statement.split("`")[1])
        else:
            row = m._registry_signing_recovery_trigger(statement)
            if rendering != "canonical":
                row["action_statement"] = row["action_statement"].replace("\n", "\r\n")
            replayed[row["trigger_name"]] = row
        previous = m._local_append_event(tmp_path, source, release, "statement_verified", previous, outcome="applied", **fields)
    current = {**baseline, "triggers": [replayed[name] for name in sorted(replayed)]}
    current["sha256"] = m._sha256_bytes(m._canonical_json(current))
    return source, release, current, tmp_path, backup_path, statements


def test_interrupted_signing_source_admits_only_hash_bound_prefix_and_original_backup(interrupted_signing_source):
    source, _, current, root, _, _ = interrupted_signing_source
    saved = deepcopy(current)
    evidence = m.qualify_registry_signing_source_recovery(None, source, current, receipt_root=root)
    assert evidence["verified_prefix_length"] == 29
    assert evidence["source_schema_sha256"] == current["sha256"]
    assert SIGNING_ARTIFACT in evidence["allowed_partial_artifacts"]
    assert "trg_case_payroll_policy_snapshots_before_delete" not in {r["trigger_name"] for r in current["triggers"]}
    assert current == saved


@pytest.mark.parametrize("interrupted_signing_source", ["restored_crlf", "restored_spacing"], indirect=True)
def test_interrupted_signing_source_uses_original_backup_rendering(interrupted_signing_source):
    source, _, current, root, _, _ = interrupted_signing_source
    saved = deepcopy(current)
    evidence = m.qualify_registry_signing_source_recovery(None, source, current, receipt_root=root)
    assert evidence["verified_prefix_length"] == 29
    assert current == saved


def test_signing_backup_trigger_parser_preserves_version_comments_inside_literals(tmp_path):
    name = "trg_fixture_before_delete"
    body = "BEGIN SET @message = 'literal /*!50003 CREATE*/ and */;;'; END"
    dump = tmp_path / "original.sql"
    dump.write_text(
        "/*!50003 CREATE*/ /*!50017 DEFINER=`fixture`@`%`*/ /*!50003 TRIGGER "
        f"`{name}` BEFORE DELETE ON `fixture` FOR EACH ROW {body} */;;\n",
        encoding="utf-8",
    )
    assert m._registry_signing_backup_triggers(dump, {name})[name]["action_statement"] == body


@pytest.mark.parametrize("fault", ["missing_journal", "tampered_journal", "foreign_source", "uncertain_ddl",
    "schema_drift", "noncanonical_progress", "missing_backup", "wrong_host", "wrong_server", "wrong_release",
    "wrong_baseline", "tampered_dump", "changed_rows", "missing_backup_triggers", "duplicate_backup_trigger",
    "backup_trigger_drift"])
def test_interrupted_signing_source_rejects_unproven_recovery(interrupted_signing_source, monkeypatch, fault):
    source, release, current, root, backup_path, statements = interrupted_signing_source
    journal = m._local_journal_path(root, source, release)
    if fault == "missing_journal":
        journal.unlink()
    elif fault == "tampered_journal":
        journal.write_text(journal.read_text(encoding="utf-8").replace('"applied"', '"unknown"', 1), encoding="utf-8")
    elif fault == "foreign_source":
        source += "_foreign"
    elif fault == "uncertain_ddl":
        previous = m._local_read_events(root, source, release)[-1]
        m._local_append_event(root, source, release, "statement_started", previous,
            source_database=source, source_schema_sha256=previous["source_schema_sha256"], ordinal=30,
            statement_sha256=m._local_digest(statements[29].encode()), classification="create_trigger")
    elif fault in {"schema_drift", "noncanonical_progress"}:
        if fault == "schema_drift":
            current["views"].append({"table_name": "foreign_view", "view_definition": "select 1"})
        else:
            current["triggers"][0]["action_statement"] += " changed"
        current["sha256"] = m._sha256_bytes(m._canonical_json({k: v for k, v in current.items() if k != "sha256"}))
    elif fault == "missing_backup":
        backup_path.unlink()
    elif fault == "tampered_dump":
        with backup_path.with_suffix(".sql").open("ab") as handle:
            handle.write(b"changed")
    elif fault == "changed_rows":
        monkeypatch.setattr(m, "_local_capture_backup_rows", lambda *_: {"data_row_counts": {"unexpected": 1}, "data_fingerprints": {}, "data_fingerprint_sha256": "f" * 64})
    elif fault in {"missing_backup_triggers", "duplicate_backup_trigger", "backup_trigger_drift"}:
        dump = backup_path.with_suffix(".sql")
        content = dump.read_bytes()
        if fault == "missing_backup_triggers":
            content = m.MYSQL_DUMP_MARKER + f"\n-- Database: {source}\n".encode()
        elif fault == "duplicate_backup_trigger":
            start = content.index(b"/*!50003 CREATE*/")
            end = content.index(b" */;;", start) + len(b" */;;")
            content += b"\r\n" + content[start:end] + b"\r\n"
        else:
            content = content.replace(b"FOR EACH ROW BEGIN", b"FOR EACH ROW BEGIN SET @untrusted = 1;", 1)
        dump.write_bytes(content)
        backup = json.loads(backup_path.read_text(encoding="utf-8"))
        backup["sha256"] = m._sha256_file(dump)
        backup_path.write_text(json.dumps(backup), encoding="utf-8")
    else:
        backup = json.loads(backup_path.read_text(encoding="utf-8"))
        key = {"wrong_host": "host", "wrong_server": "server", "wrong_release": "release_id", "wrong_baseline": "schema_sha256"}[fault]
        backup[key] = "foreign"
        backup_path.write_text(json.dumps(backup), encoding="utf-8")
    with pytest.raises((m.UpgradeBlocked, m.LocalAdditiveBlocked)):
        m.qualify_registry_signing_source_recovery(None, source, current, receipt_root=root)


def test_interrupted_signing_plan_evidence_is_fingerprint_bound():
    plan = {"source_recovery": {"journal_event_digest": "original"}}
    plan["plan_fingerprint"] = m._sha256_bytes(m._canonical_json(plan))
    fresh = {**plan, "source_recovery": {"journal_event_digest": "changed"}}
    with pytest.raises(m.UpgradeBlocked, match="source_recovery"):
        m._validate_plan_integrity(plan, fresh)


@pytest.mark.parametrize("completed", [False, True])
def test_clean_predecessor_and_completed_signing_plan_do_not_require_recovery(
    interrupted_signing_source, monkeypatch, completed,
):
    source, _, current, root, _, statements = interrupted_signing_source
    selected = {}
    parts = [ARTIFACT, m._LINE_GROUP_HISTORY_DELETE_ARTIFACT, m._LINE_DELIVERY_RETENTION_ARTIFACT]
    for part in parts:
        for statement in m.split_sql((m.ROOT / "db/schema_parts" / part).read_text(encoding="utf-8")):
            if m._local_classify_statement(statement) == "create_trigger":
                row = m._registry_signing_recovery_trigger(statement)
                selected[row["trigger_name"]] = row
    if completed:
        selected = {row["trigger_name"]: row for statement in statements
                    if m._local_classify_statement(statement) == "create_trigger"
                    for row in (m._registry_signing_recovery_trigger(statement),)}
    current["triggers"] = [selected[name] for name in sorted(selected)]
    current["sha256"] = m._sha256_bytes(m._canonical_json({k: v for k, v in current.items() if k != "sha256"}))
    monkeypatch.setattr(m, "_schema_snapshot", lambda *_: current)
    monkeypatch.setattr(m, "database_exists", lambda *_: False)
    monkeypatch.setattr(m, "_table_evidence", lambda *_: {})
    monkeypatch.setattr(m, "_legacy_knowledge_rebuild_plan", lambda *_: {"eligible": False})
    monkeypatch.setattr(m, "qualify_registry_signing_source_recovery", lambda *_args, **_kwargs:
                        pytest.fail("canonical source does not need interrupted-source authority"))
    plan = m.build_plan(None, source, "lu_nas_upgrade_fixture", source_recovery_root=root)
    assert plan["status"] == "ready" and "source_recovery" not in plan


def test_recovery_apply_revalidates_original_files_before_candidate_ddl(interrupted_signing_source, monkeypatch):
    source, _, current, root, _, _ = interrupted_signing_source
    monkeypatch.setattr(m, "_schema_snapshot", lambda *_: current)
    monkeypatch.setattr(m, "database_exists", lambda *_: False)
    monkeypatch.setattr(m, "_table_evidence", lambda *_: {})
    monkeypatch.setattr(m, "_legacy_knowledge_rebuild_plan", lambda *_: {"eligible": False})
    plan = m.build_plan(None, source, "lu_nas_upgrade_fixture", source_recovery_root=root)
    plan_path, operation_path = root / "plan.json", root / "operation.json"
    m.write_receipt(plan_path, plan)
    m.write_receipt(operation_path, {"status": "restored"})
    with pytest.raises(m.UpgradeBlocked, match="requires fresh"):
        m.apply_schema(None, source, "lu_nas_upgrade_fixture", plan_path, operation_path)
    m._local_journal_path(root, source, plan["source_recovery"]["release_id"]).unlink()
    with pytest.raises(m.UpgradeBlocked, match="original journal"):
        m.apply_schema(None, source, "lu_nas_upgrade_fixture", plan_path, operation_path,
                       source_recovery_root=root)
