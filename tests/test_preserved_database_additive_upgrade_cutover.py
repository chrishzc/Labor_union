from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

import scripts.migrate_preserved_database_additive_schema as migration
from scripts.migrate_preserved_database_additive_schema import (
    ROOT,
    UpgradeBlocked,
    apply_schema,
    build_plan,
    config_from_env,
    create_source_dump,
    database_exists,
    read_receipt,
    restore_candidate,
    rollback_environment,
    split_sql,
    switch_environment,
    validate_database_names,
    validate_dump,
    verify_candidate,
    write_receipt,
)
from services.anomaly_alert_detection import run_process_alert_scan


EXPECTED_SCANNER_CODES = {
    "ORDER-001",
    "ORDER-002",
    "ORDER-003",
    "ORDER-004",
    "BECLASS-001",
    "LINE-001",
    "LINE-005",
    "DOC-SEND-001",
    "IMPORT-003",
    "RECEIVABLE-001",
    "PAYOUT-001",
    "RETURN-001",
    "LINE-002",
    "LINE-004",
    "SCHEDULE-001",
    "SCHEDULE-002",
    "SCHEDULE-003",
    "SCHEDULE-005",
    "SCHEDULE-006",
    "IMPORT-006",
}


def test_database_identity_guards_fail_closed() -> None:
    with pytest.raises(UpgradeBlocked):
        validate_database_names("union_db", "union_db")
    with pytest.raises(UpgradeBlocked):
        validate_database_names("union_db", "bad-name;drop")


def test_sql_splitter_preserves_quoted_semicolons() -> None:
    assert split_sql("SELECT ';'; SELECT 2;") == ["SELECT ';'", "SELECT 2"]
    assert split_sql("-- comment;\nSELECT 1; # x;\nSELECT 2;") == [
        "SELECT 1",
        "SELECT 2",
    ]


class _FakeApplyCursor:
    def __init__(
        self, candidate: str, *, fail_statement: str | None = None
    ) -> None:
        self.candidate = candidate
        self.fail_statement = fail_statement
        self.executed: list[str] = []
        self._row: dict[str, object] | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement: str, parameters=None) -> None:
        if statement.startswith("SELECT DATABASE()"):
            self._row = {"db": self.candidate}
            return
        self.executed.append(statement)
        if statement == self.fail_statement:
            raise RuntimeError("injected statement interruption")

    def fetchone(self):
        return self._row


class _FakeApplyConnection:
    def __init__(self, cursor: _FakeApplyCursor) -> None:
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self) -> None:
        pass


class _FakeApplyConfig:
    def __init__(self, cursor: _FakeApplyCursor) -> None:
        self._cursor = cursor

    def connect(self, database=None):
        assert database in {None, self._cursor.candidate}
        return _FakeApplyConnection(self._cursor)


def _configure_fake_apply(
    monkeypatch: pytest.MonkeyPatch,
    schema_part: Path,
    snapshot_states: list[str],
) -> None:
    snapshots = iter(
        {"sha256": f"schema-{index}", "state": state}
        for index, state in enumerate(snapshot_states, start=1)
    )
    monkeypatch.setattr(migration, "SCHEMA_PARTS", (schema_part,))
    monkeypatch.setattr(
        migration,
        "build_plan",
        lambda config, source, candidate: {
            "source_schema_sha256": "source-schema",
            "source_data": {"orders": {"count": 1}},
            "source": {
                "database": source,
                "server": "test-server",
                "host": "127.0.0.1",
                "port": 3306,
            },
            "candidate_database": candidate,
            "schema_artifacts": [{"name": schema_part.name}],
            "phase_order": [schema_part.name],
        },
    )
    monkeypatch.setattr(
        migration, "_validate_plan_integrity", lambda plan, fresh: None
    )
    monkeypatch.setattr(migration, "database_exists", lambda *args: True)
    monkeypatch.setattr(
        migration,
        "server_identity",
        lambda config, database: {
            "database": database,
            "server": "test-server",
        },
    )
    monkeypatch.setattr(
        migration, "_schema_snapshot", lambda *args: next(snapshots)
    )
    monkeypatch.setattr(
        migration,
        "_owned_classification",
        lambda snapshot: {schema_part.name: snapshot["state"]},
    )
    monkeypatch.setattr(
        migration,
        "run_candidate_post_schema",
        lambda config, source, candidate, receipt, **kwargs: read_receipt(
            receipt
        ),
    )


def _write_fake_apply_receipts(
    tmp_path: Path, schema_part: Path
) -> tuple[Path, Path]:
    plan_path = tmp_path / "plan.json"
    operation_path = tmp_path / "operation.json"
    write_receipt(
        plan_path,
        {
            "status": "ready",
            "source_schema_sha256": "source-schema",
            "source_data": {"orders": {"count": 1}},
            "source": {"server": "test-server"},
        },
    )
    write_receipt(
        operation_path,
        {
            "status": "restored",
            "candidate_database": "candidate_db",
            "schema_steps": [],
        },
    )
    return plan_path, operation_path


