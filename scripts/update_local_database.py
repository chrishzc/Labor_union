"""
File: update_local_database.py
Description: 依 canonical release chain 預覽並逐版執行受控本機 additive 升級；replacement 必須明確選用。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
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


def _plan_receipt_payload(preview: dict[str, object]) -> dict[str, object]:
    payload = {
        "contract": "local-database-update/v1",
        "mode": "dry-run",
        "source_database": preview.get("source_database"),
        "candidate_database": preview.get("candidate_database"),
        "release_id": preview.get("release_id"),
        "release_fingerprint": preview.get("release_fingerprint"),
        "source_schema_sha256": preview.get("source_schema_sha256"),
    }
    payload["plan_fingerprint"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return payload


def _validate_plan_receipt(path: Path, preview: dict[str, object]) -> None:
    try:
        payload = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LocalDatabaseUpdateError(
            "prior dry-run receipt is not valid UTF-8 JSON",
            code="plan_receipt_invalid",
        ) from error
    expected = _plan_receipt_payload(preview)
    if payload != expected:
        raise LocalDatabaseUpdateError(
            "prior dry-run receipt does not match the current schema plan",
            code="plan_drift",
        )


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
    if len(source) > MYSQL_IDENTIFIER_MAX_LENGTH:
        raise LocalDatabaseUpdateError("source database name exceeds 64 characters")
    if any("prod" in str(values.get(key, "")).casefold() for key in ("APP_ENV", "ENV", "FLASK_ENV")):
        raise LocalDatabaseUpdateError("production environment refused")
    profile = str(
        values.get("APP_ENV", values.get("ENV", values.get("FLASK_ENV", "local")))
    ).casefold()
    if source.casefold() in migration.LOCAL_ADDITIVE_SYSTEM_DATABASES:
        raise LocalDatabaseUpdateError(
            "developer update refuses MySQL system databases"
        )
    if profile not in {"local", "development", "dev", "test", "testing"}:
        raise LocalDatabaseUpdateError("local development profile required")


def _database_config_from_environment(
    environment_path: Path,
    environment_values: dict[str, str],
):
    """Use a strict env file when present, otherwise require explicit process values."""
    try:
        return migration.config_from_env(environment_path)
    except FileNotFoundError:
        pass
    return (
        migration.DatabaseConfig(
            host=environment_values.get("DB_HOST", "127.0.0.1"),
            port=int(environment_values.get("DB_PORT", "3306")),
            user=environment_values.get("DB_USER", "root"),
            password=environment_values.get("DB_PASSWORD", ""),
        ),
        environment_values.get("DB_DATABASE", "").strip(),
    )
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


def _fast_backup_receipt_path(
    receipt_root: Path, source: str, release_id: str,
) -> Path:
    return (
        Path(receipt_root).expanduser().resolve()
        / "fast_additive"
        / f"{source}.{release_id}.backup.receipt.json"
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
    """Back up and apply only the already-qualified local source plan."""
    if additive is None:
        raise LocalDatabaseUpdateError(
            f"additive runner unavailable: {ADDITIVE_IMPORT_ERROR}"
        )
    if not isinstance(source, str) or not migration.IDENTIFIER.fullmatch(source):
        raise LocalDatabaseUpdateError(
            "source database name is invalid",
            code="target_profile_blocked",
        )
    if callable(getattr(config, "connect", None)):
        identity = migration.server_identity(config, source)
        if identity.get("database") != source or not identity.get("server"):
            raise LocalDatabaseUpdateError(
                "configured connected database host identity does not match the explicit database target",
                code="connected_identity_mismatch",
            )
    # Recompute the plan immediately before backup/DDL so schema fingerprint and
    # release identity drift fail closed on every apply or resume/replay.
    applied_releases: list[str] = []
    while True:
        preview = build_additive_preview(
            config,
            source,
            receipt_root,
            qualification_receipt_path=qualification_receipt_path,
        )
        if preview.get("status") == "current":
            current = require_current_database(preview)
            current["applied_releases"] = applied_releases
            current["terminal_receipt"] = str(
                migration._local_receipt_path(Path(receipt_root), source)
            )
            return current
        if preview.get("status") != "ready":
            raise LocalDatabaseUpdateError(
                f"{preview.get('blocked_reason', 'additive route blocked')} "
                f"[{preview.get('code', 'additive_blocked')}]"
            )
        pending = preview.get("pending_releases")
        if not isinstance(pending, list) or not pending:
            raise LocalDatabaseUpdateError(
                "ordered additive preview is incomplete",
                code="release_chain_invalid",
            )
        next_release = pending[0]
        if not isinstance(next_release, dict):
            raise LocalDatabaseUpdateError(
                "ordered additive preview is malformed",
                code="release_chain_invalid",
            )
        release_id = next_release.get("release_id")
        qualification_reference = next_release.get("qualification_receipt")
        if (
            not isinstance(release_id, str)
            or not isinstance(qualification_reference, str)
            or release_id in applied_releases
        ):
            raise LocalDatabaseUpdateError(
                "ordered additive progression is invalid",
                code="release_chain_invalid",
            )
        qualification_path = Path(qualification_reference)
        if not qualification_path.is_absolute():
            qualification_path = ROOT / qualification_path
        receipt_path = (
            Path(backup_receipt_path).expanduser().resolve()
            if backup_receipt_path is not None and not applied_releases
            else _fast_backup_receipt_path(
                Path(receipt_root), source, release_id
            )
        )
        dump_path = receipt_path.with_suffix(".sql")
        execution_phase = "backup"
        try:
            additive.prepare_backup(
                config,
                source,
                receipt_root=Path(receipt_root),
                backup_dump_path=dump_path,
                backup_receipt_path=receipt_path,
                mysql_container=mysql_container,
                qualification_path=qualification_path,
            )
            execution_phase = "apply"
            additive.apply(
                config,
                source,
                receipt_root=Path(receipt_root),
                duration_guard_ms=duration_guard_ms,
                lock_timeout_seconds=lock_timeout_seconds,
                qualification_path=qualification_path,
                backup_dump_path=dump_path,
                backup_receipt_path=receipt_path,
            )
        except additive.LocalAdditiveBlocked as error:
            raise LocalDatabaseUpdateError(
                f"{error} [{error.code}]"
            ) from error
        except Exception as error:
            raise LocalDatabaseUpdateError(
                f"release {release_id} failed during {execution_phase}: "
                f"{type(error).__name__}; rerun the updater to resume from its journal",
                code="database_update_execution_failed",
            ) from error
        applied_releases.append(release_id)


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
    try:
        entries = migration._local_ordered_upgrade_entries()
    except Exception as error:
        raise LocalDatabaseUpdateError(
            "canonical schema release chain is not current",
            code="schema_update_required",
        ) from error
    expected_artifacts = [
        {
            "name": entry["artifact"]["name"],
            "release_id": entry["release_id"],
            "release_fingerprint": entry["release_fingerprint"],
            "state": "exact",
        }
        for entry in entries
    ]
    artifacts = preview.get("artifacts")
    baseline = entries[0]["release_id"]
    latest = entries[-1]["release_id"]
    latest_fingerprint = entries[-1]["release_fingerprint"]
    projected_artifacts = (
        [
            {
                "name": item.get("name"),
                "release_id": item.get("release_id"),
                "release_fingerprint": item.get("release_fingerprint"),
                "state": item.get("state"),
            }
            for item in artifacts
        ]
        if isinstance(artifacts, list)
        and all(isinstance(item, dict) for item in artifacts)
        else None
    )
    if (
        preview.get("status") != "current"
        or preview.get("baseline_release_id") != baseline
        or preview.get("latest_release_id") != latest
        or preview.get("release_id") != latest
        or preview.get("release_fingerprint") != latest_fingerprint
        or projected_artifacts != expected_artifacts
        or preview.get("pending_releases") != []
    ):
        raise LocalDatabaseUpdateError(
            "canonical schema release chain is not current",
            code="schema_update_required",
        )
    return {
        "status": "current",
        "source_database": preview.get("source_database"),
        "release_id": latest,
        "baseline_release_id": baseline,
        "latest_release_id": latest,
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
    plan_receipt_path=None,
    resume=False,
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
        if resume and not apply:
            raise LocalDatabaseUpdateError(
                "--resume requires --apply",
                code="strategy_flags_conflict",
            )
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
        config, source = _database_config_from_environment(
            environment_path,
            environment_values,
        )
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
    if plan_receipt_path is not None and apply:
        _validate_plan_receipt(Path(plan_receipt_path), preview)
    if require_current:
        if apply:
            raise LocalDatabaseUpdateError(
                "--require-current cannot be combined with --apply",
                code="strategy_flags_conflict",
            )
        if preview.get("status") == "current":
            return require_current_database(preview)
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
    command.add_argument(
        "--plan-receipt",
        type=Path,
        help="write a dry-run plan receipt and validate it before apply",
    )
    command.add_argument(
        "--receipt-path",
        type=Path,
        help="optional terminal receipt path for a completed mutation",
    )
    command.add_argument(
        "--resume",
        action="store_true",
        help="resume/replay the recorded additive journal after an interruption",
    )
    command.add_argument(
        "--verify",
        action="store_true",
        help="verify a previously written terminal receipt without a database write",
    )
    return command


def main() -> int:
    arguments = parser().parse_args()
    mode = "dry-run" if not arguments.apply else "apply"
    if arguments.dry_run and arguments.apply:
        print(json.dumps({"status": "blocked", "code": "dry_run_apply_conflict", "error": "--dry-run cannot be combined with --apply"}, ensure_ascii=False), file=sys.stderr)
        return 2
    if arguments.verify:
        if arguments.apply or not arguments.receipt_path:
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "code": "terminal_receipt_required",
                        "error": "--verify requires --receipt-path and cannot be combined with --apply",
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 2
        try:
            receipt = json.loads(
                arguments.receipt_path.expanduser().resolve().read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            print(
                json.dumps(
                    {"status": "blocked", "code": "terminal_receipt_invalid", "error": str(error)},
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 2
        if receipt.get("receipt_status") != "committed":
            print(
                json.dumps(
                    {"status": "blocked", "code": "terminal_receipt_invalid", "error": "terminal receipt is not committed"},
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 2
        receipt["status"] = "verified"
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0
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
            plan_receipt_path=arguments.plan_receipt,
            resume=arguments.resume,
        )
    except LocalDatabaseUpdateError as error:
        payload = {
            "status": "blocked",
            "error": str(error),
            "code": getattr(error, "code", "database_update_blocked"),
        }
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        return 2
    if result.get("status") == "blocked":
        print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    if not arguments.apply and arguments.plan_receipt:
        arguments.plan_receipt.parent.mkdir(parents=True, exist_ok=True)
        arguments.plan_receipt.write_text(
            json.dumps(_plan_receipt_payload(result), ensure_ascii=False, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    if arguments.apply and arguments.receipt_path:
        if result.get("status") not in {"completed", "current"}:
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "code": "terminal_receipt_required",
                        "error": "mutation did not produce a terminal receipt",
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 2
        terminal = {
            "contract": "local-database-update/v1",
            "mode": "apply",
            "receipt_status": "committed",
            "source_database": result.get("source_database"),
            "release_id": result.get("release_id"),
            "release_fingerprint": result.get("release_fingerprint"),
            "terminal_receipt": result.get("terminal_receipt"),
            "replay_key": result.get("release_fingerprint"),
        }
        arguments.receipt_path.parent.mkdir(parents=True, exist_ok=True)
        arguments.receipt_path.write_text(
            json.dumps(terminal, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
