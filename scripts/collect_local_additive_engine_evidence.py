"""
File: collect_local_additive_engine_evidence.py
Description: 從final receipts、dump與lu_test_* readback產生strict qualification supporting evidence。
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Sequence

from scripts import build_local_additive_qualification as builder
from scripts import migrate_preserved_database_additive_schema as migration


SCRATCH_ROOT = migration.ROOT / "scratch"
SAFE_ARTIFACT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.sql")


class EngineEvidenceError(ValueError):
    """表示final engine evidence不符合本機qualification契約。"""


def _require_database_boundary(
    source: str, candidate: str, fresh: str, profile: str
) -> None:
    databases = (source, candidate, fresh)
    if str(profile).strip().casefold() not in {
        "local", "development", "dev", "test", "testing"
    }:
        raise EngineEvidenceError("development profile is required")
    if len(set(databases)) != len(databases):
        raise EngineEvidenceError("source, candidate and fresh databases must differ")
    if any(
        not isinstance(database, str)
        or migration.IDENTIFIER.fullmatch(database) is None
        or not database.casefold().startswith("lu_test_")
        or database.casefold() == "union_db"
        or database.casefold() in migration.LOCAL_ADDITIVE_SYSTEM_DATABASES
        for database in databases
    ):
        raise EngineEvidenceError("engine evidence only accepts lu_test_* databases")


def _verify_release_boundary(
    config: Any,
    database: str,
    release_id: str,
    *,
    applied: bool,
    snapshot: Mapping[str, Any],
) -> list[str]:
    entries = migration._local_ordered_upgrade_entries()
    target_indexes = [
        index for index, entry in enumerate(entries)
        if entry["release_id"] == release_id
    ]
    if len(target_indexes) != 1:
        raise EngineEvidenceError("release must select one ordered chain entry")
    target_index = target_indexes[0]
    states: list[str] = []
    dependency_gap_seen = False
    for entry in entries:
        state = migration.local_additive_target_state(
            config,
            database,
            entry["artifact"]["name"],
            entry["descriptor"],
            snapshot=snapshot,
        )["state"]
        if (
            dependency_gap_seen
            and state not in {"absent", "exact"}
            and migration._local_parent_tables_dependency_pending(
                snapshot, entry["descriptor"]
            )
        ):
            state = "dependency_pending"
        states.append(state)
        if state in {"absent", "dependency_pending"}:
            dependency_gap_seen = True

    expected_exact_end = target_index + (1 if applied else 0)
    if any(state != "exact" for state in states[:expected_exact_end]):
        raise EngineEvidenceError("release predecessor prefix is not exact")
    target_state = states[target_index]
    if applied:
        if target_state != "exact":
            raise EngineEvidenceError("applied target release is not exact")
    elif target_state != "absent":
        raise EngineEvidenceError("source target release is not the exact predecessor")
    for state in states[target_index + 1:]:
        if state not in {"absent", "dependency_pending"}:
            raise EngineEvidenceError(f"future release state is {state}")
    return states


def _columns_by_table(snapshot: Mapping[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for row in snapshot.get("columns", ()):
        table = str(row.get("table_name", ""))
        column = str(row.get("column_name", ""))
        if table and column:
            result.setdefault(table, []).append(column)
    return result


def _zero_table_fingerprint(table: str) -> str:
    return migration._local_digest(
        migration._local_canonical_json(
            {"table": table, "state": "absent_or_empty", "row_count": 0}
        )
    )


def _canonical_row_preservation(
    config: Any,
    source: str,
    candidate: str,
    allowed_tables: frozenset[str],
    source_snapshot: Mapping[str, Any],
    candidate_snapshot: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_columns = _columns_by_table(source_snapshot)
    candidate_columns = _columns_by_table(candidate_snapshot)
    counts: dict[str, int] = {}
    fingerprints: dict[str, str] = {}
    for table in sorted(allowed_tables):
        if table in source_columns:
            if table not in candidate_columns:
                raise EngineEvidenceError(f"candidate lost source table: {table}")
            before = migration._table_projection_evidence(
                config, source, table, source_columns[table]
            )
            after = migration._table_projection_evidence(
                config, candidate, table, source_columns[table]
            )
            if before != after:
                raise EngineEvidenceError(f"candidate changed source rows: {table}")
            counts[table] = int(before["row_count"])
            fingerprints[table] = migration._local_digest(
                migration._local_canonical_json(before)
            )
            continue
        if table in candidate_columns:
            added = migration._table_projection_evidence(
                config, candidate, table, candidate_columns[table]
            )
            if int(added["row_count"]) != 0:
                raise EngineEvidenceError(
                    f"schema-only release wrote rows to new table: {table}"
                )
        counts[table] = 0
        fingerprints[table] = _zero_table_fingerprint(table)
    evidence = {
        "data_row_counts": counts,
        "data_fingerprints": fingerprints,
    }
    return evidence, {
        "data_row_counts": dict(counts),
        "data_fingerprints": dict(fingerprints),
    }


def _require_fresh_zero_rows(
    config: Any,
    database: str,
    target_tables: frozenset[str],
    snapshot: Mapping[str, Any],
) -> None:
    for table, columns in _columns_by_table(snapshot).items():
        if table not in target_tables:
            continue
        projection = migration._table_projection_evidence(
            config, database, table, columns
        )
        if int(projection["row_count"]) != 0:
            raise EngineEvidenceError(f"fresh bootstrap contains data rows: {table}")


def _require_final_operation(
    config: Any,
    source: str,
    candidate: str,
    operation_path: Path,
    source_identity: Mapping[str, Any],
    candidate_identity: Mapping[str, Any],
    release_id: str,
    artifact_name: str,
    release_fingerprint: str,
) -> dict[str, Any]:
    operation = migration.read_receipt(operation_path)
    source_receipt = operation.get("source") or {}
    candidate_receipt = operation.get("candidate") or {}
    if (
        operation.get("status") != "verified"
        or operation.get("candidate_database") != candidate
        or source_receipt != source_identity
        or candidate_receipt != candidate_identity
    ):
        raise EngineEvidenceError("operation receipt is not final or identities differ")
    if (
        operation.get("release_id") != release_id
        or operation.get("artifact_name") != artifact_name
        or operation.get("artifact_names") != [artifact_name]
        or operation.get("release_fingerprint") != release_fingerprint
    ):
        raise EngineEvidenceError("operation release identity differs")
    source_data = migration._table_evidence(config, source)
    candidate_data = migration._table_evidence(config, candidate)
    if operation.get("source_data") != source_data:
        raise EngineEvidenceError("source changed after final verification")
    if operation.get("candidate_data") != candidate_data:
        raise EngineEvidenceError("candidate changed after final verification")
    return operation


def _require_dump_binding(
    dump_evidence: Mapping[str, Any],
    receipt: Mapping[str, Any],
    operation: Mapping[str, Any],
    *,
    role: str,
) -> None:
    expected_identity = operation.get("source" if role == "source" else "candidate")
    if not isinstance(expected_identity, Mapping):
        raise EngineEvidenceError("operation dump identity is missing")
    if (
        receipt.get("kind") != "source_backup"
        or receipt.get("exit_code") != 0
        or receipt.get("database") != expected_identity.get("database")
        or receipt.get("server") != expected_identity.get("server")
        or dump_evidence.get("database") != receipt.get("database")
        or dump_evidence.get("server") != receipt.get("server")
        or dump_evidence.get("sha256") != receipt.get("sha256")
    ):
        raise EngineEvidenceError(f"{role} dump is not bound to final identity")
    if role == "source":
        bound = operation.get("source_dump") or {}
        if any(
            bound.get(key) != receipt.get(key)
            for key in ("database", "server", "sha256")
        ):
            raise EngineEvidenceError("source dump is not bound to final operation")
        return
    if role != "candidate":
        raise EngineEvidenceError("dump role is invalid")
    try:
        created_at = datetime.fromisoformat(str(receipt["created_at"]))
        verified_at = datetime.fromisoformat(str(operation["verified_at"]))
    except (KeyError, TypeError, ValueError) as error:
        raise EngineEvidenceError("candidate dump timestamps are invalid") from error
    if created_at <= verified_at:
        raise EngineEvidenceError(
            "candidate dump was not created after final verification"
        )


def collect_evidence(
    *,
    config: Any,
    profile: str,
    release_id: str,
    artifact_name: str,
    source: str,
    candidate: str,
    fresh: str,
    source_dump: Path,
    source_backup_receipt: Path,
    candidate_dump: Path,
    candidate_backup_receipt: Path,
    operation_receipt: Path,
    work_package: str,
) -> dict[str, dict[str, Any]]:
    _require_database_boundary(source, candidate, fresh, profile)
    identity = builder._canonical_identity(release_id, artifact_name)
    source_identity = migration.server_identity(config, source)
    candidate_identity = migration.server_identity(config, candidate)
    fresh_identity = migration.server_identity(config, fresh)
    servers = {
        source_identity.get("server"),
        candidate_identity.get("server"),
        fresh_identity.get("server"),
    }
    if len(servers) != 1:
        raise EngineEvidenceError("source, candidate and fresh servers differ")
    operation = _require_final_operation(
        config,
        source,
        candidate,
        operation_receipt,
        source_identity,
        candidate_identity,
        release_id,
        artifact_name,
        identity["release_fingerprint"],
    )
    source_dump_evidence = migration.validate_dump(
        source_dump, source_backup_receipt, source, source_identity
    )
    candidate_dump_evidence = migration.validate_dump(
        candidate_dump, candidate_backup_receipt, candidate, candidate_identity
    )
    _require_dump_binding(
        source_dump_evidence,
        migration.read_receipt(source_backup_receipt),
        operation,
        role="source",
    )
    _require_dump_binding(
        candidate_dump_evidence,
        migration.read_receipt(candidate_backup_receipt),
        operation,
        role="candidate",
    )
    source_snapshot = migration._schema_snapshot(config, source)
    candidate_snapshot = migration._schema_snapshot(config, candidate)
    fresh_snapshot = migration._schema_snapshot(config, fresh)
    _verify_release_boundary(
        config, source, release_id, applied=False, snapshot=source_snapshot
    )
    _verify_release_boundary(
        config, candidate, release_id, applied=True, snapshot=candidate_snapshot
    )
    _verify_release_boundary(
        config, fresh, release_id, applied=True, snapshot=fresh_snapshot
    )
    source_rows, candidate_rows = _canonical_row_preservation(
        config,
        source,
        candidate,
        identity["allowed_tables"],
        source_snapshot,
        candidate_snapshot,
    )
    _require_fresh_zero_rows(
        config,
        fresh,
        frozenset(identity["canonical_projection"]["tables"]),
        fresh_snapshot,
    )
    target_projection = identity["canonical_projection"]
    target_fingerprint = identity["canonical_projection_fingerprint"]
    common = {
        "status": "verified",
        "release_id": release_id,
        "artifact_name": artifact_name,
        "release_fingerprint": identity["release_fingerprint"],
        "published_manifest_sha256": identity["published_manifest_sha256"],
        "artifact_sql_sha256": identity["artifact_sql_sha256"],
        "descriptor_sha256": identity["descriptor_sha256"],
        "backfills": [],
    }
    bundle = {
        "metadata_backup": {
            **common,
            "contract": "local-additive-metadata-backup-evidence/v1",
            "schema_fingerprint": source_snapshot["sha256"],
            "backup_dump_sha256": source_dump_evidence["sha256"],
            **source_rows,
        },
        "fresh_bootstrap": {
            **common,
            "contract": "local-additive-fresh-bootstrap-evidence/v1",
            "schema_fingerprint": fresh_snapshot["sha256"],
            "target_descriptor_state": "exact",
            "target_projection": target_projection,
            "target_projection_fingerprint": target_fingerprint,
            "data_rows_written": 0,
        },
        "preserve_data_candidate": {
            **common,
            "contract": "local-additive-preserve-data-evidence/v1",
            "source_schema_fingerprint": source_snapshot["sha256"],
            "candidate_schema_fingerprint": candidate_snapshot["sha256"],
            "source_dump_sha256": source_dump_evidence["sha256"],
            "candidate_dump_sha256": candidate_dump_evidence["sha256"],
            "source_data_row_counts": source_rows["data_row_counts"],
            "source_data_fingerprints": source_rows["data_fingerprints"],
            "candidate_data_row_counts": candidate_rows["data_row_counts"],
            "candidate_data_fingerprints": candidate_rows["data_fingerprints"],
            "target_descriptor_state": "exact",
            "target_projection": target_projection,
            "target_projection_fingerprint": target_fingerprint,
        },
    }
    builder.build_qualification(
        release_id=release_id,
        artifact_name=artifact_name,
        metadata_backup=bundle["metadata_backup"],
        fresh_bootstrap=bundle["fresh_bootstrap"],
        preserve_data_candidate=bundle["preserve_data_candidate"],
        work_package=work_package,
    )
    return bundle


def _serialized(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_evidence_bundle(
    bundle: Mapping[str, Mapping[str, Any]],
    output_directory: Path,
    artifact_name: str,
) -> dict[str, Path]:
    if SAFE_ARTIFACT.fullmatch(artifact_name) is None:
        raise EngineEvidenceError("artifact name is invalid")
    root = SCRATCH_ROOT.expanduser().resolve()
    output = Path(output_directory).expanduser().resolve()
    try:
        output.relative_to(root)
    except ValueError:
        raise EngineEvidenceError("evidence output must be below scratch") from None
    stem = artifact_name.removesuffix(".sql")
    targets = {
        kind: output / f"{stem}.{kind}.json"
        for kind in (
            "metadata_backup", "fresh_bootstrap", "preserve_data_candidate"
        )
    }
    if any(path.exists() for path in targets.values()):
        raise EngineEvidenceError("engine evidence already exists")
    output.mkdir(parents=True, exist_ok=True)
    temporary_paths: list[Path] = []
    created_targets: list[Path] = []
    try:
        for kind, target in targets.items():
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=".engine-evidence-", suffix=".json",
                dir=output, delete=False,
            ) as handle:
                handle.write(_serialized(bundle[kind]))
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            temporary_paths.append(temporary)
            try:
                os.link(temporary, target)
            except FileExistsError as error:
                raise EngineEvidenceError("engine evidence already exists") from error
            created_targets.append(target)
            temporary.unlink()
            temporary_paths.remove(temporary)
    except Exception:
        for path in created_targets:
            path.unlink(missing_ok=True)
        raise
    finally:
        for path in temporary_paths:
            path.unlink(missing_ok=True)
    return targets


def _environment(path: Path) -> tuple[Any, str]:
    values = dict(os.environ)
    if Path(path).is_file():
        _, file_values = migration._read_env_bytes(Path(path))
        values.update(file_values)
    config, _ = migration.config_from_env(Path(path))
    profile = str(
        values.get("APP_ENV", values.get("ENV", values.get("FLASK_ENV", "local")))
    )
    return config, profile


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser()
    command.add_argument("--environment-file", type=Path, default=migration.ROOT / ".env")
    command.add_argument("--release-id", required=True)
    command.add_argument("--artifact", required=True)
    command.add_argument("--source-database", required=True)
    command.add_argument("--candidate-database", required=True)
    command.add_argument("--fresh-database", required=True)
    command.add_argument("--source-dump", type=Path, required=True)
    command.add_argument("--source-backup-receipt", type=Path, required=True)
    command.add_argument("--candidate-dump", type=Path, required=True)
    command.add_argument("--candidate-backup-receipt", type=Path, required=True)
    command.add_argument("--operation-receipt", type=Path, required=True)
    command.add_argument("--work-package", required=True)
    command.add_argument("--output-directory", type=Path, required=True)
    return command


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        config, profile = _environment(arguments.environment_file)
        bundle = collect_evidence(
            config=config,
            profile=profile,
            release_id=arguments.release_id,
            artifact_name=arguments.artifact,
            source=arguments.source_database,
            candidate=arguments.candidate_database,
            fresh=arguments.fresh_database,
            source_dump=arguments.source_dump,
            source_backup_receipt=arguments.source_backup_receipt,
            candidate_dump=arguments.candidate_dump,
            candidate_backup_receipt=arguments.candidate_backup_receipt,
            operation_receipt=arguments.operation_receipt,
            work_package=arguments.work_package,
        )
        paths = _write_evidence_bundle(
            bundle, arguments.output_directory, arguments.artifact
        )
    except (EngineEvidenceError, migration.UpgradeBlocked, builder.QualificationBuilderError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps({
        "status": "verified",
        "evidence": {kind: str(path) for kind, path in paths.items()},
        "qualification_published": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