def test_statement_interruption_receipt_never_claims_partial_schema_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schema_part = tmp_path / "part.sql"
    schema_part.write_text(
        "ALTER TABLE sample ADD COLUMN added INT; SELECT 2;",
        encoding="utf-8",
    )
    _configure_fake_apply(
        monkeypatch,
        schema_part,
        ["absent", "absent", "partial", "partial", "partial"],
    )
    cursor = _FakeApplyCursor(
        "candidate_db", fail_statement="SELECT 2"
    )
    plan_path, operation_path = _write_fake_apply_receipts(
        tmp_path, schema_part
    )
    with pytest.raises(RuntimeError, match="injected statement interruption"):
        apply_schema(
            _FakeApplyConfig(cursor),
            "source_db",
            "candidate_db",
            plan_path,
            operation_path,
        )
    receipt = read_receipt(operation_path)
    first, interrupted = receipt["schema_steps"]
    assert first["status"] == "applied"
    assert first["verification_status"] == "pending_part_completion"
    assert first["before_schema_sha256"] == "schema-2"
    assert first["after_schema_sha256"] == "schema-3"
    assert interrupted["status"] == "failed"
    assert interrupted["after_part_state"] == "partial"
    assert all(step["status"] != "exact" for step in receipt["schema_steps"])


@pytest.mark.parametrize("blocked_state", ["partial", "drift"])
def test_partial_or_drift_candidate_fails_closed_before_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    blocked_state: str,
) -> None:
    schema_part = tmp_path / "part.sql"
    schema_part.write_text("ALTER TABLE sample ADD COLUMN added INT;", "utf-8")
    _configure_fake_apply(monkeypatch, schema_part, [blocked_state])
    plan_path, operation_path = _write_fake_apply_receipts(
        tmp_path, schema_part
    )
    cursor = _FakeApplyCursor("candidate_db")
    with pytest.raises(UpgradeBlocked, match="partial/drift"):
        apply_schema(
            _FakeApplyConfig(cursor),
            "source_db",
            "candidate_db",
            plan_path,
            operation_path,
        )
    assert cursor.executed == []


def test_exact_part_replay_is_idempotently_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schema_part = tmp_path / "part.sql"
    schema_part.write_text("ALTER TABLE sample ADD COLUMN added INT;", "utf-8")
    _configure_fake_apply(monkeypatch, schema_part, ["exact", "exact"])
    plan_path, operation_path = _write_fake_apply_receipts(
        tmp_path, schema_part
    )
    cursor = _FakeApplyCursor("candidate_db")
    receipt = apply_schema(
        _FakeApplyConfig(cursor),
        "source_db",
        "candidate_db",
        plan_path,
        operation_path,
    )
    assert receipt["status"] == "schema_applied"
    assert cursor.executed == []
    assert receipt["schema_steps"][0]["outcome"] == "existing_part_skipped"


def test_partial_statement_receipt_continues_until_part_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schema_part = tmp_path / "part.sql"
    schema_part.write_text("SELECT 1; SELECT 2;", encoding="utf-8")
    _configure_fake_apply(
        monkeypatch,
        schema_part,
        ["absent", "absent", "partial", "partial", "exact", "exact"],
    )
    plan_path, operation_path = _write_fake_apply_receipts(
        tmp_path, schema_part
    )
    cursor = _FakeApplyCursor("candidate_db")
    receipt = apply_schema(
        _FakeApplyConfig(cursor),
        "source_db",
        "candidate_db",
        plan_path,
        operation_path,
    )
    first, second = receipt["schema_steps"]
    assert first["status"] == "applied"
    assert first["verification_status"] == "pending_part_completion"
    assert first["after_part_state"] == "partial"
    assert second["status"] == "exact"
    assert second["verification_status"] == "exact"
    assert cursor.executed == ["SELECT 1", "SELECT 2"]


def _snapshot_from_descriptor(descriptor: dict[str, object]):
    columns = []
    for table, specs in {
        **descriptor["tables"],
        **descriptor["parent_columns"],
    }.items():
        for name, spec in specs.items():
            columns.append(
                {
                    "table_name": table,
                    "column_name": name,
                    **spec,
                    "generation_expression": "",
                }
            )
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
        constraints.append(
            {
                "table_name": table,
                "constraint_name": name,
                "constraint_type": "FOREIGN KEY",
                "enforced": "YES",
                "check_clause": None,
            }
        )
        foreign_keys.append(
            {
                "table_name": table,
                "constraint_name": name,
                "update_rule": spec["update_rule"],
                "delete_rule": spec["delete_rule"],
            }
        )
        for position, (column, referenced) in enumerate(
            zip(
                spec["columns"],
                spec["referenced_columns"],
                strict=True,
            ),
            start=1,
        ):
            key_columns.append(
                {
                    "table_name": table,
                    "constraint_name": name,
                    "column_name": column,
                    "ordinal_position": position,
                    "referenced_table_name": spec["referenced_table"],
                    "referenced_column_name": referenced,
                }
            )
    for (table, name), clause in descriptor["checks"].items():
        constraints.append(
            {
                "table_name": table,
                "constraint_name": name,
                "constraint_type": "CHECK",
                "enforced": "YES",
                "check_clause": clause,
            }
        )
    triggers = [
        {"trigger_name": name, **spec}
        for name, spec in descriptor["triggers"].items()
    ]
    return {
        "columns": columns,
        "indexes": indexes,
        "constraints": constraints,
        "key_columns": key_columns,
        "foreign_keys": foreign_keys,
        "triggers": triggers,
        "views": [],
    }


