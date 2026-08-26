"""
File: test_local_database_additive_runner.py
Description: 驗證本機 qualified additive runner 的資格、SQL allowlist、journal 與安全邊界。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import local_database_additive_update as additive
from scripts import migrate_preserved_database_additive_schema as migration
from scripts import update_local_database as update


def _option_b_receipt() -> Path:
    return (
        migration.ROOT
        / "validation"
        / "receipts"
        / "phase4"
        / "PROV-20260821-local-additive-qualification-rich-menu-option-b.json"
    )


def test_qualification_is_canonical_and_option_b_counts() -> None:
    qualification = migration.local_additive_release_qualification(
        "labor-union-line-rich-menu-publication-step-saga-2026-08-20-v1"
    )
    assert qualification["release_id"].endswith("2026-08-20-v1")
    option_b = next(item for item in qualification["schema_artifacts"] if item["name"].startswith("1001_"))
    assert option_b["data_effect"] == "schema_only"
    assert all(key in option_b["descriptor"] for key in ("indexes", "foreign_keys", "checks", "triggers"))


def test_statement_classifier_rejects_data_and_destructive_sql() -> None:
    assert additive._classify_statement("CREATE TABLE t (id int)") == "create_table"
    assert additive._classify_statement("ALTER TABLE t ADD COLUMN x int") == "alter_add_only"
    for sql in ("INSERT INTO t VALUES (1)", "UPDATE t SET x=1", "DELETE FROM t", "DROP TABLE t", "TRUNCATE t"):
        with pytest.raises(additive.LocalAdditiveBlocked, match="allowlist"):
            additive._classify_statement(sql)
    with pytest.raises(additive.LocalAdditiveBlocked, match="CTAS"):
        additive._classify_statement("CREATE TABLE copied AS SELECT * FROM source")
    for sql in (
        "ALTER TABLE t ADD COLUMN x int, DROP COLUMN y",
        "CREATE TRIGGER trg AFTER INSERT ON t FOR EACH ROW BEGIN INSERT INTO log VALUES (1); END",
    ):
        with pytest.raises(additive.LocalAdditiveBlocked):
            additive._classify_statement(sql)


def test_column_contract_detects_stored_generated_column() -> None:
    name, contract = migration._parse_column_definition(
        "active_hold_scope_key VARCHAR(191)\n"
        "GENERATED ALWAYS AS (CASE WHEN automation_hold_state = 'active'\n"
        "THEN hold_scope_ref ELSE NULL END) STORED"
    )

    assert name == "active_hold_scope_key"
    assert contract["extra"] == "stored generated"


def test_column_contract_detects_virtual_and_ignores_ordinary_text() -> None:
    _, virtual = migration._parse_column_definition(
        "virtual_key VARCHAR(191) GENERATED ALWAYS AS (LOWER(source_key)) VIRTUAL"
    )
    _, ordinary = migration._parse_column_definition(
        "description VARCHAR(191) DEFAULT 'GENERATED ALWAYS AS (x) STORED'"
    )

    assert virtual["extra"] == "virtual generated"
    assert ordinary["extra"] == ""


def test_qualification_receipt_is_portable_and_digest_verified() -> None:
    receipt = additive._discover_qualification(_option_b_receipt())
    assert receipt["metadata_backup"]["status"] == "verified"
    assert receipt["artifact"]["dependency_contracts"] == {}
    assert receipt["artifact"]["dependencies"] == []
    prerequisites = {
        item["name"]: item for item in receipt["local_prerequisites"]
    }
    assert set(prerequisites) == {
        "156_line_publication_media_order_group.sql",
        "159_line_messaging_publication_runtime.sql",
    }
    for item in prerequisites.values():
        path = Path(migration.ROOT) / item["relative_path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
        assert item["required_state"] == "exact"
    assert receipt["payload_digest"] == additive._payload_digest(receipt)


def test_declared_rich_menu_prerequisites_still_validate() -> None:
    receipt = additive._discover_qualification(_option_b_receipt())

    prerequisites = migration._local_validate_prerequisite_policy(receipt)

    assert {item["name"] for item in prerequisites} == {
        "156_line_publication_media_order_group.sql",
        "159_line_messaging_publication_runtime.sql",
    }


def test_generic_receipt_without_prerequisites_skips_optional_policy() -> None:
    assert migration._local_validate_prerequisite_policy({}) == []


def test_target_projection_allows_unrelated_full_schema_drift_when_exact() -> None:
    fingerprint = "d" * 64
    payload = {
        "fresh_bootstrap": {"schema_fingerprint": "a" * 64},
        "preserve_data_candidate": {"candidate_schema_fingerprint": "b" * 64},
        "target_projection": {
            "contract": "local-additive-target-projection/v1",
            "artifact_name": "1002_customer_service_human_escalation.sql",
            "descriptor_sha256": "d" * 64,
            "fresh_state": "exact",
            "preserve_candidate_state": "exact",
            "fresh_fingerprint": fingerprint,
            "preserve_candidate_fingerprint": fingerprint,
        },
        "policy_evidence": {
            "fresh_target_projection_fingerprint": fingerprint,
            "preserve_candidate_target_projection_fingerprint": fingerprint,
        },
    }

    migration._local_validate_target_projection(
        payload,
        {"name": "1002_customer_service_human_escalation.sql"},
        "d" * 64,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("fresh_state", "partial"),
        ("preserve_candidate_state", "drift"),
        ("descriptor_sha256", "e" * 64),
        ("preserve_candidate_fingerprint", "f" * 64),
    ),
)
def test_target_projection_fails_closed_on_non_exact_or_mismatched_evidence(
    field, value
) -> None:
    fingerprint = "d" * 64
    projection = {
        "contract": "local-additive-target-projection/v1",
        "artifact_name": "1002_customer_service_human_escalation.sql",
        "descriptor_sha256": "d" * 64,
        "fresh_state": "exact",
        "preserve_candidate_state": "exact",
        "fresh_fingerprint": fingerprint,
        "preserve_candidate_fingerprint": fingerprint,
    }
    projection[field] = value
    payload = {
        "fresh_bootstrap": {"schema_fingerprint": "a" * 64},
        "preserve_data_candidate": {"candidate_schema_fingerprint": "b" * 64},
        "target_projection": projection,
        "policy_evidence": {
            "fresh_target_projection_fingerprint": fingerprint,
            "preserve_candidate_target_projection_fingerprint": projection[
                "preserve_candidate_fingerprint"
            ],
        },
    }

    with pytest.raises(migration.LocalAdditiveBlocked):
        migration._local_validate_target_projection(
            payload,
            {"name": "1002_customer_service_human_escalation.sql"},
            "d" * 64,
        )


def test_declared_prerequisite_with_missing_fields_fails_closed() -> None:
    with pytest.raises(
        migration.LocalAdditiveBlocked,
        match="local additive schema prerequisite contract is invalid",
    ):
        migration._local_validate_prerequisite_policy(
            {"local_prerequisites": [{"name": "missing-fields.sql"}]}
        )


def test_hash_verification_uses_real_release_selection_descriptor_shape() -> None:
    qualification = migration._local_discover_qualification(_option_b_receipt())
    assert isinstance(migration.RELEASE_MANIFEST, migration.ReleaseSelection)
    assert not hasattr(migration.RELEASE_MANIFEST, "descriptor_artifact")
    migration._local_verify_hashes(qualification)


def test_local_manifest_selector_ignores_same_release_descriptor(monkeypatch, tmp_path) -> None:
    release_dir = tmp_path / "db" / "migration_releases"
    release_dir.mkdir(parents=True)
    release_id = "test-release-v1"
    manifest = release_dir / "manifest.json"
    manifest.write_text(
        '{"contract":"migration-release-manifest/v1","release_id":"test-release-v1"}',
        encoding="utf-8",
    )
    (release_dir / "manifest.descriptors.json").write_text(
        '{"contract":"preserve-data/database-descriptor/v1","release_id":"test-release-v1"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(migration, "ROOT", tmp_path)

    assert migration._local_manifest_path(release_id) == manifest.resolve()


def test_local_manifest_selector_blocks_duplicate_formal_manifests(monkeypatch, tmp_path) -> None:
    release_dir = tmp_path / "db" / "migration_releases"
    release_dir.mkdir(parents=True)
    payload = '{"contract":"migration-release-manifest/v1","release_id":"test-release-v1"}'
    (release_dir / "manifest-a.json").write_text(payload, encoding="utf-8")
    (release_dir / "manifest-b.json").write_text(payload, encoding="utf-8")
    monkeypatch.setattr(migration, "ROOT", tmp_path)

    with pytest.raises(migration.LocalAdditiveBlocked, match="missing or ambiguous"):
        migration._local_manifest_path("test-release-v1")


def test_explicit_qualification_selects_only_a_published_receipt(
    monkeypatch, tmp_path
) -> None:
    receipt_root = tmp_path / "validation" / "receipts"
    receipt_root.mkdir(parents=True)
    selected = receipt_root / "PROV-selected.json"
    selected.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(migration, "ROOT", tmp_path)
    monkeypatch.setattr(
        migration,
        "_local_validate_qualification",
        lambda path: {"selected": path.name},
    )

    assert migration._local_discover_qualification(selected) == {
        "selected": "PROV-selected.json"
    }
    nested = receipt_root / "phase4" / "PROV-nested.json"
    nested.parent.mkdir()
    nested.write_text("{}", encoding="utf-8")
    assert migration._local_discover_qualification(nested) == {
        "selected": "PROV-nested.json"
    }
    with pytest.raises(migration.LocalAdditiveBlocked):
        migration._local_discover_qualification(tmp_path / "scratch.json")


def test_automatic_qualification_selects_only_the_current_release(
    monkeypatch, tmp_path
) -> None:
    receipt_root = tmp_path / "validation" / "receipts"
    receipt_root.mkdir(parents=True)
    old = receipt_root / "PROV-old-local-additive-qualification-v1.json"
    current = receipt_root / "PROV-current-local-additive-qualification-v1.json"
    old.write_text("{}", encoding="utf-8")
    current.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(migration, "ROOT", tmp_path)
    monkeypatch.setattr(
        migration,
        "RELEASE_MANIFEST",
        SimpleNamespace(release_id="current", fingerprint="current-fingerprint"),
    )
    monkeypatch.setattr(
        migration,
        "_local_validate_qualification",
        lambda path: {
            "release_id": "current" if path == current else "old",
            "release_fingerprint": (
                "current-fingerprint" if path == current else "old-fingerprint"
            ),
            "_path": path,
        },
    )

    assert migration._local_discover_qualification()["_path"] == current


def test_target_profile_blocks_union_db_without_connecting() -> None:
    with pytest.raises(additive.LocalAdditiveBlocked) as error:
        additive.plan(SimpleNamespace(), "union_db", receipt_root=Path("scratch"))
    assert error.value.code == "target_profile_blocked"


def test_preview_reuses_one_schema_snapshot_for_target_state(monkeypatch, tmp_path) -> None:
    source = "lu_test_dataset"
    snapshot = {
        "sha256": "a" * 64,
        "columns": [],
        "indexes": [],
        "foreign_keys": [],
        "constraints": [],
        "triggers": [],
    }
    artifact = {
        "name": "1001_line_rich_menu_publication_step_saga.sql",
        "relative_path": "db/schema_parts/1001_line_rich_menu_publication_step_saga.sql",
        "data_effect": "schema_only",
    }
    qualification = {
        "release_id": "release",
        "release_fingerprint": "fingerprint",
        "metadata_backup": {
            "database": source,
            "schema_sha256": snapshot["sha256"],
            "data_fingerprint_sha256": "b" * 64,
            "host": "127.0.0.1",
            "port": 3306,
        },
        "_canonical_artifact": artifact,
        "_path": migration.ROOT / "validation" / "receipts" / "qualification.json",
    }
    descriptor = {"tables": {}, "parent_columns": {}}
    calls = {"schema_snapshot": 0}

    def snapshot_once(*_args):
        calls["schema_snapshot"] += 1
        return snapshot

    monkeypatch.setattr(migration, "_local_discover_qualification", lambda: qualification)
    monkeypatch.setattr(migration, "_local_verify_hashes", lambda _qualification: None)
    monkeypatch.setattr(migration, "database_exists", lambda *_args: True)
    monkeypatch.setattr(migration, "_local_verify_backup_rows", lambda *_args: None)
    monkeypatch.setattr(migration, "split_sql", lambda _sql: ["CREATE TABLE t (id int)"])
    monkeypatch.setattr(migration, "_schema_snapshot", snapshot_once)
    monkeypatch.setattr(migration, "_local_verify_prerequisite_metadata", lambda *_args: None)
    monkeypatch.setattr(migration, "_local_read_events", lambda *_args: [])
    monkeypatch.setattr(
        migration,
        "_local_resume_context",
        lambda *_args: (snapshot["sha256"], {}),
    )
    monkeypatch.setattr(
        migration,
        "local_additive_release_qualification",
        lambda *_args: {"schema_artifacts": [{"descriptor": descriptor}]},
    )
    monkeypatch.setattr(migration, "_artifact_metadata_state", lambda *_args, **_kwargs: "exact")
    monkeypatch.setattr(
        migration,
        "server_identity",
        lambda *_args: {
            "database": source,
            "server": "server",
            "host": "127.0.0.1",
            "port": 3306,
        },
    )

    result = migration.local_additive_plan(
        SimpleNamespace(), source, receipt_root=tmp_path
    )

    assert result["status"] == "current"
    assert calls["schema_snapshot"] == 1


def test_apply_keeps_fresh_snapshot_after_maintenance_lock(monkeypatch, tmp_path) -> None:
    source = "lu_test_dataset"
    baseline = "a" * 64
    after_digest = "c" * 64
    snapshots = [
        {"sha256": baseline, "columns": [], "indexes": [], "foreign_keys": [], "constraints": [], "triggers": []},
        {"sha256": after_digest, "columns": [], "indexes": [], "foreign_keys": [], "constraints": [], "triggers": []},
    ]
    calls = {"schema_snapshot": 0}
    artifact = {
        "name": "1001_line_rich_menu_publication_step_saga.sql",
        "relative_path": "db/schema_parts/1001_line_rich_menu_publication_step_saga.sql",
    }
    qualification = {
        "release_id": "release",
        "_canonical_artifact": artifact,
        "metadata_backup": {"data_fingerprint_sha256": "b" * 64},
    }

    def schema_snapshot(*_args):
        calls["schema_snapshot"] += 1
        return snapshots.pop(0)

    class Connection:
        def cursor(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args):
            return None

        def close(self):
            return None

    class Lock:
        def __enter__(self):
            return None

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        migration,
        "local_additive_plan",
        lambda *_args, **_kwargs: {
            "status": "ready",
            "source_database": source,
            "source_schema_sha256": baseline,
            "release_id": "release",
            "artifact": artifact,
        },
    )
    monkeypatch.setattr(migration, "_local_discover_qualification", lambda: qualification)
    monkeypatch.setattr(migration, "split_sql", lambda _sql: [])
    monkeypatch.setattr(migration, "_local_read_events", lambda *_args: [])
    monkeypatch.setattr(migration, "_local_resume_context", lambda *_args: (baseline, {}))
    monkeypatch.setattr(migration, "_local_append_event", lambda *_args, **_kwargs: {"sequence": 1})
    monkeypatch.setattr(migration, "_local_maintenance_lock", lambda *_args: Lock())
    monkeypatch.setattr(migration, "_schema_snapshot", schema_snapshot)
    monkeypatch.setattr(migration, "_owned_classification", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(migration, "_local_connect", lambda *_args: Connection())
    monkeypatch.setattr(migration, "server_identity", lambda *_args: {"database": source})
    monkeypatch.setattr(
        migration,
        "local_additive_release_qualification",
        lambda *_args: {"schema_artifacts": [{"descriptor": {"tables": {}}}]},
    )
    monkeypatch.setattr(migration, "local_additive_descriptor_state", lambda *_args: "exact")

    result = migration.local_additive_apply(
        SimpleNamespace(), source, receipt_root=tmp_path
    )

    assert result["status"] == "completed"
    assert calls["schema_snapshot"] == 2
    assert not snapshots


def test_duration_guard_is_bounded(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(additive, "plan", lambda *_args, **_kwargs: {"status": "current"})
    with pytest.raises(additive.LocalAdditiveBlocked) as error:
        additive.apply(SimpleNamespace(), "lu_test_dataset", receipt_root=tmp_path, duration_guard_ms=30_001)
    assert error.value.code == "duration_invalid"


def test_journal_chain_detects_ordinal_or_digest_tampering(tmp_path) -> None:
    event = additive._append_event(tmp_path, "lu_test_dataset", "planned")
    assert event["sequence"] == 1
    assert additive._read_events(tmp_path, "lu_test_dataset")[0]["state"] == "planned"
    path = tmp_path / "fast_additive" / "lu_test_dataset.journal.jsonl"
    path.write_text(path.read_text(encoding="utf-8").replace("planned", "tampered"), encoding="utf-8")
    with pytest.raises(additive.LocalAdditiveBlocked, match="integrity"):
        additive._read_events(tmp_path, "lu_test_dataset")


def test_descriptor_state_rejects_owned_extra_indexes() -> None:
    qualification = migration.local_additive_release_qualification(
        "labor-union-line-rich-menu-publication-step-saga-2026-08-20-v1",
        "1001_line_rich_menu_publication_step_saga.sql",
    )
    descriptor = qualification["schema_artifacts"][0]["descriptor"]
    snapshot = {"columns": [], "indexes": [], "constraints": [], "key_columns": [], "foreign_keys": [], "triggers": [], "show_create_tables": {}, "views": []}
    table = next(iter(descriptor["tables"]))
    snapshot["indexes"].append({"table_name": table, "index_name": "PRIMARY", "non_unique": 0, "columns": "id"})
    snapshot["indexes"].append({"table_name": table, "index_name": "unexpected_owned_index", "non_unique": 1, "columns": "id"})
    assert migration.local_additive_descriptor_state(snapshot, descriptor, "1001_line_rich_menu_publication_step_saga.sql") == "drift"


def test_local_descriptor_state_does_not_defer_missing_owned_trigger() -> None:
    artifact = "1001_line_rich_menu_publication_step_saga.sql"
    descriptor = migration._canonical_artifact_descriptor(artifact)
    columns = [
        {
            "table_name": table,
            "column_name": name,
            **spec,
            "generation_expression": "",
        }
        for table, specs in {
            **descriptor["tables"],
            **descriptor["parent_columns"],
        }.items()
        for name, spec in specs.items()
    ]
    indexes = [
        {
            "table_name": table,
            "index_name": name,
            "non_unique": spec["non_unique"],
            "columns": ",".join(spec["columns"]),
        }
        for (table, name), spec in descriptor["indexes"].items()
    ]
    constraints = []
    key_columns = []
    foreign_keys = []
    for (table, name), spec in descriptor["foreign_keys"].items():
        constraints.append({
            "table_name": table,
            "constraint_name": name,
            "constraint_type": "FOREIGN KEY",
            "enforced": "YES",
            "check_clause": None,
        })
        foreign_keys.append({
            "table_name": table,
            "constraint_name": name,
            "update_rule": spec["update_rule"],
            "delete_rule": spec["delete_rule"],
        })
        for position, (column, referenced) in enumerate(
            zip(spec["columns"], spec["referenced_columns"], strict=True), 1
        ):
            key_columns.append({
                "table_name": table,
                "constraint_name": name,
                "column_name": column,
                "ordinal_position": position,
                "referenced_table_name": spec["referenced_table"],
                "referenced_column_name": referenced,
            })
    for (table, name), clause in descriptor["checks"].items():
        constraints.append({
            "table_name": table,
            "constraint_name": name,
            "constraint_type": "CHECK",
            "enforced": "YES",
            "check_clause": clause,
        })
    snapshot = {
        "columns": columns,
        "indexes": indexes,
        "constraints": constraints,
        "key_columns": key_columns,
        "foreign_keys": foreign_keys,
        "triggers": [
            {"trigger_name": name, **spec}
            for name, spec in descriptor["triggers"].items()
        ],
        "show_create_tables": {},
        "views": [],
    }
    missing_trigger = next(iter(descriptor["triggers"]))
    snapshot["triggers"] = [
        row for row in snapshot["triggers"]
        if row["trigger_name"] != missing_trigger
    ]
    assert migration.local_additive_descriptor_state(snapshot, descriptor, artifact) == "partial"


def test_local_prerequisite_projection_is_narrow_and_preserves_parent_contract() -> None:
    media = migration._local_prerequisite_descriptor(
        "156_line_publication_media_order_group.sql"
    )
    assert set(media["tables"]) == {"line_rich_menu_publication_tasks"}
    assert not media["parent_columns"]
    assert not media["triggers"]
    runtime = migration._local_prerequisite_descriptor(
        "159_line_messaging_publication_runtime.sql"
    )
    assert set(runtime["tables"]) == {"line_rich_menu_publication_step_receipts"}
    assert set(runtime["parent_columns"]["line_domain_outbox"]) == {
        "max_attempts", "error_message"
    }
    assert runtime["parent_columns"]["line_domain_outbox"]["max_attempts"] == {
        "column_type": "int unsigned", "is_nullable": "NO",
        "column_default": "3", "extra": "",
    }


def test_only_fk_named_nonunique_support_index_is_accepted() -> None:
    descriptor = {
        "foreign_keys": {
            ("child", "fk_child_parent"): {"columns": ("parent_id",)}
        }
    }
    indexes = {
        ("child", "fk_child_parent"): {
            "non_unique": 1, "columns": ("parent_id",)
        },
        ("child", "unrelated"): {
            "non_unique": 1, "columns": ("parent_id",)
        },
        ("child", "unique_parent"): {
            "non_unique": 0, "columns": ("parent_id",)
        },
    }
    assert migration._auto_fk_supporting_index_keys(
        indexes, descriptor, set(indexes)
    ) == {("child", "fk_child_parent")}


def test_narrow_prerequisite_ignores_unrelated_media_and_order_objects() -> None:
    descriptor = migration._local_prerequisite_descriptor(
        "156_line_publication_media_order_group.sql"
    )
    normalized = migration._normalize_local_descriptor(descriptor)
    columns = [
        {
            "table_name": table,
            "column_name": name,
            **spec,
        }
        for table, specs in normalized["tables"].items()
        for name, spec in specs.items()
    ]
    columns.append({
        "table_name": "line_media_records", "column_name": "id",
        "column_type": "bigint unsigned", "is_nullable": "NO",
        "column_default": None, "extra": "auto_increment",
    })
    indexes = [
        {
            "table_name": table,
            "index_name": name,
            "non_unique": contract["non_unique"],
            "columns": ",".join(contract["columns"]),
        }
        for (table, name), contract in normalized["indexes"].items()
    ]
    indexes.append({
        "table_name": "line_media_records", "index_name": "PRIMARY",
        "non_unique": 0, "columns": "id",
    })
    snapshot = {
        "columns": columns,
        "indexes": indexes,
        "constraints": [{
            "table_name": "line_rich_menu_publication_tasks",
            "constraint_name": "chk_line_rich_menu_definition",
            "constraint_type": "CHECK", "enforced": "YES",
            "check_clause": "JSON_TYPE(definition_snapshot) = 'OBJECT'",
        }],
        "key_columns": [], "foreign_keys": [], "triggers": [],
        "show_create_tables": {}, "views": [],
    }
    assert migration.local_additive_descriptor_state(
        snapshot, descriptor, "156_line_publication_media_order_group.sql"
    ) == "exact"


def test_resume_context_requires_immutable_baseline_and_rejects_unknown_started_statement() -> None:
    hashes = ["a" * 64, "b" * 64]
    with pytest.raises(additive.LocalAdditiveBlocked, match="immutable pre-apply baseline"):
        migration._local_resume_context(
            [{"state": "planned"}], "release", "source", hashes, "baseline"
        )
    events = [
        {"state": "baseline_captured", "release_id": "release", "source_database": "source", "source_schema_sha256": "baseline", "statement_hashes": hashes},
        {"state": "statement_started", "release_id": "release", "source_database": "source", "ordinal": 1, "statement_sha256": hashes[0]},
    ]
    with pytest.raises(additive.LocalAdditiveBlocked, match="unverified DDL outcome"):
        migration._local_resume_context(events, "release", "source", hashes, "after-partial")


def test_default_auto_route_never_calls_legacy_replacement(tmp_path, monkeypatch) -> None:
    config = SimpleNamespace(host="127.0.0.1")
    monkeypatch.setattr(update.migration, "config_from_env", lambda _path: (config, "lu_test_dataset"))
    monkeypatch.setattr(update, "resolve_mysql_container", lambda _value: "mysql_db")
    monkeypatch.setattr(update, "build_additive_preview", lambda *_args, **_kwargs: {"status": "current"})
    monkeypatch.setattr(update, "apply_additive_update", lambda *_args, **_kwargs: {"status": "completed"})
    monkeypatch.setattr(update, "apply_update", lambda *_args, **_kwargs: pytest.fail("legacy replacement route called"))
    result = update.update_local_database(environment_file=tmp_path / ".env", apply=True, confirm_configured_database=True)
    assert result["status"] == "completed"


def test_explicit_replacement_requires_allow_long_run(tmp_path, monkeypatch) -> None:
    config = SimpleNamespace(host="127.0.0.1")
    monkeypatch.setattr(update.migration, "config_from_env", lambda _path: (config, "lu_test_dataset"))
    monkeypatch.setattr(update, "resolve_mysql_container", lambda _value: "mysql_db")
    with pytest.raises(update.LocalDatabaseUpdateError, match="allow-long-run"):
        update.update_local_database(environment_file=tmp_path / ".env", strategy="replacement", apply=True, confirm_configured_database=True)
