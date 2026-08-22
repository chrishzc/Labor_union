"""
File: update_local_database.py
Description: 依 .env 指定的本機資料庫建立候選升級、驗證並安全同名替換。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts import migrate_preserved_database_additive_schema as migration
except Exception as migration_import_error:  # Catalog corruption must remain an operator-facing error.
    migration = None
    MIGRATION_IMPORT_ERROR = migration_import_error
else:
    MIGRATION_IMPORT_ERROR = None

try:
    from scripts import local_database_additive_update as additive
except Exception as additive_import_error:  # Fast-path wiring must fail closed if unavailable.
    additive = None
    ADDITIVE_IMPORT_ERROR = additive_import_error
else:
    ADDITIVE_IMPORT_ERROR = None


DEFAULT_ENVIRONMENT_FILE = ROOT / ".env"
DEFAULT_RECEIPT_ROOT = ROOT / "scratch/local_database_updates"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
MYSQL_IDENTIFIER_MAX_LENGTH = 64
DEFAULT_DOCKER_MYSQL_CONTAINER = "mysql_db"
LOCAL_RESUMABLE_PARTIAL_ARTIFACTS = frozenset({
    "148_knowledge_retrieval.sql",
    "163_knowledge_runtime.sql",
    "181_matching_service_date_confirmation.sql",
    "185_customer_service_runtime.sql",
    "186_line_identity_management.sql",
})
NOTIFICATION_CATALOG_PARTS = frozenset({
    "203_line_notification_rule_catalog.sql",
    "204_scheduling_service_day_logs.sql",
    "205_scheduling_service_day_checkpoints.sql",
    "206_line_notification_recurring_intents.sql",
    "207_scheduling_service_day_log_outbox_retry.sql",
    "208_scheduling_rebuild_notification_invalidation.sql",
})


class LocalDatabaseUpdateError(RuntimeError):
    """Bounded operator-facing updater failure."""

    def __init__(self, message: str, *, code: str = "database_update_blocked"):
        super().__init__(message)
        self.code = code


def resolve_mysql_container(configured_container=None) -> str | None:
    if configured_container:
        return str(configured_container)
    if shutil.which("mysql") and shutil.which("mysqldump"):
        return None
    return (
        DEFAULT_DOCKER_MYSQL_CONTAINER
        if _default_docker_mysql_is_running()
        else None
    )


def _default_docker_mysql_is_running() -> bool:
    try:
        inspection = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Running}}",
                DEFAULT_DOCKER_MYSQL_CONTAINER,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
    except OSError:
        return False
    return inspection.returncode == 0 and inspection.stdout.strip() == "true"


def require_mysql_clients(mysql_container: str | None) -> None:
    if mysql_container:
        return
    missing = [name for name in ("mysql", "mysqldump") if not shutil.which(name)]
    if missing:
        names = ", ".join(missing)
        raise LocalDatabaseUpdateError(
            f"required MySQL client is unavailable: {names}; "
            "start Docker container mysql_db or set MYSQL_CONTAINER"
        )


def require_mysql_apply_client(mysql_container: str | None) -> None:
    """The qualified in-place path executes mysql only; it never dumps data."""
    if mysql_container or shutil.which("mysql"):
        return
    raise LocalDatabaseUpdateError(
        "required MySQL apply client is unavailable: mysql; "
        "start Docker container mysql_db or set MYSQL_CONTAINER"
    )


def validate_local_source(config, source: str, environment=None) -> None:
    values = environment if environment is not None else os.environ
    if config.host.casefold() not in LOCAL_HOSTS:
        raise LocalDatabaseUpdateError("developer update only accepts local MySQL")
    if not isinstance(source, str) or not migration.IDENTIFIER.fullmatch(source):
        raise LocalDatabaseUpdateError("source database name is invalid")
    if any("prod" in str(values.get(key, "")).casefold() for key in ("APP_ENV", "ENV", "FLASK_ENV")):
        raise LocalDatabaseUpdateError("production environment refused")
    profile = str(
        values.get("APP_ENV", values.get("ENV", values.get("FLASK_ENV", "local")))
    ).casefold()
    if source.casefold() == "union_db" or not source.casefold().startswith("lu_test_"):
        raise LocalDatabaseUpdateError(
            "daily additive update requires a lu_test_* local development database"
        )
    if profile not in {"local", "development", "dev", "test", "testing"}:
        raise LocalDatabaseUpdateError("local development profile required")


def with_database_port(config, database_port: int | None):
    """Return the same credential set with an explicit local TCP forwarding port."""
    if database_port is None:
        return config
    if not 1 <= database_port <= 65535:
        raise LocalDatabaseUpdateError("database port must be between 1 and 65535")
    return migration.DatabaseConfig(
        host=config.host,
        port=database_port,
        user=config.user,
        password=config.password,
    )


def candidate_name(source: str, now=None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d%H%M%S")
    suffix = f"_local_{timestamp}"
    return f"{source[:MYSQL_IDENTIFIER_MAX_LENGTH - len(suffix)]}{suffix}"


def validate_candidate_database(source: str, candidate: str) -> None:
    if not migration.IDENTIFIER.fullmatch(candidate):
        raise LocalDatabaseUpdateError("candidate database name is invalid")
    if len(candidate) > MYSQL_IDENTIFIER_MAX_LENGTH:
        raise LocalDatabaseUpdateError("candidate database name exceeds MySQL identifier limit")
    if candidate == source:
        raise LocalDatabaseUpdateError("candidate database must differ from source")


def build_preview(config, source: str, candidate: str) -> dict[str, object]:
    plan = migration.build_plan(
        config,
        source,
        candidate,
        LOCAL_RESUMABLE_PARTIAL_ARTIFACTS,
    )
    states = plan["source_objects"]
    completed_retirements = migration.PURE_RETIREMENT_ARTIFACTS
    return {
        "status": "preview",
        "source_database": source,
        "candidate_database": candidate,
        "release_id": plan["release_id"],
        "parts_to_apply": [
            name for name, state in states.items()
            if state == "absent" and name not in completed_retirements
        ],
        "parts_to_resume": [name for name, state in states.items() if state == "partial"],
        "exact_parts": [
            name for name, state in states.items()
            if state == "exact" or (
                state == "absent" and name in completed_retirements
            )
        ],
        "source_policy": "no_ddl_before_verified_same_name_replacement",
        "plan": plan,
    }


def _fast_backup_receipt_path(receipt_root: Path, source: str) -> Path:
    return (
        Path(receipt_root).expanduser().resolve()
        / "fast_additive"
        / f"{source}.backup.receipt.json"
    )


def _additive_error_payload(error: Exception) -> dict[str, object]:
    code = getattr(error, "code", "additive_preflight_failed")
    details = getattr(error, "details", {})
    message = str(error)
    if any(word in message.casefold() for word in ("password", "passwd", "secret", "token", "credential", "api_key")):
        message = "additive operation failed; sensitive detail redacted"
    message = message[:240]
    return {
        "status": "blocked",
        "route": (
            "recovery"
            if code == "recovery_required"
            else "rare_replacement"
            if code == "replacement_required"
            else "daily_additive"
        ),
        "selected_strategy": "additive",
        "blocked_reason": message,
        "code": code,
        "details": dict(details) if isinstance(details, dict) else {},
        "target_profile": "local-development",
        "local_qualified_additive_exception": True,
        "estimated_work": {"artifact_count": 0, "statement_count": 0},
        "duration_guard_ms": 30_000,
    }


def build_additive_preview(
    config,
    source: str,
    receipt_root: Path,
    *,
    backup_receipt_path: Path | None = None,
    qualification_receipt_path: Path | None = None,
    duration_guard_ms: int = 30_000,
) -> dict[str, object]:
    """Build a bounded local-only plan without candidate creation or mysqldump."""
    if additive is None:
        raise LocalDatabaseUpdateError(
            f"additive runner unavailable: {ADDITIVE_IMPORT_ERROR}"
        )
    try:
        plan = additive.plan(
            config,
            source,
            receipt_root=receipt_root,
            qualification_path=qualification_receipt_path,
        )
    except additive.LocalAdditiveBlocked as error:
        return _additive_error_payload(error)
    return plan


def apply_additive_update(
    config,
    source: str,
    receipt_root: Path,
    *,
    backup_receipt_path: Path | None = None,
    qualification_receipt_path: Path | None = None,
    duration_guard_ms: int = 30_000,
    lock_timeout_seconds: int = 5,
    mysql_container: str | None = None,
) -> dict[str, object]:
    """Apply only the already-qualified source plan; no candidate or dump operations."""
    if additive is None:
        raise LocalDatabaseUpdateError(
            f"additive runner unavailable: {ADDITIVE_IMPORT_ERROR}"
        )
    preview = build_additive_preview(
        config,
        source,
        receipt_root,
        qualification_receipt_path=qualification_receipt_path,
    )
    if preview.get("status") not in {"ready", "current"}:
        raise LocalDatabaseUpdateError(
            f"{preview.get('blocked_reason', 'additive route blocked')} "
            f"[{preview.get('code', 'additive_blocked')}]"
        )
    if preview.get("status") == "current":
        return preview
    try:
        return additive.apply(
            config,
            source,
            receipt_root=Path(receipt_root),
            duration_guard_ms=duration_guard_ms,
            lock_timeout_seconds=lock_timeout_seconds,
            qualification_path=qualification_receipt_path,
        )
    except additive.LocalAdditiveBlocked as error:
        raise LocalDatabaseUpdateError(
            f"{error} [{error.code}]"
        ) from error


def build_drift_report(config, source: str) -> dict[str, object]:
    """唯讀列出阻擋升級的 owned-object 狀態與可否安全續跑。"""
    snapshot = migration._schema_snapshot(config, source)
    states = migration._owned_classification(snapshot, defer_missing_triggers=True)
    blocked = migration._blocking_schema_states(
        states, LOCAL_RESUMABLE_PARTIAL_ARTIFACTS
    )
    remediations = [
        _drift_remediation(snapshot, artifact, state)
        for artifact, state in sorted(blocked.items())
    ]
    return {
        "contract": "local-database-schema-drift-report/v1",
        "status": "blocked" if remediations else "ready",
        "source_database": source,
        "source_schema_sha256": snapshot["sha256"],
        "source_objects": states,
        "remediations": remediations,
        "source_policy": "read_only_no_source_ddl",
        "next_step": (
            "review each candidate-only remediation before --apply"
            if remediations else "run the normal preserved-data update preview"
        ),
    }


def _drift_remediation(snapshot, artifact: str, state: str) -> dict[str, object]:
    """把分類結果轉成可稽核的處置，不把未知 schema 猜成可修復。"""
    descriptor = migration._canonical_artifact_descriptor(artifact)
    expected_tables = {
        **descriptor["tables"], **descriptor["parent_columns"],
    }
    actual_columns: dict[str, set[str]] = {}
    for row in snapshot["columns"]:
        actual_columns.setdefault(str(row["table_name"]), set()).add(
            str(row["column_name"])
        )
    table_deltas = []
    for table, columns in sorted(expected_tables.items()):
        actual = actual_columns.get(table, set())
        expected = set(columns)
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected) if table in descriptor["tables"] else []
        if missing or unexpected:
            table_deltas.append({
                "table": table,
                "missing_columns": missing,
                "unexpected_columns": unexpected,
            })
    resumable = state == "partial" and artifact in LOCAL_RESUMABLE_PARTIAL_ARTIFACTS
    return {
        "artifact": artifact,
        "state": state,
        "table_deltas": table_deltas,
        "disposition": (
            "candidate_resume_reviewed_partial"
            if resumable else "candidate_repair_requires_artifact_decision"
        ),
        "source_ddl": "forbidden",
        "automatic_apply": resumable,
        "required_evidence": (
            "candidate backup, data preservation projection, exact descriptor verification"
        ),
    }


def require_current_database(preview: dict[str, object]) -> dict[str, object]:
    pending = [*preview["parts_to_apply"], *preview["parts_to_resume"]]
    if pending:
        names = ", ".join(str(name) for name in pending)
        raise LocalDatabaseUpdateError(f"schema update required: {names}")
    return {
        "status": "current",
        "source_database": preview.get("source_database"),
        "release_id": preview.get("release_id"),
    }


def artifact_paths(receipt_root: Path, candidate: str) -> dict[str, Path]:
    directory = receipt_root.expanduser().resolve() / candidate
    return {
        "directory": directory,
        "plan": directory / "plan.json",
        "dump": directory / "source.sql",
        "backup": directory / "backup.receipt.json",
        "operation": directory / "operation.receipt.json",
        "candidate_dump": directory / "candidate.sql",
        "candidate_backup": directory / "candidate-backup.receipt.json",
        "replacement": directory / "replacement.receipt.json",
    }


def restore_dump(
    config, database: str, dump_path: Path, *, mysql_container=None
) -> None:
    command = migration._mysql_base(
        config, "mysql", container=mysql_container
    ) + [database]
    with dump_path.open("rb") as source:
        completed = subprocess.run(
            command,
            stdin=source,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=migration._client_environment(config),
            check=False,
        )
    if completed.returncode != 0:
        raise LocalDatabaseUpdateError(f"mysql restore failed for {database}")


def recreate_database(config, database: str) -> None:
    if not migration.IDENTIFIER.fullmatch(database):
        raise LocalDatabaseUpdateError("destructive rebuild target is invalid")
    connection = config.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
            cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4")
    finally:
        connection.close()


def verify_replacement(config, source: str, candidate: str) -> dict[str, object]:
    source_data = migration._table_evidence(config, source)
    candidate_data = migration._table_evidence(config, candidate)
    if source_data != candidate_data:
        raise LocalDatabaseUpdateError("rebuilt union_db data differs from verified candidate")
    source_schema = migration._schema_snapshot(config, source)
    candidate_schema = migration._schema_snapshot(config, candidate)
    _verify_schema_equivalence(source_schema, candidate_schema, source, candidate)
    states = migration._owned_classification(source_schema)
    if not migration._candidate_schema_is_exact(states):
        raise LocalDatabaseUpdateError(f"rebuilt union_db schema is not exact: {states}")
    return {"table_evidence": source_data, "owned_objects": states}


def _verify_schema_equivalence(source_schema, candidate_schema, source: str, candidate: str) -> None:
    structural_keys = (
        "columns",
        "indexes",
        "constraints",
        "key_columns",
        "foreign_keys",
    )
    for key in structural_keys:
        if source_schema[key] != candidate_schema[key]:
            raise LocalDatabaseUpdateError(f"rebuilt union_db schema differs: {key}")
    if not _show_create_tables_match(source_schema, candidate_schema):
        raise LocalDatabaseUpdateError("rebuilt union_db schema differs: show_create_tables")
    source_programs = migration._restored_schema_program_evidence(
        source_schema, source, (candidate,)
    )
    candidate_programs = migration._restored_schema_program_evidence(
        candidate_schema, candidate, (source,)
    )
    if source_programs != candidate_programs:
        raise LocalDatabaseUpdateError("rebuilt union_db triggers or views differ")


def _show_create_tables_match(source_schema, candidate_schema) -> bool:
    return _stable_show_create_tables(source_schema) == _stable_show_create_tables(candidate_schema)


def _stable_show_create_tables(schema) -> dict[str, str]:
    tables = schema["show_create_tables"]
    return {
        table_name: _stable_show_create_table(create_sql)
        for table_name, create_sql in tables.items()
    }


def _stable_show_create_table(create_sql: str) -> str:
    without_dynamic_counter = re.sub(r" AUTO_INCREMENT=\d+", "", create_sql)
    return without_dynamic_counter.replace(
        " CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci",
        " COLLATE utf8mb4_unicode_ci",
    )


def rollback_source(
    config,
    source: str,
    dump_path: Path,
    expected_data,
    expected_schema_sha256: str,
    *,
    mysql_container=None,
) -> None:
    recreate_database(config, source)
    restore_dump(
        config, source, dump_path, **_container_argument(mysql_container)
    )
    if migration._table_evidence(config, source) != expected_data:
        raise LocalDatabaseUpdateError("automatic rollback data verification failed")
    actual_schema = migration._schema_snapshot(config, source)["sha256"]
    if actual_schema != expected_schema_sha256:
        raise LocalDatabaseUpdateError("automatic rollback schema verification failed")


# Kept together so the destructive replacement and its mandatory rollback remain one visible boundary.
def replace_source_database(
    config,
    source: str,
    candidate: str,
    paths: dict[str, Path],
    *,
    mysql_container=None,
) -> dict[str, object]:
    verified = migration.read_receipt(paths["operation"])
    plan = migration.read_receipt(paths["plan"])
    expected_source_data = verified.get("source_data")
    if migration._table_evidence(config, source) != expected_source_data:
        raise LocalDatabaseUpdateError("source changed during migration; stop services and retry")
    expected_schema_sha256 = str(plan.get("source_schema_sha256") or "")
    if migration._schema_snapshot(config, source)["sha256"] != expected_schema_sha256:
        raise LocalDatabaseUpdateError("source schema changed during migration; retry from a fresh backup")
    receipt = {
        "status": "prepared",
        "source_database": source,
        "candidate_database": candidate,
        "rollback_dump": str(paths["dump"]),
        "candidate_dump": str(paths["candidate_dump"]),
    }
    migration.write_receipt(paths["replacement"], receipt)
    try:
        recreate_database(config, source)
        restore_dump(
            config,
            source,
            paths["candidate_dump"],
            **_container_argument(mysql_container),
        )
        verification = verify_replacement(config, source, candidate)
    except Exception:
        rollback_source(
            config,
            source,
            paths["dump"],
            expected_source_data,
            expected_schema_sha256,
            **_container_argument(mysql_container),
        )
        receipt.update(status="rolled_back")
        migration.write_receipt(paths["replacement"], receipt)
        raise
    receipt.update(status="completed", verification=verification)
    migration.write_receipt(paths["replacement"], receipt)
    return receipt


# Kept together because this is the operator-facing phase order and contains no lower-level SQL details.
def apply_update(
    config,
    environment_file: Path,
    preview: dict[str, object],
    receipt_root: Path,
    *,
    mysql_container=None,
) -> dict[str, object]:
    source = str(preview["source_database"])
    candidate = str(preview["candidate_database"])
    paths = artifact_paths(receipt_root, candidate)
    if paths["directory"].exists():
        return resume_update(
            config, environment_file, preview, paths,
            mysql_container=mysql_container,
        )
    paths["directory"].mkdir(parents=True, exist_ok=False)
    migration.write_receipt(paths["plan"], preview["plan"])
    migration.create_source_dump(
        config,
        source,
        paths["dump"],
        paths["backup"],
        **_container_argument(mysql_container),
    )
    migration.restore_candidate(
        config,
        source,
        candidate,
        paths["dump"],
        paths["backup"],
        paths["operation"],
        **_container_argument(mysql_container),
    )
    migration.apply_schema(
        config,
        source,
        candidate,
        paths["plan"],
        paths["operation"],
        **_container_argument(mysql_container),
        allowed_partial_artifacts=LOCAL_RESUMABLE_PARTIAL_ARTIFACTS,
    )
    migration.verify_candidate(config, source, candidate, paths["operation"])
    replacement = resume_or_replace_source(
        config, source, candidate, paths, mysql_container=mysql_container
    )
    return {
        "status": "completed",
        "source_database": source,
        "candidate_database": candidate,
        "source_backup": str(paths["dump"]),
        "receipt_directory": str(paths["directory"]),
        "replacement": replacement,
        "environment_file_unchanged": str(environment_file),
        "restart_required": True,
    }


# Kept together because a completed candidate dump may have reached source replacement before interruption.
def resume_or_replace_source(
    config,
    source: str,
    candidate: str,
    paths: dict[str, Path],
    *,
    mysql_container=None,
) -> dict[str, object]:
    if paths["replacement"].is_file():
        receipt = migration.read_receipt(paths["replacement"])
        if receipt.get("source_database") != source or receipt.get("candidate_database") != candidate:
            raise LocalDatabaseUpdateError("existing replacement receipt targets another database")
        if receipt.get("status") == "completed":
            return receipt
        if receipt.get("status") == "prepared":
            verification = verify_replacement(config, source, candidate)
            receipt.update(status="completed", verification=verification, resumed=True)
            migration.write_receipt(paths["replacement"], receipt)
            return receipt
        raise LocalDatabaseUpdateError("existing replacement receipt is not resumable")
    if not paths["candidate_dump"].is_file():
        migration.create_source_dump(
            config,
            candidate,
            paths["candidate_dump"],
            paths["candidate_backup"],
            **_container_argument(mysql_container),
        )
    return replace_source_database(
        config,
        source,
        candidate,
        paths,
        **_container_argument(mysql_container),
    )


# Kept together because an interrupted candidate is safe to continue only from its recorded schema phase.
def resume_update(
    config,
    environment_file: Path,
    preview: dict[str, object],
    paths: dict[str, Path],
    *,
    mysql_container=None,
) -> dict[str, object]:
    source = str(preview["source_database"])
    candidate = str(preview["candidate_database"])
    required = (paths["plan"], paths["operation"], paths["dump"], paths["backup"])
    if not all(path.is_file() for path in required):
        raise LocalDatabaseUpdateError(
            "existing candidate receipt directory is incomplete; choose a new candidate"
        )
    plan = migration.read_receipt(paths["plan"])
    receipt = migration.read_receipt(paths["operation"])
    plan_source = plan.get("source")
    plan_source_database = (
        plan_source.get("database") if isinstance(plan_source, dict) else None
    )
    if plan_source_database != source or plan.get("candidate_database") != candidate:
        raise LocalDatabaseUpdateError("existing candidate plan targets another database")
    if receipt.get("candidate_database") != candidate:
        raise LocalDatabaseUpdateError("existing candidate operation targets another database")
    status = receipt.get("status")
    phase = receipt.get("phase")
    if status == "prepared" and phase == "restore":
        discard_incomplete_candidate(config, source, candidate)
        migration.restore_candidate(
            config,
            source,
            candidate,
            paths["dump"],
            paths["backup"],
            paths["operation"],
            **_container_argument(mysql_container),
        )
        status = "restored"
    if status == "restored" or (status == "partial" and phase == "schema_apply"):
        allowed_partial_artifacts = resumable_partial_artifacts(receipt)
        migration.apply_schema(
            config,
            source,
            candidate,
            paths["plan"],
            paths["operation"],
            **_container_argument(mysql_container),
            allowed_partial_artifacts=allowed_partial_artifacts,
        )
        status = "backfilled"
    if status in migration.VERIFYABLE_CANDIDATE_STATUSES:
        migration.verify_candidate(config, source, candidate, paths["operation"])
        status = "verified"
    if status != "verified":
        raise LocalDatabaseUpdateError(
            "existing candidate is not resumable from its recorded phase; choose a new candidate"
        )
    replacement = resume_or_replace_source(
        config, source, candidate, paths, mysql_container=mysql_container
    )
    return {
        "status": "completed",
        "source_database": source,
        "candidate_database": candidate,
        "source_backup": str(paths["dump"]),
        "receipt_directory": str(paths["directory"]),
        "replacement": replacement,
        "environment_file_unchanged": str(environment_file),
        "resumed": True,
        "restart_required": True,
    }


# Kept together because only a candidate stalled before restore can be discarded and recreated safely.
def discard_incomplete_candidate(config, source: str, candidate: str) -> None:
    validate_candidate_database(source, candidate)
    connection = config.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{candidate}`")
    finally:
        connection.close()


def resumable_partial_artifacts(receipt: dict[str, object]) -> frozenset[str]:
    raw_steps = receipt.get("schema_steps")
    steps = raw_steps if isinstance(raw_steps, list) else []
    completed_parts = {
        str(step.get("part"))
        for step in steps
        if isinstance(step, dict)
    }
    if completed_parts.intersection(NOTIFICATION_CATALOG_PARTS):
        return LOCAL_RESUMABLE_PARTIAL_ARTIFACTS | NOTIFICATION_CATALOG_PARTS
    return LOCAL_RESUMABLE_PARTIAL_ARTIFACTS


def _container_argument(mysql_container: str | None) -> dict[str, str]:
    if mysql_container is None:
        return {}
    return {"mysql_container": mysql_container}


def update_local_database(
    *,
    environment_file=DEFAULT_ENVIRONMENT_FILE,
    receipt_root=DEFAULT_RECEIPT_ROOT,
    candidate=None,
    apply=False,
    require_current=False,
    confirm_database=None,
    confirm_configured_database=False,
    mysql_container=None,
    database_port=None,
    drift_report=False,
    strategy="auto",
    allow_long_run=False,
    duration_guard_ms=30_000,
    lock_timeout_seconds=5,
    backup_receipt_path=None,
    qualification_receipt_path=None,
) -> dict[str, object]:
    if migration is None:
        raise LocalDatabaseUpdateError(f"migration catalog unavailable: {MIGRATION_IMPORT_ERROR}")
    normalized_strategy = str(strategy or "auto").casefold().replace("_", "-")
    if normalized_strategy == "additive-in-place":
        normalized_strategy = "additive"
    if normalized_strategy not in {"auto", "additive", "replacement", "fresh-reset"}:
        raise LocalDatabaseUpdateError(
            f"unknown update strategy: {strategy}", code="strategy_invalid"
        )
    environment_path = Path(environment_file)
    try:
        environment_values = dict(os.environ)
        if environment_path.is_file():
            _, file_environment_values = migration._read_env_bytes(environment_path)
            environment_values.update(file_environment_values)
        mysql_container = (
            mysql_container
            or environment_values.get("MYSQL_CONTAINER")
            or os.getenv("MYSQL_CONTAINER")
            or None
        )
        mysql_container = resolve_mysql_container(mysql_container)
        config, source = migration.config_from_env(environment_path)
        config = with_database_port(config, database_port)
        validate_local_source(config, source, environment_values)
        if drift_report:
            if apply or require_current or normalized_strategy != "auto":
                raise LocalDatabaseUpdateError(
                    "--drift-report cannot be combined with apply, require-current, or an explicit strategy",
                    code="strategy_flags_conflict",
                )
            return build_drift_report(config, source)
        if normalized_strategy == "fresh-reset":
            preview = {
                "status": "blocked",
                "route": "fresh_reset",
                "selected_strategy": "fresh_reset",
                "target_profile": "local-development",
                "blocked_reason": "fresh reset is owned by scripts/init_db.py or reset_DB.bat",
                "estimated_work": {"artifact_count": 0, "statement_count": 0},
                "duration_guard_ms": 30_000,
            }
        elif normalized_strategy == "replacement":
            if not allow_long_run:
                raise LocalDatabaseUpdateError(
                    "replacement requires --allow-long-run",
                    code="replacement_requires_allow_long_run",
                )
            target = candidate or candidate_name(source)
            validate_candidate_database(source, target)
            preview = build_preview(config, source, target)
            preview.update({
                "route": "rare_replacement",
                "selected_strategy": "replacement",
                "warning": "long-running preserve-data candidate replacement explicitly selected",
                "allow_long_run": True,
                "estimated_work": {
                    "artifact_count": len(preview.get("parts_to_apply", ())),
                    "statement_count": "unbounded_candidate_flow",
                },
            })
        else:
            preview = build_additive_preview(
                config,
                source,
                Path(receipt_root),
                backup_receipt_path=(
                    Path(backup_receipt_path)
                    if backup_receipt_path is not None
                    else None
                ),
                duration_guard_ms=duration_guard_ms,
                qualification_receipt_path=(
                    Path(qualification_receipt_path)
                    if qualification_receipt_path is not None
                    else None
                ),
            )
    except migration.UpgradeBlocked as error:
        raise LocalDatabaseUpdateError(str(error)) from error
    except LocalDatabaseUpdateError:
        raise
    except Exception as error:
        raise LocalDatabaseUpdateError("database update preview failed") from error
    if require_current:
        if apply:
            raise LocalDatabaseUpdateError(
                "--require-current cannot be combined with --apply",
                code="strategy_flags_conflict",
            )
        if preview.get("status") == "current":
            return {
                "status": "current",
                "source_database": source,
                "release_id": preview.get("release_id"),
            }
        if preview.get("status") != "blocked":
            raise LocalDatabaseUpdateError(
                "schema update required",
                code="schema_update_required",
            )
        raise LocalDatabaseUpdateError(
            str(preview.get("blocked_reason") or "database update is blocked"),
            code=str(preview.get("code") or "database_update_blocked"),
        )
    if not apply:
        return {key: value for key, value in preview.items() if key != "plan"}
    if preview.get("status") == "blocked":
        raise LocalDatabaseUpdateError(
            str(preview.get("blocked_reason") or "database update is blocked"),
            code=str(preview.get("code") or "database_update_blocked"),
        )
    if confirm_configured_database:
        confirm_database = source
    if confirm_database != source:
        raise LocalDatabaseUpdateError(
            f"apply requires --confirm-database {source}",
            code="confirmation_required",
        )
    try:
        if normalized_strategy in {"auto", "additive"}:
            require_mysql_apply_client(mysql_container)
            return apply_additive_update(
                config,
                source,
                Path(receipt_root),
                backup_receipt_path=(
                    Path(backup_receipt_path)
                    if backup_receipt_path is not None
                    else None
                ),
                duration_guard_ms=duration_guard_ms,
                lock_timeout_seconds=lock_timeout_seconds,
                mysql_container=mysql_container,
                qualification_receipt_path=(
                    Path(qualification_receipt_path)
                    if qualification_receipt_path is not None
                    else None
                ),
            )
        require_mysql_clients(mysql_container)
        arguments = (config, environment_path, preview, Path(receipt_root))
        if mysql_container is None:
            return apply_update(*arguments)
        return apply_update(*arguments, mysql_container=mysql_container)
    except LocalDatabaseUpdateError:
        raise
    except migration.UpgradeBlocked as error:
        raise LocalDatabaseUpdateError(str(error)) from error
    except Exception as error:
        raise LocalDatabaseUpdateError(
            f"database update execution failed: {type(error).__name__}",
            code="database_update_execution_failed",
        ) from error


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser()
    command.add_argument("--environment-file", type=Path, default=DEFAULT_ENVIRONMENT_FILE)
    command.add_argument("--receipt-root", type=Path, default=DEFAULT_RECEIPT_ROOT)
    command.add_argument("--candidate-database")
    command.add_argument("--apply", action="store_true")
    command.add_argument("--dry-run", action="store_true", help="bounded preview; never mutates the source")
    command.add_argument("--drift-report", action="store_true")
    command.add_argument("--require-current", action="store_true")
    command.add_argument("--confirm-database")
    command.add_argument("--confirm-configured-database", action="store_true")
    command.add_argument("--mysql-container")
    command.add_argument("--database-port", type=int)
    command.add_argument(
        "--strategy",
        choices=("auto", "additive", "additive-in-place", "replacement", "fresh-reset"),
        default="auto",
    )
    command.add_argument(
        "--allow-long-run",
        action="store_true",
        help="required for the explicit preserve-data replacement route",
    )
    command.add_argument("--duration-guard-ms", type=int, default=30_000)
    command.add_argument("--lock-timeout-seconds", type=int, default=5)
    command.add_argument("--backup-receipt", type=Path)
    command.add_argument("--qualification-receipt", type=Path)
    return command


def main() -> int:
    arguments = parser().parse_args()
    if arguments.dry_run and arguments.apply:
        print(json.dumps({"status": "blocked", "code": "dry_run_apply_conflict", "error": "--dry-run cannot be combined with --apply"}, ensure_ascii=False), file=sys.stderr)
        return 2
    try:
        result = update_local_database(
            environment_file=arguments.environment_file,
            receipt_root=arguments.receipt_root,
            candidate=arguments.candidate_database,
            apply=arguments.apply,
            require_current=arguments.require_current,
            confirm_database=arguments.confirm_database,
            confirm_configured_database=arguments.confirm_configured_database,
            mysql_container=arguments.mysql_container,
            database_port=arguments.database_port,
            drift_report=arguments.drift_report,
            strategy=arguments.strategy,
            allow_long_run=arguments.allow_long_run,
            duration_guard_ms=arguments.duration_guard_ms,
            lock_timeout_seconds=arguments.lock_timeout_seconds,
            backup_receipt_path=arguments.backup_receipt,
            qualification_receipt_path=arguments.qualification_receipt,
        )
    except LocalDatabaseUpdateError as error:
        payload = {
            "status": "blocked",
            "error": str(error),
            "code": getattr(error, "code", "database_update_blocked"),
        }
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