def test_105_owned_column_subset_is_partial_then_exact() -> None:
    part = "105_order_service_time_terms.sql"
    descriptor = migration._canonical_artifact_descriptor(part)
    exact = _snapshot_from_descriptor(descriptor)
    assert migration._canonical_artifact_metadata_state(exact, part) == "exact"
    partial = {
        key: list(value) if isinstance(value, list) else value
        for key, value in exact.items()
    }
    partial["columns"] = [
        row for row in partial["columns"]
        if row["column_name"] != "service_end_day_offset"
    ]
    assert (
        migration._canonical_artifact_metadata_state(partial, part)
        == "partial"
    )


def _system_alert_transition_snapshot(
    stage: str,
    *,
    wrong_column: tuple[str, str] | None = None,
    wrong_updated_extra: bool = False,
    wrong_unique_index: bool = False,
) -> dict[str, object]:
    final = stage in {"tightened", "unique_index", "exact"}
    expanded = stage in {"expanded", "tightened", "unique_index", "exact"}
    specs = {
        "id": ("int", "NO", None, "auto_increment"),
        "event_type": ("varchar(50)", "YES" if final else "NO", None, ""),
        "description": ("text", "YES" if final else "NO", None, ""),
        "alert_code": ("varchar(50)", "NO" if final else "YES", None, ""),
        "source_domain": ("varchar(50)", "NO" if final else "YES", None, ""),
        "case_key": ("varchar(100)", "NO" if final else "YES", None, ""),
        "reason": ("varchar(500)", "NO" if final else "YES", None, ""),
        "details": ("json", "NO" if final else "YES", None, ""),
        "status": (
            (
                "enum('open','claimed','resolved')"
                if final
                else (
                    "enum('pending','open','claimed','resolved')"
                    if expanded
                    else "enum('pending','resolved')"
                )
            ),
            "NO" if final else "YES",
            "open" if final else "pending",
            "",
        ),
        "claimed_by": ("varchar(100)", "YES", None, ""),
        "claimed_at": ("datetime", "YES", None, ""),
        "resolved_by": (
            "varchar(100)" if final else "varchar(50)",
            "YES",
            None,
            "",
        ),
        "resolved_at": (
            "datetime" if final else "timestamp",
            "YES",
            None,
            "",
        ),
        "resolution_reason": ("varchar(500)", "YES", None, ""),
        "created_at": (
            "timestamp",
            "YES",
            "current_timestamp()",
            "default_generated",
        ),
        "updated_at": (
            "timestamp",
            "YES",
            "current_timestamp()",
            (
                "default_generated"
                if wrong_updated_extra
                else "default_generated on update current_timestamp()"
            ),
        ),
    }
    if wrong_column is not None:
        name, column_type = wrong_column
        _, nullable, default, extra = specs[name]
        specs[name] = (column_type, nullable, default, extra)
    columns = [
        {
            "table_name": "system_alerts",
            "column_name": name,
            "column_type": column_type,
            "is_nullable": nullable,
            "column_default": default,
            "extra": extra,
            "generation_expression": "",
        }
        for name, (column_type, nullable, default, extra) in specs.items()
    ]
    indexes = []
    if stage in {"unique_index", "exact"}:
        indexes.append(
            {
                "table_name": "system_alerts",
                "index_name": "uq_alert_case",
                "non_unique": 0,
                "columns": (
                    "case_key,alert_code"
                    if wrong_unique_index
                    else "alert_code,case_key"
                ),
            }
        )
    if stage == "exact":
        indexes.append(
            {
                "table_name": "system_alerts",
                "index_name": "idx_system_alert_status",
                "non_unique": 1,
                "columns": "status",
            }
        )
    return {
        "columns": columns,
        "indexes": indexes,
        "constraints": [],
        "key_columns": [],
        "foreign_keys": [],
        "triggers": [],
        "views": [],
        "sha256": f"system-alert-{stage}",
    }


@pytest.mark.parametrize(
    "stage",
    ["added_nullable", "expanded", "tightened", "unique_index"],
)
def test_107_only_canonical_statement_boundaries_are_partial(
    stage: str,
) -> None:
    snapshot = _system_alert_transition_snapshot(stage)
    assert migration._system_alert_projection_state(snapshot) == "partial"


def test_107_exact_projection_requires_both_exact_indexes() -> None:
    snapshot = _system_alert_transition_snapshot("exact")
    assert migration._system_alert_projection_state(snapshot) == "exact"


@pytest.mark.parametrize(
    "snapshot",
    [
        _system_alert_transition_snapshot(
            "added_nullable", wrong_column=("alert_code", "varchar(51)")
        ),
        _system_alert_transition_snapshot(
            "expanded", wrong_updated_extra=True
        ),
        _system_alert_transition_snapshot(
            "unique_index", wrong_unique_index=True
        ),
    ],
)
def test_107_transitional_metadata_drift_is_not_resumable(
    snapshot: dict[str, object],
) -> None:
    assert migration._system_alert_projection_state(snapshot) == "drift"


def test_107_arbitrary_new_column_subset_is_drift() -> None:
    snapshot = _system_alert_transition_snapshot("added_nullable")
    snapshot["columns"] = [
        row
        for row in snapshot["columns"]
        if row["column_name"] != "resolution_reason"
    ]
    assert migration._system_alert_projection_state(snapshot) == "drift"


