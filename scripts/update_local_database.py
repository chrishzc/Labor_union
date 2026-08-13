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


DEFAULT_ENVIRONMENT_FILE = ROOT / ".env"
DEFAULT_RECEIPT_ROOT = ROOT / "scratch/local_database_updates"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
MYSQL_IDENTIFIER_MAX_LENGTH = 64
LOCAL_RESUMABLE_PARTIAL_ARTIFACTS = frozenset({
    "148_knowledge_retrieval.sql",
    "163_knowledge_runtime.sql",
    "181_matching_service_date_confirmation.sql",
    "186_line_identity_management.sql",
})


class LocalDatabaseUpdateError(RuntimeError):
    pass


def validate_local_source(config, source: str, environment=None) -> None:
    values = environment if environment is not None else os.environ
    if config.host.casefold() not in LOCAL_HOSTS:
        raise LocalDatabaseUpdateError("developer update only accepts local MySQL")
    if not isinstance(source, str) or not migration.IDENTIFIER.fullmatch(source):
        raise LocalDatabaseUpdateError("source database name is invalid")
    if any("prod" in str(values.get(key, "")).casefold() for key in ("APP_ENV", "ENV", "FLASK_ENV")):
        raise LocalDatabaseUpdateError("production environment refused")


def candidate_name(source: str, now=None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d%H%M%S")
    suffix = f"_local_{timestamp}"
    return f"{source[:MYSQL_IDENTIFIER_MAX_LENGTH - len(suffix)]}{suffix}"


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


def restore_dump(config, database: str, dump_path: Path) -> None:
    command = migration._mysql_base(config, "mysql") + [database]
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
        "show_create_tables",
    )
    for key in structural_keys:
        if source_schema[key] != candidate_schema[key]:
            raise LocalDatabaseUpdateError(f"rebuilt union_db schema differs: {key}")
    source_programs = migration._restored_schema_program_evidence(
        source_schema, source, (candidate,)
    )
    candidate_programs = migration._restored_schema_program_evidence(
        candidate_schema, candidate, (source,)
    )
    if source_programs != candidate_programs:
        raise LocalDatabaseUpdateError("rebuilt union_db triggers or views differ")


def rollback_source(
    config,
    source: str,
    dump_path: Path,
    expected_data,
    expected_schema_sha256: str,
) -> None:
    recreate_database(config, source)
    restore_dump(config, source, dump_path)
    if migration._table_evidence(config, source) != expected_data:
        raise LocalDatabaseUpdateError("automatic rollback data verification failed")
    actual_schema = migration._schema_snapshot(config, source)["sha256"]
    if actual_schema != expected_schema_sha256:
        raise LocalDatabaseUpdateError("automatic rollback schema verification failed")


# Kept together so the destructive replacement and its mandatory rollback remain one visible boundary.
def replace_source_database(config, source: str, candidate: str, paths: dict[str, Path]) -> dict[str, object]:
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
        restore_dump(config, source, paths["candidate_dump"])
        verification = verify_replacement(config, source, candidate)
    except Exception:
        rollback_source(
            config,
            source,
            paths["dump"],
            expected_source_data,
            expected_schema_sha256,
        )
        receipt.update(status="rolled_back")
        migration.write_receipt(paths["replacement"], receipt)
        raise
    receipt.update(status="completed", verification=verification)
    migration.write_receipt(paths["replacement"], receipt)
    return receipt


# Kept together because this is the operator-facing phase order and contains no lower-level SQL details.
def apply_update(config, environment_file: Path, preview: dict[str, object], receipt_root: Path) -> dict[str, object]:
    source = str(preview["source_database"])
    candidate = str(preview["candidate_database"])
    paths = artifact_paths(receipt_root, candidate)
    paths["directory"].mkdir(parents=True, exist_ok=False)
    migration.write_receipt(paths["plan"], preview["plan"])
    migration.create_source_dump(config, source, paths["dump"], paths["backup"])
    migration.restore_candidate(config, source, candidate, paths["dump"], paths["backup"], paths["operation"])
    migration.apply_schema(
        config,
        source,
        candidate,
        paths["plan"],
        paths["operation"],
        allowed_partial_artifacts=LOCAL_RESUMABLE_PARTIAL_ARTIFACTS,
    )
    migration.verify_candidate(config, source, candidate, paths["operation"])
    migration.create_source_dump(
        config,
        candidate,
        paths["candidate_dump"],
        paths["candidate_backup"],
    )
    replacement = replace_source_database(config, source, candidate, paths)
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


def update_local_database(
    *,
    environment_file=DEFAULT_ENVIRONMENT_FILE,
    receipt_root=DEFAULT_RECEIPT_ROOT,
    candidate=None,
    apply=False,
    require_current=False,
    confirm_database=None,
    confirm_configured_database=False,
) -> dict[str, object]:
    if migration is None:
        raise LocalDatabaseUpdateError(f"migration catalog unavailable: {MIGRATION_IMPORT_ERROR}")
    environment_path = Path(environment_file)
    try:
        config, source = migration.config_from_env(environment_path)
        validate_local_source(config, source)
        target = candidate or candidate_name(source)
        preview = build_preview(config, source, target)
    except migration.UpgradeBlocked as error:
        raise LocalDatabaseUpdateError(str(error)) from error
    except Exception as error:
        raise LocalDatabaseUpdateError("database update preview failed") from error
    if require_current:
        if apply:
            raise LocalDatabaseUpdateError("--require-current cannot be combined with --apply")
        return require_current_database(preview)
    if not apply:
        return {key: value for key, value in preview.items() if key != "plan"}
    if confirm_configured_database:
        confirm_database = source
    if confirm_database != source:
        raise LocalDatabaseUpdateError(f"apply requires --confirm-database {source}")
    try:
        return apply_update(
            config, environment_path, preview, Path(receipt_root)
        )
    except LocalDatabaseUpdateError:
        raise
    except migration.UpgradeBlocked as error:
        raise LocalDatabaseUpdateError(str(error)) from error
    except Exception as error:
        raise LocalDatabaseUpdateError("database update execution failed") from error


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser()
    command.add_argument("--environment-file", type=Path, default=DEFAULT_ENVIRONMENT_FILE)
    command.add_argument("--receipt-root", type=Path, default=DEFAULT_RECEIPT_ROOT)
    command.add_argument("--candidate-database")
    command.add_argument("--apply", action="store_true")
    command.add_argument("--require-current", action="store_true")
    command.add_argument("--confirm-database")
    command.add_argument("--confirm-configured-database", action="store_true")
    return command


def main() -> int:
    arguments = parser().parse_args()
    try:
        result = update_local_database(
            environment_file=arguments.environment_file,
            receipt_root=arguments.receipt_root,
            candidate=arguments.candidate_database,
            apply=arguments.apply,
            require_current=arguments.require_current,
            confirm_database=arguments.confirm_database,
            confirm_configured_database=arguments.confirm_configured_database,
        )
    except LocalDatabaseUpdateError as error:
        payload = {"status": "blocked", "error": str(error)}
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