def test_build_plan_blocks_source_with_107_transitional_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _system_alert_transition_snapshot("expanded")
    monkeypatch.setattr(
        migration,
        "server_identity",
        lambda config, database: {
            "database": database,
            "server": "test-server",
            "host": config.host,
            "port": config.port,
        },
    )
    monkeypatch.setattr(migration, "_schema_snapshot", lambda *args: snapshot)
    monkeypatch.setattr(
        migration,
        "_owned_classification",
        lambda value: {"107_system_alert_current_projection.sql": "partial"},
    )
    config = migration.DatabaseConfig("127.0.0.1", 3306, "user", "secret")
    with pytest.raises(
        UpgradeBlocked, match="source contains partial/drift owned objects"
    ):
        build_plan(config, "source_db", "candidate_db")


def test_descriptor_preserves_parameterized_types_and_mysql_default_extra() -> None:
    part = "61_finance_import_reprocessing.sql"
    descriptor = migration._canonical_artifact_descriptor(part)
    run = descriptor["tables"]["finance_import_reprocess_runs"]
    assert run["actor"]["column_type"] == "varchar(255)"
    assert run["plan_fingerprint"]["column_type"] == "char(64)"
    assert run["batch_status"]["column_type"] == (
        "enum('staged','completed','failed')"
    )
    assert run["created_at"]["column_type"] == "timestamp"
    assert run["created_at"]["extra"] == "default_generated"


def test_column_type_normalization_removes_only_structural_whitespace() -> None:
    assert migration._normalize_column_type_contract(
        "ENUM( 'cancellation',\n 'actual_start_reconfirmation' )"
    ) == migration._normalize_column_type_contract(
        "enum('cancellation','actual_start_reconfirmation')"
    )
    assert migration._normalize_column_type_contract(
        "enum('requires review','ready')"
    ) != migration._normalize_column_type_contract(
        "enum('requiresreview','ready')"
    )
    assert "'a b'" in migration._normalize_column_type_contract(
        "ENUM( 'a b', 'c' )"
    )


def test_sql_contract_normalization_preserves_grouping_precedence() -> None:
    assert migration._normalize_sql_contract(
        "((a AND b) OR c)"
    ) != migration._normalize_sql_contract(
        "a AND (b OR c)"
    )
    assert migration._normalize_sql_contract(
        "((a AND (b OR c)))"
    ) == migration._normalize_sql_contract(
        "a AND (b OR c)"
    )
    assert migration._normalize_sql_contract(
        "`status` = _utf8mb4'open'"
    ) == migration._normalize_sql_contract(
        "status='open'"
    )


@pytest.mark.parametrize(
    ("canonical", "mysql_actual"),
    [
        (
            "plan_fingerprint REGEXP '^[0-9a-f]{64}$'",
            "regexp_like(`plan_fingerprint`,"
            "_utf8mb4\\'^[0-9a-f]{64}$\\')",
        ),
        (
            "batch_status = 'completed'",
            "(`batch_status` = _utf8mb4\\'completed\\')",
        ),
        (
            "changed_count <= selected_count "
            "AND dispatch_count <= changed_count "
            "AND reconciled_count <= dispatch_count "
            "AND pending_count <= dispatch_count "
            "AND reconciled_count + pending_count <= dispatch_count",
            "((`changed_count` <= `selected_count`) and "
            "(`dispatch_count` <= `changed_count`) and "
            "(`reconciled_count` <= `dispatch_count`) and "
            "(`pending_count` <= `dispatch_count`) and "
            "((`reconciled_count` + `pending_count`) "
            "<= `dispatch_count`))",
        ),
    ],
)
def test_captured_mysql_check_clauses_match_canonical_contract(
    canonical: str, mysql_actual: str
) -> None:
    assert migration._normalize_sql_contract(
        canonical
    ) == migration._normalize_sql_contract(mysql_actual)


def test_captured_mysql_de_morgan_rewrite_matches_canonical_contract() -> None:
    canonical = (
        "NOT ("
        "before_classification_type <=> after_classification_type "
        "AND before_classification_reason <=> after_classification_reason "
        "AND before_matched_identity_ids <=> after_matched_identity_ids "
        "AND before_resolved_counterparty_account "
        "<=> after_resolved_counterparty_account"
        ")"
    )
    mysql_actual = (
        "((not((`before_classification_type` "
        "<=> `after_classification_type`))) or "
        "(not((`before_classification_reason` "
        "<=> `after_classification_reason`))) or "
        "(not((`before_matched_identity_ids` "
        "<=> `after_matched_identity_ids`))) or "
        "(not((`before_resolved_counterparty_account` "
        "<=> `after_resolved_counterparty_account`))))"
    )
    assert migration._normalize_sql_contract(
        canonical
    ) == migration._normalize_sql_contract(mysql_actual)


def test_de_morgan_normalization_preserves_non_equivalent_forms() -> None:
    assert migration._normalize_sql_contract(
        "NOT (a AND b)"
    ) != migration._normalize_sql_contract(
        "NOT a AND NOT b"
    )
    assert migration._normalize_sql_contract(
        "NOT (a OR b)"
    ) != migration._normalize_sql_contract(
        "NOT a OR NOT b"
    )


def test_show_create_check_parser_preserves_chinese_and_nested_literals() -> None:
    create_sql = """
    CREATE TABLE `order_lifecycle_state_events` (
      `before_status` varchar(20) NOT NULL,
      `facts_snapshot` json NOT NULL,
      CONSTRAINT `chk_before_status`
        CHECK (((`before_status` in
          (_utf8mb4'洽談中',_utf8mb4'訂單成立',_utf8mb4'服務中',
           _utf8mb4'訂單完成',_utf8mb4'訂單取消')))),
      CONSTRAINT `chk_json`
        CHECK ((json_type(`facts_snapshot`) = _utf8mb4'OBJECT'))
    ) ENGINE=InnoDB
    """
    clauses = migration._show_create_check_clauses(create_sql)
    assert "洽談中" in clauses[
        ("order_lifecycle_state_events", "chk_before_status")
    ]
    assert migration._normalize_sql_contract(
        clauses[("order_lifecycle_state_events", "chk_json")]
    ) == migration._normalize_sql_contract(
        "JSON_TYPE(facts_snapshot) = 'OBJECT'"
    )


def test_show_create_clause_overrides_information_schema_mojibake() -> None:
    part = "104_order_lifecycle_state_history.sql"
    descriptor = migration._canonical_artifact_descriptor(part)
    snapshot = _snapshot_from_descriptor(descriptor)
    status_key = (
        "order_lifecycle_state_events",
        "chk_order_lifecycle_state_event_before_status",
    )
    status_constraint = next(
        row for row in snapshot["constraints"]
        if (row["table_name"], row["constraint_name"]) == status_key
    )
    status_constraint["check_clause"] = (
        "before_status in ('æ´½è«\x87ä¸\xad')"
    )
    snapshot["show_create_tables"] = {
        "order_lifecycle_state_events": (
            "CREATE TABLE `order_lifecycle_state_events` ("
            "`before_status` varchar(20) NOT NULL,"
            "CONSTRAINT "
            "`chk_order_lifecycle_state_event_before_status` "
            "CHECK (before_status IN "
            "('洽談中','訂單成立','服務中','訂單完成','訂單取消'))"
            ")"
        )
    }
    assert migration._canonical_artifact_metadata_state(
        snapshot, part
    ) == "exact"
    snapshot["show_create_tables"] = {}
    assert migration._canonical_artifact_metadata_state(
        snapshot, part
    ) == "drift"


@pytest.mark.parametrize(
    ("collection", "field", "replacement"),
    [
        ("columns", "column_type", "varchar(255)"),
        ("indexes", "columns", "wrong_column"),
        ("key_columns", "referenced_column_name", "wrong_id"),
        ("constraints", "check_clause", "wrong_check_clause"),
        ("triggers", "action_timing", "AFTER"),
        ("triggers", "action_statement", "wrong trigger body"),
    ],
)
def test_current_metadata_descriptor_rejects_wrong_owned_shape(
    collection: str,
    field: str,
    replacement: str,
) -> None:
    part = "61_finance_import_reprocessing.sql"
    descriptor = migration._canonical_artifact_descriptor(part)
    snapshot = _snapshot_from_descriptor(descriptor)
    assert migration._canonical_artifact_metadata_state(
        snapshot, part
    ) == "exact"
    row = snapshot[collection][0]
    if collection == "constraints" and row["constraint_type"] != "CHECK":
        row = next(
            item for item in snapshot[collection]
            if item["constraint_type"] == "CHECK"
        )
    if collection == "indexes":
        row[field] = replacement
    else:
        row[field] = replacement
    assert migration._canonical_artifact_metadata_state(
        snapshot, part
    ) == "drift"


def test_plan_artifact_and_fingerprint_staleness_fail_closed() -> None:
    payload = {
        "status": "ready",
        "source": {
            "database": "source_db",
            "server": "server",
            "host": "127.0.0.1",
            "port": 3306,
        },
        "candidate_database": "candidate_db",
        "schema_artifacts": [{"name": "108.sql", "sha256": "a" * 64}],
        "phase_order": ["108.sql"],
    }
    plan = {
        **payload,
        "plan_fingerprint": migration._sha256_bytes(
            migration._canonical_json(payload)
        ),
    }
    migration._validate_plan_integrity(plan, dict(payload))
    changed = {
        **payload,
        "schema_artifacts": [{"name": "108.sql", "sha256": "b" * 64}],
    }
    with pytest.raises(UpgradeBlocked, match="schema_artifacts"):
        migration._validate_plan_integrity(plan, changed)
    corrupt = {**plan, "status": "blocked"}
    with pytest.raises(UpgradeBlocked, match="fingerprint"):
        migration._validate_plan_integrity(corrupt, dict(payload))


def test_write_receipt_retries_a_transient_windows_file_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt_path = tmp_path / "receipt.json"
    replace_attempts = 0
    real_replace = migration.os.replace

    def transiently_locked_replace(source: Path, target: Path) -> None:
        nonlocal replace_attempts
        replace_attempts += 1
        if replace_attempts == 1:
            raise PermissionError("temporary scanner lock")
        real_replace(source, target)

    monkeypatch.setattr(migration.os, "replace", transiently_locked_replace)
    monkeypatch.setattr(migration.time_module, "sleep", lambda _seconds: None)

    write_receipt(receipt_path, {"status": "ready"})

    assert read_receipt(receipt_path) == {"status": "ready"}
    assert replace_attempts == 2


def test_backup_receipt_mismatch_fails_before_restore(tmp_path: Path) -> None:
    dump = tmp_path / "source.sql"
    dump.write_bytes(
        b"-- MySQL dump\n-- Current Database: `source_db`\nSELECT 1;\n"
    )
    receipt = tmp_path / "backup.json"
    write_receipt(
        receipt,
        {
            "database": "source_db",
            "server": "wrong-server",
            "sha256": migration._sha256_file(dump),
        },
    )
    with pytest.raises(UpgradeBlocked, match="receipt mismatch: server"):
        validate_dump(
            dump,
            receipt,
            "source_db",
            {"server": "expected-server"},
        )


def test_restore_program_evidence_normalizes_only_database_qualifier() -> None:
    source_snapshot = {
        "triggers": [
            {
                "trigger_name": "trg_a",
                "event_manipulation": "INSERT",
                "event_object_table": "sample",
                "action_timing": "BEFORE",
                "action_statement": "SET NEW.x = `source_db`.helper(NEW.x)",
            }
        ],
        "views": [
            {
                "table_name": "v_sample",
                "view_definition": "select `source_db`.`sample`.`id` AS `id`",
            }
        ],
    }
    candidate_snapshot = {
        "triggers": [
            {
                **source_snapshot["triggers"][0],
                "action_statement": (
                    "SET NEW.x = `candidate_db`.helper(NEW.x)"
                ),
            }
        ],
        "views": [
            {
                "table_name": "v_sample",
                "view_definition": (
                    "select `candidate_db`.`sample`.`id` AS `id`"
                ),
            }
        ],
    }
    assert migration._restored_schema_program_evidence(
        source_snapshot, "source_db"
    ) == migration._restored_schema_program_evidence(
        candidate_snapshot, "candidate_db"
    )
    candidate_snapshot["triggers"][0]["action_timing"] = "AFTER"
    assert migration._restored_schema_program_evidence(
        source_snapshot, "source_db"
    ) != migration._restored_schema_program_evidence(
        candidate_snapshot, "candidate_db"
    )


def test_restore_data_mismatch_is_retained_and_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dump = tmp_path / "source.sql"
    dump.write_bytes(b"restored fixture")
    operation = tmp_path / "operation.json"
    cursor = _FakeApplyCursor("candidate_db")
    config = _FakeApplyConfig(cursor)
    monkeypatch.setattr(migration, "database_exists", lambda *args: False)
    monkeypatch.setattr(
        migration,
        "server_identity",
        lambda config, database: {
            "database": database,
            "server": "test-server",
        },
    )
    monkeypatch.setattr(
        migration,
        "validate_dump",
        lambda *args: {
            "path": str(dump),
            "database": "source_db",
            "server": "test-server",
            "sha256": "a" * 64,
        },
    )
    monkeypatch.setattr(migration, "_mysql_base", lambda *args, **kwargs: [])
    monkeypatch.setattr(migration, "_client_environment", lambda config: {})
    monkeypatch.setattr(
        migration.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    evidence = iter(
        [
            {"orders": {"count": 1, "checksum": 1}},
            {"orders": {"count": 2, "checksum": 2}},
        ]
    )
    monkeypatch.setattr(
        migration, "_table_evidence", lambda *args: next(evidence)
    )
    with pytest.raises(UpgradeBlocked, match="differs from source"):
        restore_candidate(
            config,
            "source_db",
            "candidate_db",
            dump,
            tmp_path / "backup.json",
            operation,
        )
    receipt = read_receipt(operation)
    assert receipt["status"] == "partial"
    assert receipt["failed_phase"] == "restore_validation"


def test_orders_legacy_projection_mismatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = iter(
        [
            {
                "columns": ["id", "case_no", "status"],
                "row_count": 1,
                "rows_sha256": "a" * 64,
            },
            {
                "columns": ["id", "case_no", "status"],
                "row_count": 1,
                "rows_sha256": "b" * 64,
            },
        ]
    )
    monkeypatch.setattr(
        migration,
        "_table_projection_evidence",
        lambda *args: next(evidence),
    )
    source_snapshot = {
        "columns": [
            {"table_name": "orders", "column_name": "id"},
            {"table_name": "orders", "column_name": "case_no"},
            {"table_name": "orders", "column_name": "status"},
        ]
    }
    with pytest.raises(UpgradeBlocked, match="orders legacy data changed"):
        migration._verify_orders_preservation(
            object(), "source_db", "candidate_db", source_snapshot
        )


def test_switch_identity_config_staleness_and_quoted_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = tmp_path / "quoted.env"
    environment.write_text(
        'DB_HOST=127.0.0.1\nDB_PORT=3306\n'
        'DB_DATABASE = "source_db"  \nSECRET=preserved\n',
        encoding="utf-8",
    )
    original = environment.read_bytes()
    verified_path = tmp_path / "verified.json"
    switch_path = tmp_path / "switch.json"
    write_receipt(
        verified_path,
        {
            "status": "verified",
            "source": {
                "database": "source_db",
                "server": "server",
                "host": "127.0.0.1",
                "port": 3306,
            },
            "candidate_database": "candidate_db",
            "candidate": {
                "database": "candidate_db",
                "server": "server",
            },
            "source_data": {"orders": {"count": 1}},
            "candidate_data": {"orders": {"count": 1}},
        },
    )
    monkeypatch.setattr(
        migration,
        "config_from_env",
        lambda path: (object(), "source_db"),
    )
    monkeypatch.setattr(
        migration,
        "server_identity",
        lambda config, database: {
            "database": database,
            "server": "server",
        },
    )
    monkeypatch.setattr(
        migration,
        "_table_evidence",
        lambda config, database: {"orders": {"count": 1}},
    )
    switch_environment(
        environment,
        "source_db",
        "candidate_db",
        verified_path,
        switch_path,
    )
    assert b'DB_DATABASE = "candidate_db"  ' in environment.read_bytes()
    rollback_environment(environment, switch_path)
    assert environment.read_bytes() == original

    stale_environment = tmp_path / "stale.env"
    stale_environment.write_text(
        "DB_HOST=192.0.2.1\nDB_PORT=3306\nDB_DATABASE=source_db\n",
        encoding="utf-8",
    )
    with pytest.raises(UpgradeBlocked, match="connection identity is stale"):
        switch_environment(
            stale_environment,
            "source_db",
            "candidate_db",
            verified_path,
            tmp_path / "stale-switch.json",
        )

    wrong_verified = read_receipt(verified_path)
    wrong_verified["candidate_database"] = "other_candidate"
    write_receipt(verified_path, wrong_verified)
    with pytest.raises(UpgradeBlocked, match="database identity mismatch"):
        switch_environment(
            environment,
            "source_db",
            "candidate_db",
            verified_path,
            tmp_path / "wrong-switch.json",
        )


def _drop_created_test_databases(config, names: list[str]) -> None:
    connection = config.connect()
    try:
        with connection.cursor() as cursor:
            for name in names:
                assert name.startswith("adad_cutover_")
                validate_database_names("guard_source", name)
                cursor.execute(f"DROP DATABASE `{name}`")
    finally:
        connection.close()


@pytest.mark.integration
def test_real_mysql_preserved_source_candidate_cutover(tmp_path: Path) -> None:
    container = os.getenv("MYSQL_TEST_CONTAINER", "").strip()
    if not container:
        pytest.fail(
            "MYSQL_TEST_CONTAINER is required for the real MySQL cutover gate"
        )
    live_environment = ROOT / ".env"
    config, configured_source = config_from_env(live_environment)
    live_source = (
        os.getenv("PRESERVED_DB_TEST_SOURCE", "").strip()
        or configured_source
    )
    if not live_source:
        pytest.fail(
            "PRESERVED_DB_TEST_SOURCE is required when .env has no DB_DATABASE"
        )
    assert live_source not in {"", "adad_cutover_source", "adad_cutover_candidate"}

    nonce = uuid.uuid4().hex[:12]
    disposable_source = f"adad_cutover_source_{nonce}"
    candidate = f"adad_cutover_candidate_{nonce}"
    created: list[str] = []
    completed = False

    live_dump = tmp_path / "live.sql"
    live_backup_receipt = tmp_path / "live.backup.json"
    source_restore_receipt = tmp_path / "source.restore.json"
    source_dump = tmp_path / "source.sql"
    source_backup_receipt = tmp_path / "source.backup.json"
    candidate_restore_receipt = tmp_path / "candidate.restore.json"
    plan_path = tmp_path / "candidate.plan.json"
    switch_receipt = tmp_path / "switch.json"
    temporary_environment = tmp_path / "cutover.env"

    try:
        assert not database_exists(config, disposable_source)
        assert not database_exists(config, candidate)
        create_source_dump(
            config,
            live_source,
            live_dump,
            live_backup_receipt,
            mysql_container=container,
        )
        restore_candidate(
            config,
            live_source,
            disposable_source,
            live_dump,
            live_backup_receipt,
            source_restore_receipt,
            mysql_container=container,
        )
        created.append(disposable_source)

        credential_marker = "cutover-secret-marker-must-not-leak"
        lines = [
            f"DB_HOST={config.host}",
            f"DB_PORT={config.port}",
            f"DB_USER={config.user}",
            f"DB_PASSWORD={config.password}",
            f"DB_DATABASE={disposable_source}",
            f"INTERNAL_API_KEY={credential_marker}",
            "CUTOVER_TEST_SETTING=preserved",
        ]
        temporary_environment.write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
        )
        disposable_config, configured_source = config_from_env(
            temporary_environment
        )
        assert configured_source == disposable_source

        connection = disposable_config.connect(disposable_source)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) AS n FROM information_schema.columns "
                    "WHERE table_schema=%s AND table_name='matching_records' "
                    "AND column_name='sent_resume_at'",
                    (disposable_source,),
                )
                if int(cursor.fetchone()["n"]) == 1:
                    cursor.execute(
                        "ALTER TABLE matching_records "
                        "DROP COLUMN sent_resume_at"
                    )
                cursor.execute("DROP TABLE system_alerts")
                cursor.execute(
                    """CREATE TABLE system_alerts (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        event_type VARCHAR(50) NOT NULL,
                        description TEXT NOT NULL,
                        status ENUM('pending','resolved') DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        resolved_at TIMESTAMP NULL,
                        resolved_by VARCHAR(50) NULL,
                        INDEX idx_alert_status (status)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
                )
                cursor.execute(
                    """INSERT INTO system_alerts
                       (event_type,description,status,resolved_by,resolved_at)
                       VALUES
                       ('IMPORT-LEGACY','legacy pending alert','pending',NULL,NULL),
                       ('ORDER-LEGACY','legacy resolved alert','resolved',
                        'legacy-operator','2026-01-02 03:04:05')"""
                )
        finally:
            connection.close()

        create_source_dump(
            disposable_config,
            disposable_source,
            source_dump,
            source_backup_receipt,
            mysql_container=container,
        )
        plan = build_plan(disposable_config, disposable_source, candidate)
        assert plan["status"] == "ready"
        write_receipt(plan_path, plan)
        restore_candidate(
            disposable_config,
            disposable_source,
            candidate,
            source_dump,
            source_backup_receipt,
            candidate_restore_receipt,
            mysql_container=container,
        )
        created.append(candidate)
        apply_schema(
            disposable_config,
            disposable_source,
            candidate,
            plan_path,
            candidate_restore_receipt,
            mysql_container=container,
        )
        verified = verify_candidate(
            disposable_config,
            disposable_source,
            candidate,
            candidate_restore_receipt,
        )
        assert verified["status"] == "verified"
        assert verified["system_alert_preservation"] == {
            "mode": "legacy_migrated",
            "row_count": 2,
            "status_mapping": "pending_to_open_resolved_unchanged",
        }
        assert (
            verified["matching_records_preservation"][
                "source_resume_state"
            ]
            == "absent"
        )
        assert (
            verified["matching_records_preservation"][
                "sent_resume_non_null_count"
            ]
            == 0
        )
        connection = disposable_config.connect(candidate)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT column_type,is_nullable,column_default,extra,"
                    "generation_expression "
                    "FROM information_schema.columns "
                    "WHERE table_schema=%s AND table_name='matching_records' "
                    "AND column_name='sent_resume_at'",
                    (candidate,),
                )
                sent_resume = {
                    str(key).casefold(): value
                    for key, value in cursor.fetchone().items()
                }
                assert sent_resume == {
                    "column_type": "datetime",
                    "is_nullable": "YES",
                    "column_default": None,
                    "extra": "",
                    "generation_expression": "",
                }
                cursor.execute(
                    """SELECT id,event_type,description,alert_code,source_domain,
                              case_key,reason,status
                       FROM system_alerts ORDER BY id"""
                )
                migrated = cursor.fetchall()
                assert migrated[0]["event_type"] == "IMPORT-LEGACY"
                assert migrated[0]["description"] == "legacy pending alert"
                assert migrated[0]["alert_code"] == "IMPORT-LEGACY"
                assert migrated[0]["source_domain"] == "LEGACY"
                assert migrated[0]["case_key"] == (
                    f"legacy-alert:{migrated[0]['id']}"
                )
                assert migrated[0]["reason"] == "legacy pending alert"
                assert migrated[0]["status"] == "open"
                assert migrated[1]["status"] == "resolved"
                connection.begin()
                cursor.execute(
                    """INSERT INTO system_alerts
                       (alert_code,source_domain,case_key,reason,details,status)
                       VALUES
                       ('IMPORT-006','FINANCE_IMPORT','batch:integration',
                        'review required',JSON_OBJECT('batch_id',1),'open')"""
                )
                cursor.execute(
                    """SELECT event_type,description,status
                       FROM system_alerts
                       WHERE alert_code='IMPORT-006'
                         AND case_key='batch:integration'"""
                )
                inserted = cursor.fetchone()
                assert inserted == {
                    "event_type": None,
                    "description": None,
                    "status": "open",
                }
                connection.rollback()
                cursor.execute("SELECT COUNT(*) AS n FROM system_alerts")
                alerts_before_scan = int(cursor.fetchone()["n"])
                cursor.execute(
                    "SELECT COUNT(*) AS n FROM finance_import_rows"
                )
                finance_rows_before_scan = int(cursor.fetchone()["n"])
                connection.begin()
                summary = run_process_alert_scan(cursor)
                assert set(summary) == EXPECTED_SCANNER_CODES
                assert "IMPORT-006" in summary
                connection.rollback()
        finally:
            connection.close()
        connection = disposable_config.connect(candidate)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS n FROM system_alerts")
                assert int(cursor.fetchone()["n"]) == alerts_before_scan
                cursor.execute(
                    "SELECT COUNT(*) AS n FROM finance_import_rows"
                )
                assert int(cursor.fetchone()["n"]) == finance_rows_before_scan
        finally:
            connection.close()
        before_bytes = temporary_environment.read_bytes()
        switched = switch_environment(
            temporary_environment,
            disposable_source,
            candidate,
            candidate_restore_receipt,
            switch_receipt,
        )
        assert switched["status"] == "switched"
        serialized_switch = json.dumps(
            switched, ensure_ascii=False, sort_keys=True
        )
        assert "before_bytes_hex" not in switched
        assert credential_marker not in serialized_switch
        assert credential_marker.encode("utf-8").hex() not in serialized_switch
        assert before_bytes.hex() not in serialized_switch
        rolled_back = rollback_environment(
            temporary_environment, switch_receipt
        )
        assert rolled_back["status"] == "rolled_back"
        serialized_rollback = json.dumps(
            rolled_back, ensure_ascii=False, sort_keys=True
        )
        assert "before_bytes_hex" not in rolled_back
        assert credential_marker not in serialized_rollback
        assert (
            credential_marker.encode("utf-8").hex()
            not in serialized_rollback
        )
        assert temporary_environment.read_bytes() == before_bytes
        assert read_receipt(candidate_restore_receipt)["status"] == "verified"
        completed = True
    finally:
        if completed:
            _drop_created_test_databases(config, list(reversed(created)))
        elif created:
            print("preserved disposable databases for diagnosis:", created)
