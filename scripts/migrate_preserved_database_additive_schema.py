"""Preserve-first MySQL candidate upgrade runner.

The live source database is read-only.  Every schema/data mutation is guarded
by an explicit, different candidate database identity and a durable receipt.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pymysql

from infrastructure.migration.rehearsal_runtime import (
    CandidateReadSmokePort,
    CandidateRuntimeConfig,
    EphemeralCandidateRestartPort,
)
from infrastructure.migration.verification import (
    restart_and_run_read_smoke,
    run_manifest_verifications,
)
from shared_kernel.migration_release import (
    MigrationReleaseManifest,
    load_migration_release_manifest,
)


SCHEMA_PARTS = (
    ROOT / "db" / "schema_parts" / "61_finance_import_reprocessing.sql",
    ROOT / "db" / "schema_parts" / "104_order_lifecycle_state_history.sql",
    ROOT / "db" / "schema_parts" / "105_order_service_time_terms.sql",
    ROOT / "db" / "schema_parts" / "106_order_lifecycle_control_facts.sql",
    ROOT / "db" / "schema_parts" / "107_system_alert_current_projection.sql",
    ROOT / "db" / "schema_parts" / "108_matching_records_resume_delivery.sql",
)
IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")
MYSQL_DUMP_MARKER = b"MySQL dump"
VERIFYABLE_CANDIDATE_STATUSES = frozenset(
    {"schema_applied", "backfilled", "verified"}
)
MANIFEST_DRIVEN_RELEASE = False

OWNED_OBJECTS: dict[str, dict[str, Any]] = {
    "61_finance_import_reprocessing.sql": {
        "tables": {
            "finance_import_reprocess_runs": {
                "id", "batch_id", "actor", "classifier_version",
                "plan_fingerprint", "selected_count", "changed_count",
                "dispatch_count", "reconciled_count", "pending_count",
                "request_summary", "result_summary", "status",
            },
            "finance_import_reclassification_events": {
                "id", "run_id", "finance_import_row_id", "actor",
                "before_classification_type", "after_classification_type",
                "dispatch_result", "dispatch_reason",
            },
        },
        "triggers": {
            "trg_finance_import_reprocess_runs_before_update",
            "trg_finance_import_reprocess_runs_before_delete",
            "trg_finance_import_reclassification_events_before_update",
            "trg_finance_import_reclassification_events_before_delete",
        },
    },
    "104_order_lifecycle_state_history.sql": {
        "tables": {
            "order_lifecycle_state_events": {
                "id", "case_no", "trigger_event", "before_status",
                "after_status", "actor", "business_date",
                "expected_version", "idempotency_key",
                "facts_snapshot",
            },
        },
        "triggers": {
            "trg_order_lifecycle_state_events_before_update",
            "trg_order_lifecycle_state_events_before_delete",
        },
    },
    "105_order_service_time_terms.sql": {
        "tables": {
            "orders": {
                "service_start_time", "service_end_time",
                "service_end_day_offset",
            },
        },
        "triggers": set(),
    },
    "106_order_lifecycle_control_facts.sql": {
        "tables": {
            "orders": {"lifecycle_version"},
            "order_lifecycle_control_events": {
                "id", "case_no", "control_type", "control_key", "scope",
                "action", "actor", "reason", "expected_version",
                "idempotency_key", "payload_hash", "payload_snapshot",
            },
            "order_lifecycle_control_state": {
                "case_no", "control_type", "control_key", "scope", "state",
                "current_event_id", "release_policy", "expires_at_utc",
                "confirmed_start_date", "deposit_settlement_identity_hash",
            },
            "order_lifecycle_projection_outbox": {
                "id", "case_no", "lifecycle_event_id", "intent_key",
                "scope", "alert_code", "action", "payload_hash",
                "payload_snapshot", "status", "attempt_count",
            },
        },
        "triggers": {
            "trg_order_lifecycle_control_events_before_update",
            "trg_order_lifecycle_control_events_before_delete",
            "trg_order_lifecycle_control_state_before_delete",
        },
    },
    "107_system_alert_current_projection.sql": {
        "tables": {
            "system_alerts": {
                "id", "alert_code", "source_domain", "case_key", "reason",
                "details", "status", "claimed_by", "claimed_at",
                "resolved_by", "resolved_at", "resolution_reason",
                "created_at", "updated_at",
            },
        },
        "triggers": set(),
    },
    "108_matching_records_resume_delivery.sql": {
        "tables": {
            "matching_records": {"sent_resume_at"},
        },
        "triggers": set(),
    },
}


@dataclass(frozen=True, slots=True)
class ReleaseSelection:
    """Validated migration artifacts selected for one runner operation."""

    release_id: str
    source_baseline_id: str
    fingerprint: str
    manifests: tuple[MigrationReleaseManifest, ...]
    schema_artifacts: tuple[Any, ...]
    backfills: tuple[Any, ...]
    verification_contracts: tuple[Any, ...]
    required_restart_targets: tuple[str, ...]
    post_cutover_smoke_ids: tuple[str, ...]


def _legacy_release_selection() -> ReleaseSelection:
    payload = [
        {
            "name": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in SCHEMA_PARTS
    ]
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return ReleaseSelection(
        release_id="legacy-preserve-runner-v1",
        source_baseline_id="legacy-runner-owned-objects-v1",
        fingerprint=fingerprint,
        manifests=(),
        schema_artifacts=(),
        backfills=(),
        verification_contracts=(),
        required_restart_targets=(),
        post_cutover_smoke_ids=(),
    )


RELEASE_MANIFEST = _legacy_release_selection()


def configure_release_manifests(manifest_paths: Iterable[Path]) -> None:
    """Select a validated, ordered manifest chain for the current process."""

    paths = tuple(Path(path).expanduser().resolve() for path in manifest_paths)
    if not paths:
        return
    manifests = tuple(
        load_migration_release_manifest(path, ROOT) for path in paths
    )
    _validate_release_chain(manifests)
    schema_paths = tuple(
        path for manifest in manifests for path in manifest.schema_paths(ROOT)
    )
    descriptors: dict[str, dict[str, Any]] = {}
    for manifest in manifests:
        for name, descriptor in manifest.owned_object_descriptors(ROOT).items():
            if name in descriptors:
                raise UpgradeBlocked(f"duplicate migration artifact: {name}")
            descriptors[name] = descriptor
    selection = ReleaseSelection(
        release_id="+".join(item.release_id for item in manifests),
        source_baseline_id=manifests[0].source_baseline_id,
        fingerprint=_manifest_chain_fingerprint(manifests),
        manifests=manifests,
        schema_artifacts=tuple(
            item for manifest in manifests for item in manifest.schema_artifacts
        ),
        backfills=tuple(
            item for manifest in manifests for item in manifest.backfills
        ),
        verification_contracts=_unique_verification_contracts(manifests),
        required_restart_targets=_ordered_unique(
            target
            for manifest in manifests
            for target in manifest.required_restart_targets
        ),
        post_cutover_smoke_ids=_ordered_unique(
            smoke_id
            for manifest in manifests
            for smoke_id in manifest.post_cutover_smoke_ids
        ),
    )
    global RELEASE_MANIFEST, SCHEMA_PARTS, OWNED_OBJECTS
    global MANIFEST_DRIVEN_RELEASE
    RELEASE_MANIFEST = selection
    SCHEMA_PARTS = schema_paths
    OWNED_OBJECTS = descriptors
    MANIFEST_DRIVEN_RELEASE = True


def _validate_release_chain(
    manifests: tuple[MigrationReleaseManifest, ...],
) -> None:
    release_ids = tuple(item.release_id for item in manifests)
    if len(release_ids) != len(set(release_ids)):
        raise UpgradeBlocked("migration release IDs must be unique")
    ordinals = tuple(
        int(path.name.split("_", 1)[0])
        for manifest in manifests
        for path in manifest.schema_paths(ROOT)
    )
    if ordinals != tuple(sorted(ordinals)) or len(ordinals) != len(set(ordinals)):
        raise UpgradeBlocked("migration artifacts must be unique and ordered")


def _manifest_chain_fingerprint(
    manifests: tuple[MigrationReleaseManifest, ...],
) -> str:
    payload = [
        {"release_id": item.release_id, "fingerprint": item.fingerprint}
        for item in manifests
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _unique_verification_contracts(
    manifests: tuple[MigrationReleaseManifest, ...],
) -> tuple[Any, ...]:
    contracts: dict[tuple[str, str], Any] = {}
    for manifest in manifests:
        for contract in manifest.verification_contracts:
            key = (contract.phase, contract.verification_id)
            previous = contracts.get(key)
            if previous is not None and previous != contract:
                raise UpgradeBlocked("verification contract conflict")
            contracts[key] = contract
    return tuple(contracts.values())


class UpgradeBlocked(RuntimeError):
    """Fail-closed safety or drift condition."""


def _normalized_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key).casefold(): value for key, value in row.items()}


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    user: str
    password: str

    def connect(self, database: str | None = None):
        kwargs: dict[str, Any] = {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "charset": "utf8mb4",
            "cursorclass": pymysql.cursors.DictCursor,
            "autocommit": True,
        }
        if database:
            kwargs["database"] = database
        return pymysql.connect(**kwargs)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> bytes:
    def default(item: Any) -> Any:
        if isinstance(item, (date, datetime, time)):
            return item.isoformat()
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, bytes):
            return {"bytes_hex": item.hex()}
        raise TypeError(f"unsupported canonical JSON type: {type(item).__name__}")

    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        default=default,
    ).encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_receipt(path: str | Path, receipt: Mapping[str, Any]) -> str:
    target = Path(path)
    _atomic_write(target, _canonical_json(receipt) + b"\n")
    return str(target.expanduser().resolve())


def read_receipt(path: str | Path) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise UpgradeBlocked(f"invalid receipt: {target}") from exc
    if not isinstance(data, dict):
        raise UpgradeBlocked("receipt root must be an object")
    return data


def _read_env_bytes(path: Path) -> tuple[bytes, dict[str, str]]:
    raw = path.expanduser().resolve().read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UpgradeBlocked("environment file must be strict UTF-8") from exc
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return raw, values


def config_from_env(path: Path) -> tuple[DatabaseConfig, str]:
    _, values = _read_env_bytes(path)
    source = values.get(
        "DB_DATABASE", os.getenv("DB_DATABASE", "")
    ).strip()
    return (
        DatabaseConfig(
            host=values.get(
                "DB_HOST", os.getenv("DB_HOST", "127.0.0.1")
            ),
            port=int(values.get("DB_PORT", os.getenv("DB_PORT", "3306"))),
            user=values.get("DB_USER", os.getenv("DB_USER", "root")),
            password=values.get(
                "DB_PASSWORD", os.getenv("DB_PASSWORD", "")
            ),
        ),
        source,
    )


def validate_database_names(source: str, candidate: str) -> None:
    if not IDENTIFIER.fullmatch(source) or not IDENTIFIER.fullmatch(candidate):
        raise UpgradeBlocked("database names must match [A-Za-z0-9_]+")
    if source.casefold() == candidate.casefold():
        raise UpgradeBlocked("candidate database must differ from source")


def validate_rehearsal_database_names(source: str, candidate: str) -> None:
    validate_database_names(source, candidate)
    for database in (source, candidate):
        if not database.casefold().startswith("lu_test_"):
            raise UpgradeBlocked(
                "rehearsal databases must use the lu_test_* namespace"
            )


def server_identity(config: DatabaseConfig, database: str) -> dict[str, Any]:
    connection = config.connect(database)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT DATABASE() AS db, @@hostname AS server, "
                "@@version AS version"
            )
            row = cursor.fetchone()
    finally:
        connection.close()
    if not row or row.get("db") != database:
        raise UpgradeBlocked("database connection identity mismatch")
    return {
        "database": row["db"],
        "server": str(row["server"]),
        "version": str(row["version"]),
        "host": config.host,
        "port": config.port,
    }


def database_exists(config: DatabaseConfig, database: str) -> bool:
    connection = config.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS n FROM information_schema.schemata "
                "WHERE schema_name=%s",
                (database,),
            )
            return int(cursor.fetchone()["n"]) == 1
    finally:
        connection.close()


def _schema_snapshot(config: DatabaseConfig, database: str) -> dict[str, Any]:
    connection = config.connect(database)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name,column_name,column_type,is_nullable,"
                "column_default,extra,generation_expression "
                "FROM information_schema.columns "
                "WHERE table_schema=%s ORDER BY table_name,ordinal_position",
                (database,),
            )
            columns = [_normalized_row(row) for row in cursor.fetchall()]
            cursor.execute(
                "SELECT table_name,index_name,non_unique,"
                "GROUP_CONCAT(column_name ORDER BY seq_in_index) AS columns "
                "FROM information_schema.statistics WHERE table_schema=%s "
                "GROUP BY table_name,index_name,non_unique "
                "ORDER BY table_name,index_name",
                (database,),
            )
            indexes = [_normalized_row(row) for row in cursor.fetchall()]
            cursor.execute(
                "SELECT trigger_name,event_manipulation,event_object_table,"
                "action_timing,action_statement FROM information_schema.triggers "
                "WHERE trigger_schema=%s ORDER BY trigger_name",
                (database,),
            )
            triggers = [_normalized_row(row) for row in cursor.fetchall()]
            cursor.execute(
                "SELECT table_name,view_definition FROM information_schema.views "
                "WHERE table_schema=%s ORDER BY table_name",
                (database,),
            )
            views = [_normalized_row(row) for row in cursor.fetchall()]
            cursor.execute(
                "SELECT tc.table_name,tc.constraint_name,tc.constraint_type,"
                "tc.enforced,cc.check_clause "
                "FROM information_schema.table_constraints tc "
                "LEFT JOIN information_schema.check_constraints cc "
                "ON cc.constraint_schema=tc.constraint_schema "
                "AND cc.constraint_name=tc.constraint_name "
                "WHERE tc.constraint_schema=%s "
                "ORDER BY tc.table_name,tc.constraint_name",
                (database,),
            )
            constraints = [
                _normalized_row(row) for row in cursor.fetchall()
            ]
            cursor.execute(
                "SELECT table_name,constraint_name,column_name,"
                "ordinal_position,referenced_table_name,"
                "referenced_column_name "
                "FROM information_schema.key_column_usage "
                "WHERE constraint_schema=%s "
                "ORDER BY table_name,constraint_name,ordinal_position",
                (database,),
            )
            key_columns = [
                _normalized_row(row) for row in cursor.fetchall()
            ]
            cursor.execute(
                "SELECT table_name,constraint_name,update_rule,delete_rule "
                "FROM information_schema.referential_constraints "
                "WHERE constraint_schema=%s "
                "ORDER BY table_name,constraint_name",
                (database,),
            )
            foreign_keys = [
                _normalized_row(row) for row in cursor.fetchall()
            ]
            table_names = sorted(
                {
                    row["table_name"] for row in columns
                    if row["table_name"] in {
                        table
                        for owned in OWNED_OBJECTS.values()
                        for table in owned["tables"]
                    }
                    or row["table_name"] == "finance_import_batches"
                }
            )
            show_create_tables: dict[str, str] = {}
            for table_name in table_names:
                safe_table = table_name.replace("`", "``")
                cursor.execute(f"SHOW CREATE TABLE `{safe_table}`")
                create_row = _normalized_row(cursor.fetchone() or {})
                create_sql = create_row.get("create table")
                if not isinstance(create_sql, str):
                    raise UpgradeBlocked(
                        f"SHOW CREATE TABLE missing for {table_name}"
                    )
                show_create_tables[table_name] = create_sql
    finally:
        connection.close()
    payload = {
        "columns": columns,
        "indexes": indexes,
        "triggers": triggers,
        "views": views,
        "constraints": constraints,
        "key_columns": key_columns,
        "foreign_keys": foreign_keys,
        "show_create_tables": show_create_tables,
    }
    return {"sha256": _sha256_bytes(_canonical_json(payload)), **payload}


def _table_evidence(config: DatabaseConfig, database: str) -> dict[str, Any]:
    connection = config.connect(database)
    evidence: dict[str, Any] = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema=%s AND table_type='BASE TABLE' "
                "ORDER BY table_name",
                (database,),
            )
            names = [
                _normalized_row(row)["table_name"]
                for row in cursor.fetchall()
            ]
            for name in names:
                cursor.execute(f"SELECT COUNT(*) AS n FROM `{name}`")
                count = int(cursor.fetchone()["n"])
                cursor.execute(f"CHECKSUM TABLE `{name}`")
                checksum_row = _normalized_row(cursor.fetchone() or {})
                checksum = checksum_row.get("checksum")
                cursor.execute(
                    "SELECT column_name FROM information_schema.key_column_usage "
                    "WHERE table_schema=%s AND table_name=%s "
                    "AND constraint_name='PRIMARY' ORDER BY ordinal_position",
                    (database, name),
                )
                primary = [
                    _normalized_row(row)["column_name"]
                    for row in cursor.fetchall()
                ]
                pk_hash = None
                if primary:
                    projection = ",".join(f"`{column}`" for column in primary)
                    cursor.execute(
                        f"SELECT {projection} FROM `{name}` "
                        f"ORDER BY {projection}"
                    )
                    pk_hash = _sha256_bytes(
                        _canonical_json(cursor.fetchall())
                    )
                evidence[name] = {
                    "count": count,
                    "checksum": checksum,
                    "primary_key_sha256": pk_hash,
                }
    finally:
        connection.close()
    return evidence


def _normalize_database_qualifiers(
    value: Any, databases: Iterable[str]
) -> str:
    text = str(value or "")
    for database in databases:
        qualified = re.compile(
            rf"(?i)(?:`{re.escape(database)}`|{re.escape(database)})\."
        )
        text = qualified.sub("<database>.", text)
    return text


def _restored_schema_program_evidence(
    snapshot: Mapping[str, Any],
    database: str,
    equivalent_databases: Iterable[str] = (),
) -> dict[str, Any]:
    database_names = (database, *tuple(equivalent_databases))
    triggers = [
        {
            "trigger_name": row["trigger_name"],
            "event_manipulation": row["event_manipulation"],
            "event_object_table": row["event_object_table"],
            "action_timing": row["action_timing"],
            "action_statement": _normalize_database_qualifiers(
                row["action_statement"], database_names
            ),
        }
        for row in snapshot["triggers"]
    ]
    views = [
        {
            "table_name": row["table_name"],
            "view_definition": _normalize_database_qualifiers(
                row["view_definition"], database_names
            ),
        }
        for row in snapshot["views"]
    ]
    payload = {"triggers": triggers, "views": views}
    return {
        **payload,
        "sha256": _sha256_bytes(_canonical_json(payload)),
    }


def _system_alert_projection_state(snapshot: Mapping[str, Any]) -> str:
    rows = [
        row for row in snapshot["columns"]
        if row["table_name"] == "system_alerts"
    ]
    if not rows:
        return "drift"
    columns = {row["column_name"]: row for row in rows}
    names = set(columns)
    legacy_names = {
        "id", "event_type", "description", "status", "created_at",
        "resolved_at", "resolved_by",
    }
    current_names = {
        "id", "alert_code", "source_domain", "case_key", "reason", "details",
        "status", "claimed_by", "claimed_at", "resolved_by", "resolved_at",
        "resolution_reason", "created_at", "updated_at",
    }
    if names == legacy_names:
        expected = {
            "id": ("int", "NO"),
            "event_type": ("varchar(50)", "NO"),
            "description": ("text", "NO"),
            "status": ("enum('pending','resolved')", "YES"),
            "created_at": ("timestamp", "YES"),
            "resolved_at": ("timestamp", "YES"),
            "resolved_by": ("varchar(50)", "YES"),
        }
        return (
            "absent"
            if all(
                str(columns[name]["column_type"]).casefold() == column_type
                and columns[name]["is_nullable"] == nullable
                for name, (column_type, nullable) in expected.items()
            )
            else "drift"
        )
    if not (
        names == current_names
        or names == current_names | {"event_type", "description"}
    ):
        # Migration 107 adds all projection columns in one ALTER statement.
        # A proper subset is therefore not a resumable statement boundary.
        return "drift"
    transitional_with_legacy = (
        names == current_names | {"event_type", "description"}
    )
    expected = {
        "id": ("int", "NO"),
        "alert_code": ("varchar(50)", "NO"),
        "source_domain": ("varchar(50)", "NO"),
        "case_key": ("varchar(100)", "NO"),
        "reason": ("varchar(500)", "NO"),
        "details": ("json", "NO"),
        "status": ("enum('open','claimed','resolved')", "NO"),
        "claimed_by": ("varchar(100)", "YES"),
        "claimed_at": ("datetime", "YES"),
        "resolved_by": ("varchar(100)", "YES"),
        "resolved_at": ("datetime", "YES"),
        "resolution_reason": ("varchar(500)", "YES"),
        "created_at": ("timestamp", "YES"),
        "updated_at": ("timestamp", "YES"),
    }
    for name, (column_type, nullable) in expected.items():
        actual_type = str(columns[name]["column_type"]).casefold()
        actual_nullable = columns[name]["is_nullable"]
        if transitional_with_legacy and name == "status":
            allowed_status = {
                "enum('pending','resolved')",
                "enum('pending','open','claimed','resolved')",
                "enum('open','claimed','resolved')",
            }
            if actual_type not in allowed_status:
                return "drift"
            if actual_nullable not in {"YES", "NO"}:
                return "drift"
            continue
        if transitional_with_legacy and name == "resolved_by":
            if actual_type not in {"varchar(50)", "varchar(100)"}:
                return "drift"
            if actual_nullable != "YES":
                return "drift"
            continue
        if transitional_with_legacy and name == "resolved_at":
            if actual_type not in {"timestamp", "datetime"}:
                return "drift"
            if actual_nullable != "YES":
                return "drift"
            continue
        if actual_type != column_type:
            return "drift"
        if (
            transitional_with_legacy
            and name in {
                "alert_code", "source_domain", "case_key", "reason",
                "details",
            }
        ):
            if actual_nullable not in {"YES", "NO"}:
                return "drift"
        elif actual_nullable != nullable:
            return "drift"
    if transitional_with_legacy:
        for name in (
            "alert_code", "source_domain", "case_key", "reason", "details",
            "claimed_by", "claimed_at", "resolution_reason",
        ):
            if columns[name]["column_default"] is not None:
                return "drift"
        status_default = columns["status"]["column_default"]
        if status_default not in {"pending", "open"}:
            return "drift"
        if "on update current_timestamp" not in str(
            columns["updated_at"]["extra"]
        ).casefold():
            return "drift"
        final_columns = (
            all(
                columns[name]["is_nullable"] == "NO"
                for name in {
                    "alert_code", "source_domain", "case_key", "reason",
                    "details", "status",
                }
            )
            and columns["status"]["column_type"].casefold()
            == "enum('open','claimed','resolved')"
            and status_default == "open"
            and columns["event_type"]["is_nullable"] == "YES"
            and columns["description"]["is_nullable"] == "YES"
            and columns["resolved_by"]["column_type"].casefold()
            == "varchar(100)"
            and columns["resolved_at"]["column_type"].casefold()
            == "datetime"
        )
        if not final_columns:
            return "partial"
    if (
        columns["status"]["column_default"] != "open"
        or "on update current_timestamp" not in str(
            columns["updated_at"]["extra"]
        ).casefold()
    ):
        return "drift"
    for name in {"event_type", "description"} & names:
        if columns[name]["is_nullable"] != "YES":
            return "drift"
    indexes = {
        row["index_name"]: (
            int(row["non_unique"]), str(row["columns"]).casefold()
        )
        for row in snapshot["indexes"]
        if row["table_name"] == "system_alerts"
    }
    unique_identity = indexes.get("uq_alert_case")
    status_index = indexes.get("idx_system_alert_status")
    if (
        unique_identity is not None
        and unique_identity != (0, "alert_code,case_key")
    ):
        return "drift"
    if status_index is not None and status_index != (1, "status"):
        return "drift"
    if (
        transitional_with_legacy
        and (unique_identity is None or status_index is None)
    ):
        return "partial"
    if unique_identity is None or status_index is None:
        return "drift"
    return "exact"


def _matching_records_resume_delivery_state(
    snapshot: Mapping[str, Any],
) -> str:
    rows = [
        row for row in snapshot["columns"]
        if row["table_name"] == "matching_records"
    ]
    if not rows:
        return "drift"
    columns = {row["column_name"]: row for row in rows}
    required = {
        "id", "case_no", "staff_id", "caregiver_accepted",
        "sent_at", "replied_at", "sent_info_1_at", "sent_info_2_at",
    }
    missing = required - set(columns)
    if missing:
        return "partial" if required.intersection(columns) else "drift"
    column = columns.get("sent_resume_at")
    if column is None:
        return "absent"
    if (
        str(column["column_type"]).casefold() == "datetime"
        and column["is_nullable"] == "YES"
        and column["column_default"] is None
        and str(column["extra"] or "") == ""
        and str(column.get("generation_expression") or "") == ""
    ):
        return "exact"
    return "drift"


def _owned_classification(snapshot: Mapping[str, Any]) -> dict[str, str]:
    present_columns: dict[str, set[str]] = {}
    for row in snapshot["columns"]:
        present_columns.setdefault(row["table_name"], set()).add(
            row["column_name"]
        )
    present_triggers = {row["trigger_name"] for row in snapshot["triggers"]}
    result: dict[str, str] = {}
    for part, expected in OWNED_OBJECTS.items():
        if part == "107_system_alert_current_projection.sql":
            result[part] = _system_alert_projection_state(snapshot)
            continue
        if part == "108_matching_records_resume_delivery.sql":
            result[part] = _matching_records_resume_delivery_state(snapshot)
            continue
        if part in {
            "61_finance_import_reprocessing.sql",
            "104_order_lifecycle_state_history.sql",
            "105_order_service_time_terms.sql",
            "106_order_lifecycle_control_facts.sql",
        }:
            result[part] = _canonical_artifact_metadata_state(
                snapshot, part
            )
            continue
        table_states = []
        for table, columns in expected["tables"].items():
            actual = present_columns.get(table)
            if actual is None:
                table_states.append("absent")
            elif columns.issubset(actual):
                table_states.append("exact")
            elif not columns.intersection(actual):
                table_states.append("absent")
            else:
                table_states.append("partial")
        trigger_states = [
            "exact" if trigger in present_triggers else "absent"
            for trigger in expected["triggers"]
        ]
        states = table_states + trigger_states
        if states and all(state == "absent" for state in states):
            result[part] = "absent"
        elif states and all(state == "exact" for state in states):
            result[part] = "exact"
        elif "drift" in states:
            result[part] = "drift"
        else:
            result[part] = "partial"
    return result


def schema_artifacts() -> list[dict[str, Any]]:
    artifacts = []
    for path in SCHEMA_PARTS:
        raw = path.read_bytes()
        raw.decode("utf-8")
        artifacts.append(
            {
                "name": path.name,
                "path": str(path),
                "size": len(raw),
                "sha256": _sha256_bytes(raw),
            }
        )
    return artifacts


def build_plan(
    config: DatabaseConfig, source: str, candidate: str
) -> dict[str, Any]:
    validate_database_names(source, candidate)
    source_identity = server_identity(config, source)
    source_snapshot = _schema_snapshot(config, source)
    source_objects = _owned_classification(source_snapshot)
    if any(state in {"partial", "drift"} for state in source_objects.values()):
        raise UpgradeBlocked(
            f"source contains partial/drift owned objects: {source_objects}"
        )
    candidate_exists = database_exists(config, candidate)
    source_data = _table_evidence(config, source)
    candidate_data = (
        _table_evidence(config, candidate) if candidate_exists else None
    )
    candidate_matches_source = (
        _candidate_preserves_source_data(source_data, candidate_data)
        if candidate_exists and candidate_data is not None
        else None
    )
    plan = {
        "contract": "preserved-database-additive-upgrade/v1",
        "created_at": _now(),
        "release_id": RELEASE_MANIFEST.release_id,
        "release_fingerprint": RELEASE_MANIFEST.fingerprint,
        "source": source_identity,
        "candidate_database": candidate,
        "candidate_exists": candidate_exists,
        "candidate_precondition": "source_data_must_match_before_apply",
        "candidate_matches_source": candidate_matches_source,
        "schema_artifacts": schema_artifacts(),
        "source_schema_sha256": source_snapshot["sha256"],
        "source_objects": source_objects,
        "source_data": source_data,
        "phase_order": [path.name for path in SCHEMA_PARTS],
        "status": (
            "blocked"
            if candidate_exists and not candidate_matches_source
            else "ready"
        ),
    }
    plan["plan_fingerprint"] = _sha256_bytes(_canonical_json(plan))
    return plan


def _candidate_preserves_source_data(
    source_data: Mapping[str, Any],
    candidate_data: Mapping[str, Any],
) -> bool:
    for table, expected in source_data.items():
        if candidate_data.get(table) != expected:
            return False
    return True


def _validate_plan_integrity(
    plan: Mapping[str, Any], fresh: Mapping[str, Any]
) -> None:
    fingerprint_payload = dict(plan)
    recorded_fingerprint = fingerprint_payload.pop("plan_fingerprint", None)
    if not isinstance(recorded_fingerprint, str) or (
        _sha256_bytes(_canonical_json(fingerprint_payload))
        != recorded_fingerprint
    ):
        raise UpgradeBlocked("plan fingerprint is invalid")
    for key in (
        "release_id",
        "release_fingerprint",
        "schema_artifacts",
        "phase_order",
    ):
        if plan.get(key) != fresh.get(key):
            raise UpgradeBlocked(f"plan artifact changed after planning: {key}")
    if plan.get("candidate_database") != fresh.get("candidate_database"):
        raise UpgradeBlocked("plan candidate identity mismatch")
    planned_source = plan.get("source") or {}
    fresh_source = fresh.get("source") or {}
    for key in ("database", "server", "host", "port"):
        if planned_source.get(key) != fresh_source.get(key):
            raise UpgradeBlocked(f"plan source identity mismatch: {key}")


def validate_dump(
    dump_path: Path, receipt_path: Path, source: str, identity: Mapping[str, Any]
) -> dict[str, Any]:
    path = dump_path.expanduser().resolve()
    if not path.is_file() or path.stat().st_size <= 0:
        raise UpgradeBlocked("source dump is missing or empty")
    head = path.read_bytes()[: 1024 * 1024]
    if MYSQL_DUMP_MARKER not in head:
        raise UpgradeBlocked("source backup is not a mysqldump artifact")
    markers = (
        f"Database: {source}".encode("utf-8"),
        f"Current Database: `{source}`".encode("utf-8"),
    )
    if not any(marker in head for marker in markers):
        raise UpgradeBlocked("source backup does not identify source database")
    receipt = read_receipt(receipt_path)
    expected = {
        "database": source,
        "server": identity["server"],
        "sha256": _sha256_file(path),
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise UpgradeBlocked(f"source backup receipt mismatch: {key}")
    return {"path": str(path), "size": path.stat().st_size, **expected}


def _client_environment(config: DatabaseConfig) -> dict[str, str]:
    environment = os.environ.copy()
    environment["MYSQL_PWD"] = config.password
    return environment


def _mysql_base(
    config: DatabaseConfig,
    executable: str,
    *,
    container: str | None = None,
) -> list[str]:
    prefix = [executable]
    host = config.host
    port = config.port
    if container:
        if not IDENTIFIER.fullmatch(container.replace("-", "_")):
            raise UpgradeBlocked("invalid mysql container name")
        prefix = [
            "docker", "exec", "-i", "-e", "MYSQL_PWD",
            container, executable,
        ]
        host = "127.0.0.1"
        port = 3306
    return prefix + [
        "--host", host, "--port", str(port),
        "--user", config.user, "--default-character-set=utf8mb4",
    ]


def create_source_dump(
    config: DatabaseConfig,
    source: str,
    dump_path: Path,
    receipt_path: Path,
    *,
    mysqldump: str = "mysqldump",
    mysql_container: str | None = None,
) -> dict[str, Any]:
    identity = server_identity(config, source)
    target = dump_path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    command = _mysql_base(
        config, mysqldump, container=mysql_container
    ) + [
        "--single-transaction", "--routines", "--events", "--triggers",
        "--hex-blob", source,
    ]
    with target.open("wb") as output:
        completed = subprocess.run(
            command, stdout=output, stderr=subprocess.PIPE,
            env=_client_environment(config), check=False,
        )
    if completed.returncode != 0 or target.stat().st_size <= 0:
        raise UpgradeBlocked("mysqldump failed or produced an empty artifact")
    receipt = {
        "kind": "source_backup",
        "created_at": _now(),
        "database": source,
        "server": identity["server"],
        "sha256": _sha256_file(target),
        "size": target.stat().st_size,
        "exit_code": completed.returncode,
    }
    write_receipt(receipt_path, receipt)
    return receipt


def restore_candidate(
    config: DatabaseConfig,
    source: str,
    candidate: str,
    dump_path: Path,
    backup_receipt_path: Path,
    operation_receipt_path: Path,
    *,
    mysql: str = "mysql",
    mysql_container: str | None = None,
) -> dict[str, Any]:
    validate_database_names(source, candidate)
    if database_exists(config, candidate):
        raise UpgradeBlocked("candidate must not exist before restore")
    identity = server_identity(config, source)
    dump = validate_dump(dump_path, backup_receipt_path, source, identity)
    prepared = {
        "kind": "preserved_database_upgrade",
        "status": "prepared",
        "phase": "restore",
        "created_at": _now(),
        "source": identity,
        "candidate_database": candidate,
        "source_dump": dump,
    }
    write_receipt(operation_receipt_path, prepared)
    connection = config.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{candidate}` CHARACTER SET utf8mb4")
    finally:
        connection.close()
    command = _mysql_base(
        config, mysql, container=mysql_container
    ) + [candidate]
    with dump_path.expanduser().resolve().open("rb") as source_handle:
        completed = subprocess.run(
            command, stdin=source_handle, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=_client_environment(config), check=False,
        )
    if completed.returncode != 0:
        prepared.update(
            status="partial", failed_phase="restore",
            mysql_exit_code=completed.returncode,
        )
        write_receipt(operation_receipt_path, prepared)
        raise UpgradeBlocked("mysql restore failed; candidate retained")
    source_data = _table_evidence(config, source)
    candidate_data = _table_evidence(config, candidate)
    if source_data != candidate_data:
        prepared.update(status="partial", failed_phase="restore_validation")
        write_receipt(operation_receipt_path, prepared)
        raise UpgradeBlocked("restored candidate differs from source")
    source_programs = _restored_schema_program_evidence(
        _schema_snapshot(config, source), source
    )
    candidate_programs = _restored_schema_program_evidence(
        _schema_snapshot(config, candidate), candidate, (source,)
    )
    if source_programs != candidate_programs:
        prepared.update(
            status="partial", failed_phase="restore_program_validation"
        )
        write_receipt(operation_receipt_path, prepared)
        raise UpgradeBlocked(
            "restored candidate triggers/views differ from source"
        )
    prepared.update(
        status="restored", restored_at=_now(),
        candidate=server_identity(config, candidate),
        restored_data=candidate_data,
        restored_programs=candidate_programs,
    )
    write_receipt(operation_receipt_path, prepared)
    return prepared


def split_sql(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        if quote:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            current.append(char)
        elif char == "-" and next_char == "-" and (
            index + 2 == len(sql) or sql[index + 2].isspace()
        ):
            while index < len(sql) and sql[index] not in "\r\n":
                index += 1
            current.append("\n")
            continue
        elif char == "#":
            while index < len(sql) and sql[index] not in "\r\n":
                index += 1
            current.append("\n")
            continue
        elif char == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
        index += 1
    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements


def _split_top_level(value: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    escaped = False
    for char in value:
        if quote:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
            current.append(char)
        elif char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
        else:
            current.append(char)
    trailing = "".join(current).strip()
    if trailing:
        parts.append(trailing)
    return parts


def _sql_without_unsafe_rendering_differences(value: Any) -> str:
    text = str(value or "")
    text = re.sub(
        r"(?i)_(?:utf8mb4|utf8mb3|utf8|latin1|ascii|binary)"
        r"(?=\\?['\"])",
        "",
        text,
    )
    text = text.replace("\\'", "'").replace('\\"', '"')
    text = re.sub(
        r"(?i)(`?[A-Za-z0-9_]+`?)\s+REGEXP\s+"
        r"('(?:''|[^'])*')",
        r"regexp_like(\1,\2)",
        text,
    )
    normalized: list[str] = []
    quote: str | None = None
    escaped = False
    pending_space = False
    for char in text:
        if quote:
            normalized.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            if pending_space and normalized:
                normalized.append(" ")
            pending_space = False
            quote = char
            normalized.append(char)
        elif char == "`":
            continue
        elif char.isspace():
            pending_space = True
        else:
            if pending_space and normalized:
                normalized.append(" ")
            pending_space = False
            normalized.append(char.casefold())
    return "".join(normalized).strip()


def _strip_outer_sql_parentheses(value: str) -> str:
    result = value.strip()
    while result.startswith("(") and result.endswith(")"):
        try:
            _, closing = _extract_parenthesized(result, 0)
        except UpgradeBlocked:
            break
        if closing != len(result) - 1:
            break
        result = result[1:-1]
    return result


def _split_top_level_boolean(
    value: str, keyword: str
) -> list[str] | None:
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    index = 0
    lowered = value.casefold()
    target = keyword.casefold()
    while index < len(value):
        char = value[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char == "(":
            depth += 1
            index += 1
            continue
        if char == ")":
            depth -= 1
            index += 1
            continue
        if depth == 0 and lowered.startswith(target, index):
            before = value[index - 1] if index else " "
            after_index = index + len(target)
            after = value[after_index] if after_index < len(value) else " "
            if (
                not (before.isalnum() or before == "_")
                and not (after.isalnum() or after == "_")
            ):
                parts.append(value[start:index].strip())
                start = after_index
                index = after_index
                continue
        index += 1
    if not parts:
        return None
    parts.append(value[start:].strip())
    return parts


def _compact_sql_atom(value: str) -> str:
    compact: list[str] = []
    quote: str | None = None
    escaped = False
    for char in value:
        if quote:
            compact.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in {"'", '"'}:
            quote = char
            compact.append(char)
        elif not char.isspace():
            compact.append(char)
    return "".join(compact)


def _boolean_contract_tree(value: str) -> tuple[str, Any]:
    expression = _strip_outer_sql_parentheses(value)
    for keyword in ("or", "and"):
        parts = _split_top_level_boolean(expression, keyword)
        if parts:
            return (
                keyword,
                tuple(_boolean_contract_tree(part) for part in parts),
            )
    unary_not = re.match(r"^not\b(.*)$", expression, re.I | re.S)
    if unary_not:
        return _negate_boolean_contract_tree(
            _boolean_contract_tree(unary_not.group(1))
        )
    return ("atom", _compact_sql_atom(expression))


def _negate_boolean_contract_tree(
    node: tuple[str, Any],
) -> tuple[str, Any]:
    operator, payload = node
    if operator == "and":
        return (
            "or",
            tuple(
                _negate_boolean_contract_tree(child) for child in payload
            ),
        )
    if operator == "or":
        return (
            "and",
            tuple(
                _negate_boolean_contract_tree(child) for child in payload
            ),
        )
    if operator == "not":
        return payload
    return ("not", node)


def _render_boolean_contract_tree(node: tuple[str, Any]) -> str:
    operator, payload = node
    if operator == "atom":
        return f"atom({payload})"
    if operator == "not":
        return f"not({_render_boolean_contract_tree(payload)})"
    return (
        f"{operator}("
        + ",".join(
            _render_boolean_contract_tree(child) for child in payload
        )
        + ")"
    )


def _canonical_boolean_contract(value: str) -> str:
    return _render_boolean_contract_tree(_boolean_contract_tree(value))


def _normalize_sql_contract(value: Any) -> str:
    lexical = _sql_without_unsafe_rendering_differences(value)
    lexical = re.sub(
        r"\(\s*([A-Za-z0-9_]+\s*[+\-*/]\s*[A-Za-z0-9_]+)\s*\)"
        r"\s*(<=|>=|<>|!=|=|<|>)",
        r"\1\2",
        lexical,
    )
    return _canonical_boolean_contract(lexical)


def _extract_parenthesized(value: str, opening: int) -> tuple[str, int]:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(opening, len(value)):
        char = value[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return value[opening + 1:index], index
    raise UpgradeBlocked("canonical schema artifact has unbalanced parentheses")


def _parse_column_definition(definition: str) -> tuple[str, dict[str, Any]]:
    match = re.match(r"^`?([A-Za-z0-9_]+)`?\s+(.+)$", definition, re.S)
    if not match:
        raise UpgradeBlocked("canonical column definition is invalid")
    name, remainder = match.groups()
    type_match = re.match(
        r"^([A-Za-z]+(?:\s+UNSIGNED)?(?:\([^)]*\))?"
        r"(?:\s+UNSIGNED)?)(?=\s|$)",
        remainder,
        re.I | re.S,
    )
    if not type_match:
        raise UpgradeBlocked(f"canonical column type is invalid: {name}")
    column_type = _normalize_column_type_contract(type_match.group(1))
    upper = remainder.upper()
    nullable = "NO" if (
        "NOT NULL" in upper or "PRIMARY KEY" in upper
    ) else "YES"
    default_match = re.search(
        r"\bDEFAULT\s+("
        r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|"
        r"[A-Za-z_]+(?:\(\d*\))?|[-+]?\d+(?:\.\d+)?"
        r")",
        remainder,
        re.I,
    )
    default: Any = None
    if default_match:
        token = default_match.group(1)
        if token.upper() != "NULL":
            default = token.strip("'\"").casefold()
    extra_parts: list[str] = []
    if (
        default is not None
        and re.fullmatch(r"current_timestamp(?:\(\d*\))?", default)
    ):
        extra_parts.append("default_generated")
    if "AUTO_INCREMENT" in upper:
        extra_parts.append("auto_increment")
    update_match = re.search(
        r"\bON\s+UPDATE\s+([A-Za-z_]+(?:\(\d*\))?)",
        remainder,
        re.I,
    )
    if update_match:
        extra_parts.append(
            "on update " + update_match.group(1).casefold()
        )
    return name, {
        "column_type": column_type,
        "is_nullable": nullable,
        "column_default": default,
        "extra": " ".join(extra_parts),
    }


def _normalize_column_type_contract(value: Any) -> str:
    normalized: list[str] = []
    quote: str | None = None
    escaped = False
    pending_space = False
    for char in str(value or ""):
        if quote:
            normalized.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            if pending_space and normalized and normalized[-1] not in "(,":
                normalized.append(" ")
            pending_space = False
            quote = char
            normalized.append(char)
        elif char.isspace():
            pending_space = True
        elif char in "(),":
            while normalized and normalized[-1] == " ":
                normalized.pop()
            normalized.append(char)
            pending_space = False
        else:
            if pending_space and normalized and normalized[-1] not in "(,":
                normalized.append(" ")
            pending_space = False
            normalized.append(char.casefold())
    return "".join(normalized).strip()


def _parse_index_columns(value: str) -> tuple[str, ...]:
    return tuple(
        re.sub(r"\s+(?:ASC|DESC)\b", "", item, flags=re.I)
        .strip()
        .strip("`")
        .casefold()
        for item in _split_top_level(value)
    )


def _canonical_artifact_descriptor(part_name: str) -> dict[str, Any]:
    path = next(
        (path for path in SCHEMA_PARTS if path.name == part_name),
        None,
    )
    if path is None:
        raise UpgradeBlocked(f"canonical schema part is missing: {part_name}")
    sql = path.read_text(encoding="utf-8")
    descriptor: dict[str, Any] = {
        "tables": {},
        "indexes": {},
        "foreign_keys": {},
        "checks": {},
        "triggers": {},
        "parent_columns": {},
    }
    create_pattern = re.compile(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+`?([A-Za-z0-9_]+)`?\s*\(",
        re.I,
    )
    for match in create_pattern.finditer(sql):
        table = match.group(1)
        body, _ = _extract_parenthesized(sql, match.end() - 1)
        columns: dict[str, Any] = {}
        for definition in _split_top_level(body):
            normalized = definition.strip()
            upper = normalized.upper()
            if upper.startswith(("PRIMARY KEY", "UNIQUE KEY", "INDEX ", "KEY ")):
                index_match = re.match(
                    r"^(PRIMARY\s+KEY|UNIQUE\s+KEY|INDEX|KEY)"
                    r"(?:\s+`?([A-Za-z0-9_]+)`?)?\s*\(",
                    normalized,
                    re.I,
                )
                if not index_match:
                    raise UpgradeBlocked("canonical index definition is invalid")
                inside, _ = _extract_parenthesized(
                    normalized, index_match.end() - 1
                )
                kind = re.sub(
                    r"\s+", " ", index_match.group(1)
                ).upper()
                name = (
                    "PRIMARY"
                    if kind == "PRIMARY KEY"
                    else str(index_match.group(2))
                )
                descriptor["indexes"][(table, name)] = {
                    "non_unique": 0 if kind in {
                        "PRIMARY KEY", "UNIQUE KEY"
                    } else 1,
                    "columns": _parse_index_columns(inside),
                }
                continue
            if upper.startswith("CONSTRAINT "):
                constraint_match = re.match(
                    r"^CONSTRAINT\s+`?([A-Za-z0-9_]+)`?\s+(.+)$",
                    normalized,
                    re.I | re.S,
                )
                if not constraint_match:
                    raise UpgradeBlocked(
                        "canonical constraint definition is invalid"
                    )
                name, contract = constraint_match.groups()
                if re.match(r"^FOREIGN\s+KEY", contract, re.I):
                    local_open = contract.index("(")
                    local, local_end = _extract_parenthesized(
                        contract, local_open
                    )
                    reference = re.search(
                        r"REFERENCES\s+`?([A-Za-z0-9_]+)`?\s*\(",
                        contract[local_end + 1:],
                        re.I,
                    )
                    if not reference:
                        raise UpgradeBlocked(
                            "canonical foreign key reference is invalid"
                        )
                    reference_offset = local_end + 1 + reference.end() - 1
                    remote, _ = _extract_parenthesized(
                        contract, reference_offset
                    )
                    update = re.search(
                        r"ON\s+UPDATE\s+(RESTRICT|CASCADE|SET\s+NULL|NO\s+ACTION)",
                        contract,
                        re.I,
                    )
                    delete = re.search(
                        r"ON\s+DELETE\s+(RESTRICT|CASCADE|SET\s+NULL|NO\s+ACTION)",
                        contract,
                        re.I,
                    )
                    descriptor["foreign_keys"][(table, name)] = {
                        "columns": _parse_index_columns(local),
                        "referenced_table": reference.group(1).casefold(),
                        "referenced_columns": _parse_index_columns(remote),
                        "update_rule": (
                            re.sub(r"\s+", " ", update.group(1)).upper()
                            if update else "RESTRICT"
                        ),
                        "delete_rule": (
                            re.sub(r"\s+", " ", delete.group(1)).upper()
                            if delete else "RESTRICT"
                        ),
                    }
                elif re.match(r"^CHECK\s*\(", contract, re.I):
                    opening = contract.index("(")
                    clause, _ = _extract_parenthesized(contract, opening)
                    descriptor["checks"][(table, name)] = (
                        _normalize_sql_contract(clause)
                    )
                continue
            name, column = _parse_column_definition(normalized)
            columns[name] = column
            if "PRIMARY KEY" in upper:
                descriptor["indexes"][(table, "PRIMARY")] = {
                    "non_unique": 0,
                    "columns": (name.casefold(),),
                }
        descriptor["tables"][table] = columns
    trigger_pattern = re.compile(
        r"CREATE\s+TRIGGER\s+`?([A-Za-z0-9_]+)`?\s+"
        r"(BEFORE|AFTER)\s+(INSERT|UPDATE|DELETE)\s+ON\s+"
        r"`?([A-Za-z0-9_]+)`?\s+FOR\s+EACH\s+ROW\s+(.+?)(?=;\s*(?:$|\n))",
        re.I | re.S,
    )
    for match in trigger_pattern.finditer(sql + "\n"):
        name, timing, event, table, body = match.groups()
        descriptor["triggers"][name] = {
            "action_timing": timing.upper(),
            "event_manipulation": event.upper(),
            "event_object_table": table,
            "action_statement": _normalize_sql_contract(body),
        }
    if part_name == "105_order_service_time_terms.sql":
        descriptor["parent_columns"]["orders"] = {
            "service_start_time": {
                "column_type": "time",
                "is_nullable": "YES",
                "column_default": None,
                "extra": "",
            },
            "service_end_time": {
                "column_type": "time",
                "is_nullable": "YES",
                "column_default": None,
                "extra": "",
            },
            "service_end_day_offset": {
                "column_type": "tinyint unsigned",
                "is_nullable": "YES",
                "column_default": None,
                "extra": "",
            },
        }
        descriptor["checks"].update(
            {
                ("orders", "chk_orders_service_time_terms_complete"):
                    _normalize_sql_contract(
                        "((service_start_time IS NULL AND "
                        "service_end_time IS NULL AND "
                        "service_end_day_offset IS NULL) OR "
                        "(service_start_time IS NOT NULL AND "
                        "service_end_time IS NOT NULL AND "
                        "service_end_day_offset IS NOT NULL))"
                    ),
                ("orders", "chk_orders_service_end_day_offset"):
                    _normalize_sql_contract(
                        "service_end_day_offset IS NULL OR "
                        "service_end_day_offset IN (0,1)"
                    ),
            }
        )
    if part_name == "106_order_lifecycle_control_facts.sql":
        descriptor["parent_columns"]["orders"] = {
            "lifecycle_version": {
                "column_type": "bigint unsigned",
                "is_nullable": "NO",
                "column_default": "0",
                "extra": "",
            }
        }
    if part_name == "61_finance_import_reprocessing.sql":
        descriptor["indexes"][(
            "finance_import_batches",
            "uq_finance_import_batch_id_status",
        )] = {
            "non_unique": 0,
            "columns": ("id", "status"),
        }
    return descriptor


def _show_create_check_clauses(
    create_sql: str,
) -> dict[tuple[str, str], str]:
    create_match = re.search(
        r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+"
        r"`?([A-Za-z0-9_]+)`?\s*\(",
        create_sql,
        re.I,
    )
    if not create_match:
        raise UpgradeBlocked("SHOW CREATE TABLE contract is invalid")
    table = create_match.group(1)
    body, _ = _extract_parenthesized(
        create_sql, create_match.end() - 1
    )
    checks: dict[tuple[str, str], str] = {}
    for definition in _split_top_level(body):
        constraint = re.match(
            r"^CONSTRAINT\s+`?([A-Za-z0-9_]+)`?\s+CHECK\s*\(",
            definition.strip(),
            re.I | re.S,
        )
        if not constraint:
            continue
        clause, _ = _extract_parenthesized(
            definition, constraint.end() - 1
        )
        checks[(table, constraint.group(1))] = clause
    return checks


def _canonical_artifact_metadata_state(
    snapshot: Mapping[str, Any], part_name: str
) -> str:
    descriptor = _canonical_artifact_descriptor(part_name)
    columns_by_table: dict[str, dict[str, Mapping[str, Any]]] = {}
    for row in snapshot["columns"]:
        columns_by_table.setdefault(row["table_name"], {})[
            row["column_name"]
        ] = row
    required_tables = descriptor["tables"]
    parent_columns = descriptor["parent_columns"]
    owned_presence: list[bool] = []
    for table, expected_columns in {
        **required_tables, **parent_columns
    }.items():
        actual = columns_by_table.get(table, {})
        for name, expected in expected_columns.items():
            row = actual.get(name)
            owned_presence.append(row is not None)
            if row is None:
                continue
            actual_default = row["column_default"]
            if isinstance(actual_default, str):
                actual_default = actual_default.casefold()
            actual_extra = re.sub(
                r"\s+", " ", str(row["extra"] or "")
            ).casefold()
            if (
                _normalize_column_type_contract(row["column_type"])
                != expected["column_type"]
                or row["is_nullable"] != expected["is_nullable"]
                or actual_default != expected["column_default"]
                or actual_extra != expected["extra"]
            ):
                return "drift"
        if table in required_tables and actual:
            if set(actual) != set(expected_columns):
                return "drift"
    indexes = {
        (row["table_name"], row["index_name"]): {
            "non_unique": int(row["non_unique"]),
            "columns": tuple(
                item.casefold() for item in str(row["columns"]).split(",")
            ),
        }
        for row in snapshot["indexes"]
    }
    for key, expected in descriptor["indexes"].items():
        actual = indexes.get(key)
        owned_presence.append(actual is not None)
        if actual is not None and actual != expected:
            return "drift"
    constraints = {
        (row["table_name"], row["constraint_name"]): row
        for row in snapshot.get("constraints", [])
    }
    key_columns: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in snapshot.get("key_columns", []):
        key_columns.setdefault(
            (row["table_name"], row["constraint_name"]), []
        ).append(row)
    foreign_rules = {
        (row["table_name"], row["constraint_name"]): row
        for row in snapshot.get("foreign_keys", [])
    }
    show_create_checks: dict[tuple[str, str], str] = {}
    for create_sql in snapshot.get("show_create_tables", {}).values():
        show_create_checks.update(_show_create_check_clauses(create_sql))
    for key, expected in descriptor["foreign_keys"].items():
        row = constraints.get(key)
        owned_presence.append(row is not None)
        if row is None:
            continue
        columns = key_columns.get(key, [])
        rules = foreign_rules.get(key, {})
        actual = {
            "columns": tuple(
                item["column_name"].casefold() for item in columns
            ),
            "referenced_table": str(
                columns[0]["referenced_table_name"] if columns else ""
            ).casefold(),
            "referenced_columns": tuple(
                str(item["referenced_column_name"]).casefold()
                for item in columns
            ),
            "update_rule": str(rules.get("update_rule") or "").upper(),
            "delete_rule": str(rules.get("delete_rule") or "").upper(),
        }
        if row["constraint_type"] != "FOREIGN KEY" or actual != expected:
            return "drift"
    for key, expected_clause in descriptor["checks"].items():
        row = constraints.get(key)
        owned_presence.append(row is not None)
        if row is None:
            continue
        actual_clause = show_create_checks.get(key, row.get("check_clause"))
        if (
            row["constraint_type"] != "CHECK"
            or str(row.get("enforced") or "YES").upper() != "YES"
            or (
                actual_clause != expected_clause
                and _normalize_sql_contract(actual_clause)
                != expected_clause
            )
        ):
            return "drift"
    triggers = {
        row["trigger_name"]: {
            "action_timing": str(row["action_timing"]).upper(),
            "event_manipulation": str(
                row["event_manipulation"]
            ).upper(),
            "event_object_table": row["event_object_table"],
            "action_statement": (
                row["action_statement"]
                if row["action_statement"]
                in {
                    item["action_statement"]
                    for item in descriptor["triggers"].values()
                }
                else _normalize_sql_contract(row["action_statement"])
            ),
        }
        for row in snapshot["triggers"]
    }
    for name, expected in descriptor["triggers"].items():
        actual = triggers.get(name)
        owned_presence.append(actual is not None)
        if actual is not None and actual != expected:
            return "drift"
    if not owned_presence or not any(owned_presence):
        return "absent"
    if not all(owned_presence):
        return "partial"
    return "exact"


def apply_schema(
    config: DatabaseConfig,
    source: str,
    candidate: str,
    plan_path: Path,
    operation_receipt_path: Path,
    *,
    mysql_container: str | None = None,
) -> dict[str, Any]:
    validate_database_names(source, candidate)
    operation_receipt = read_receipt(operation_receipt_path)
    if operation_receipt.get("status") == "schema_applied":
        if operation_receipt.get("candidate_database") != candidate:
            raise UpgradeBlocked("operation receipt targets another candidate")
        return run_candidate_post_schema(
            config,
            source,
            candidate,
            operation_receipt_path,
            mysql_container=mysql_container,
        )
    plan = read_receipt(plan_path)
    if plan.get("status") != "ready":
        raise UpgradeBlocked("plan is not ready")
    fresh = build_plan(config, source, candidate)
    _validate_plan_integrity(plan, fresh)
    if fresh["source_schema_sha256"] != plan.get("source_schema_sha256"):
        raise UpgradeBlocked("source schema changed after planning")
    if fresh["source_data"] != plan.get("source_data"):
        raise UpgradeBlocked("source data changed after planning")
    if not database_exists(config, candidate):
        raise UpgradeBlocked("candidate has not been restored")
    # Preserve compatibility with legacy/minimal operation receipts while
    # enforcing the source-data invariant for receipts produced by the real
    # restore workflow.  The latter always records candidate_data.
    if isinstance(operation_receipt.get("candidate_data"), Mapping):
        candidate_data = _table_evidence(config, candidate)
        if not _candidate_preserves_source_data(
            plan.get("source_data") or {}, candidate_data
        ):
            raise UpgradeBlocked("candidate data does not match restored source")
    candidate_identity = server_identity(config, candidate)
    if candidate_identity["server"] != plan["source"]["server"]:
        raise UpgradeBlocked("candidate is on a different server")
    before = _schema_snapshot(config, candidate)
    states = _owned_classification(before)
    if any(state in {"partial", "drift"} for state in states.values()):
        raise UpgradeBlocked(f"candidate schema is partial/drift: {states}")
    receipt = operation_receipt
    if receipt.get("candidate_database") != candidate:
        raise UpgradeBlocked("operation receipt targets another candidate")
    steps = receipt.setdefault("schema_steps", [])
    connection = config.connect(candidate)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS db")
            if cursor.fetchone()["db"] != candidate:
                raise UpgradeBlocked("mutation connection is not candidate")
            for part in SCHEMA_PARTS:
                statements = split_sql(part.read_text(encoding="utf-8"))
                if states.get(part.name) == "exact":
                    steps.append(
                        {
                            "part": part.name,
                            "index": 0,
                            "status": "exact",
                            "outcome": "existing_part_skipped",
                            "verified_at": _now(),
                        }
                    )
                    write_receipt(operation_receipt_path, receipt)
                    continue
                for index, statement in enumerate(statements, start=1):
                    statement_before = _schema_snapshot(config, candidate)
                    before_state = _owned_classification(
                        statement_before
                    )[part.name]
                    if before_state == "exact":
                        steps.append(
                            {
                                "part": part.name,
                                "index": index,
                                "status": "exact",
                                "outcome": "remaining_part_skipped",
                                "before_schema_sha256": (
                                    statement_before["sha256"]
                                ),
                                "before_part_state": before_state,
                                "verified_at": _now(),
                            }
                        )
                        write_receipt(operation_receipt_path, receipt)
                        break
                    if before_state == "drift":
                        raise UpgradeBlocked(
                            f"candidate schema drift before "
                            f"{part.name}:{index}"
                        )
                    step = {
                        "part": part.name,
                        "index": index,
                        "statement_sha256": _sha256_bytes(
                            statement.encode("utf-8")
                        ),
                        "status": "prepared",
                        "before_schema_sha256": statement_before["sha256"],
                        "before_part_state": before_state,
                        "prepared_at": _now(),
                    }
                    steps.append(step)
                    receipt.update(status="partial", phase="schema_apply")
                    write_receipt(operation_receipt_path, receipt)
                    try:
                        cursor.execute(statement)
                    except Exception as exc:
                        statement_after = _schema_snapshot(config, candidate)
                        after_state = _owned_classification(
                            statement_after
                        )[part.name]
                        step.update(
                            status="failed",
                            error_type=type(exc).__name__,
                            after_schema_sha256=statement_after["sha256"],
                            after_part_state=after_state,
                            failed_at=_now(),
                        )
                        write_receipt(operation_receipt_path, receipt)
                        raise
                    statement_after = _schema_snapshot(config, candidate)
                    after_state = _owned_classification(
                        statement_after
                    )[part.name]
                    if after_state == "drift":
                        step.update(
                            status="failed",
                            verification_status="drift",
                            after_schema_sha256=statement_after["sha256"],
                            after_part_state=after_state,
                            failed_at=_now(),
                        )
                        write_receipt(operation_receipt_path, receipt)
                        raise UpgradeBlocked(
                            f"candidate schema drift after "
                            f"{part.name}:{index}"
                        )
                    step.update(
                        status=(
                            "exact" if after_state == "exact" else "applied"
                        ),
                        verification_status=(
                            "exact"
                            if after_state == "exact"
                            else "pending_part_completion"
                        ),
                        after_schema_sha256=statement_after["sha256"],
                        after_part_state=after_state,
                        verified_at=(
                            _now() if after_state == "exact" else None
                        ),
                        applied_at=_now(),
                    )
                    write_receipt(operation_receipt_path, receipt)
                    if after_state == "exact":
                        break
    finally:
        connection.close()
    after = _schema_snapshot(config, candidate)
    states = _owned_classification(after)
    if any(state != "exact" for state in states.values()):
        receipt.update(status="partial", owned_objects=states)
        write_receipt(operation_receipt_path, receipt)
        raise UpgradeBlocked(f"schema postcheck is not exact: {states}")
    receipt.update(
        status="schema_applied", phase="schema_complete",
        schema_applied_at=_now(), candidate_schema_sha256=after["sha256"],
        owned_objects=states,
    )
    write_receipt(operation_receipt_path, receipt)
    return run_candidate_post_schema(
        config, source, candidate, operation_receipt_path,
        mysql_container=mysql_container,
    )


def _run_project_python(
    arguments: list[str],
    *,
    config: DatabaseConfig,
    database: str,
) -> dict[str, Any]:
    environment = os.environ.copy()
    environment.update(
        {
            "DB_HOST": config.host,
            "DB_PORT": str(config.port),
            "DB_USER": config.user,
            "DB_PASSWORD": config.password,
            "DB_DATABASE": database,
        }
    )
    completed = subprocess.run(
        [sys.executable, *arguments],
        cwd=str(ROOT),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode != 0:
        raise UpgradeBlocked(
            f"candidate migration failed: {Path(arguments[0]).name}"
        )
    last_line = next(
        (
            line for line in reversed(completed.stdout.splitlines())
            if line.strip().startswith("{")
        ),
        "",
    )
    try:
        payload = json.loads(last_line)
    except json.JSONDecodeError:
        payload = {"stdout_sha256": _sha256_bytes(completed.stdout.encode())}
    return {
        "exit_code": completed.returncode,
        "result": payload,
        "stderr_sha256": _sha256_bytes(completed.stderr.encode()),
    }


def _candidate_preddl_dump(
    config: DatabaseConfig,
    candidate: str,
    target: Path,
    *,
    mysqldump: str = "mysqldump",
    mysql_container: str | None = None,
) -> dict[str, Any]:
    command = _mysql_base(
        config, mysqldump, container=mysql_container
    ) + [
        "--single-transaction", "--routines", "--events", "--triggers",
        "--hex-blob", "--databases", candidate,
    ]
    with target.open("wb") as output:
        completed = subprocess.run(
            command, stdout=output, stderr=subprocess.PIPE,
            env=_client_environment(config), check=False,
        )
    if completed.returncode != 0 or not target.is_file() or target.stat().st_size <= 0:
        raise UpgradeBlocked("candidate pre-DDL mysqldump failed")
    return {
        "path": str(target),
        "sha256": _sha256_file(target),
        "size": target.stat().st_size,
    }


def run_candidate_post_schema(
    config: DatabaseConfig,
    source: str,
    candidate: str,
    operation_receipt_path: Path,
    *,
    mysql_container: str | None = None,
) -> dict[str, Any]:
    receipt = read_receipt(operation_receipt_path)
    if receipt.get("status") != "schema_applied":
        raise UpgradeBlocked("post-schema phase requires schema_applied receipt")
    if server_identity(config, candidate)["database"] != candidate:
        raise UpgradeBlocked("post-schema target is not candidate")
    if MANIFEST_DRIVEN_RELEASE:
        if RELEASE_MANIFEST.backfills:
            raise UpgradeBlocked(
                "manifest backfill execution is not supported by this runner"
            )
        receipt.update(
            status="backfilled",
            phase="post_schema_complete",
            backfilled_at=_now(),
            backfills=(),
        )
        write_receipt(operation_receipt_path, receipt)
        return receipt
    artifact_dir = operation_receipt_path.expanduser().resolve().parent
    backup = artifact_dir / f"{candidate}.pre_backfill.sql"
    plan = artifact_dir / f"{candidate}.backfill.plan.json"
    backfill_receipt = artifact_dir / f"{candidate}.backfill.receipt.json"
    candidate_backup = _candidate_preddl_dump(
        config, candidate, backup, mysql_container=mysql_container
    )
    receipt["candidate_pre_backfill_dump"] = candidate_backup
    write_receipt(operation_receipt_path, receipt)
    migration = "scripts/migrate_order_lifecycle_control_facts.py"
    dry = _run_project_python(
        [
            migration, "--dry-run", "--target-database", candidate,
            "--receipt-path", str(plan),
        ],
        config=config,
        database=candidate,
    )
    applied = _run_project_python(
        [
            migration, "--apply", "--target-database", candidate,
            "--backup-receipt", str(backup), "--plan-receipt", str(plan),
            "--receipt-path", str(backfill_receipt),
        ],
        config=config,
        database=candidate,
    )
    verified = _run_project_python(
        [
            migration, "--verify", "--target-database", candidate,
            "--receipt-path", str(backfill_receipt),
        ],
        config=config,
        database=candidate,
    )
    view_migration = "scripts/migrate_order_details_lifecycle_version_view.py"
    view_dry = _run_project_python(
        [view_migration], config=config, database=candidate
    )
    view_apply = _run_project_python(
        [view_migration, "--apply"], config=config, database=candidate
    )
    receipt.update(
        status="backfilled",
        phase="post_schema_complete",
        backfilled_at=_now(),
        backfill={
            "dry_run": dry,
            "apply": applied,
            "verify": verified,
            "plan_sha256": _sha256_file(plan),
            "receipt_sha256": _sha256_file(backfill_receipt),
        },
        view={"dry_run": view_dry, "apply": view_apply},
    )
    write_receipt(operation_receipt_path, receipt)
    return receipt


def _replace_database_setting(raw: bytes, before: str, after: str) -> bytes:
    text = raw.decode("utf-8")
    pattern = re.compile(
        r"(?m)^([ \t]*DB_DATABASE[ \t]*=[ \t]*)([^\r\n]*)(\r?)$"
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise UpgradeBlocked("environment must contain exactly one DB_DATABASE")
    value = matches[0].group(2)
    parsed = re.fullmatch(
        r"([ \t]*)(?:(['\"])([A-Za-z0-9_]+)\2|([A-Za-z0-9_]+))"
        r"([ \t]*)",
        value,
    )
    if parsed is None:
        raise UpgradeBlocked("environment DB_DATABASE format is unsupported")
    current = parsed.group(3) or parsed.group(4)
    if current != before:
        raise UpgradeBlocked("environment DB_DATABASE is stale")
    quote = parsed.group(2) or ""
    replacement_value = (
        f"{parsed.group(1)}{quote}{after}{quote}{parsed.group(5)}"
    )
    replacement = (
        f"{matches[0].group(1)}{replacement_value}{matches[0].group(3)}"
    )
    updated = text[: matches[0].start()] + replacement + text[matches[0].end():]
    return updated.encode("utf-8")


def switch_environment(
    environment_file: Path,
    source: str,
    candidate: str,
    verified_receipt_path: Path,
    switch_receipt_path: Path,
) -> dict[str, Any]:
    verified = read_receipt(verified_receipt_path)
    if verified.get("status") != "verified":
        raise UpgradeBlocked("candidate is not verified")
    source_identity = verified.get("source") or {}
    candidate_identity = verified.get("candidate") or {}
    if (
        verified.get("candidate_database") != candidate
        or source_identity.get("database") != source
        or candidate_identity.get("database") != candidate
        or source_identity.get("server") != candidate_identity.get("server")
    ):
        raise UpgradeBlocked("verified receipt database identity mismatch")
    raw, environment = _read_env_bytes(environment_file)
    try:
        environment_port = int(environment.get("DB_PORT", "3306"))
        verified_port = int(source_identity.get("port"))
    except (TypeError, ValueError) as exc:
        raise UpgradeBlocked(
            "verified environment port identity is invalid"
        ) from exc
    if (
        environment.get("DB_HOST", "127.0.0.1")
        != str(source_identity.get("host"))
        or environment_port != verified_port
    ):
        raise UpgradeBlocked("environment connection identity is stale")
    config, configured_source = config_from_env(environment_file)
    if configured_source != source:
        raise UpgradeBlocked("environment source database is stale")
    current_source_identity = server_identity(config, source)
    current_candidate_identity = server_identity(config, candidate)
    if (
        current_source_identity.get("server") != source_identity.get("server")
        or current_candidate_identity.get("server")
        != candidate_identity.get("server")
    ):
        raise UpgradeBlocked("verified server identity is stale")
    if _table_evidence(config, source) != verified.get("source_data"):
        raise UpgradeBlocked("verified source data fingerprint is stale")
    if _table_evidence(config, candidate) != verified.get("candidate_data"):
        raise UpgradeBlocked("verified candidate data fingerprint is stale")
    updated = _replace_database_setting(raw, source, candidate)
    receipt = {
        "kind": "database_switch",
        "status": "prepared",
        "created_at": _now(),
        "environment_file": str(environment_file.expanduser().resolve()),
        "source_database": source,
        "candidate_database": candidate,
        "before_sha256": _sha256_bytes(raw),
        "after_sha256": _sha256_bytes(updated),
        "verified_receipt_sha256": _sha256_file(verified_receipt_path),
    }
    write_receipt(switch_receipt_path, receipt)
    _atomic_write(environment_file, updated)
    receipt.update(status="switched", switched_at=_now())
    write_receipt(switch_receipt_path, receipt)
    return receipt


def rollback_environment(
    environment_file: Path, switch_receipt_path: Path
) -> dict[str, Any]:
    receipt = read_receipt(switch_receipt_path)
    if receipt.get("status") != "switched":
        raise UpgradeBlocked("switch receipt is not rollback eligible")
    current = environment_file.expanduser().resolve().read_bytes()
    if _sha256_bytes(current) != receipt.get("after_sha256"):
        raise UpgradeBlocked("environment changed after switch")
    source = str(receipt.get("source_database") or "")
    candidate = str(receipt.get("candidate_database") or "")
    validate_database_names(source, candidate)
    before = _replace_database_setting(current, candidate, source)
    if _sha256_bytes(before) != receipt.get("before_sha256"):
        raise UpgradeBlocked("environment cannot reconstruct switch baseline")
    _atomic_write(environment_file, before)
    if _sha256_bytes(environment_file.expanduser().resolve().read_bytes()) != (
        receipt.get("before_sha256")
    ):
        raise UpgradeBlocked("environment rollback verification failed")
    receipt.update(status="rolled_back", rolled_back_at=_now())
    write_receipt(switch_receipt_path, receipt)
    return receipt


def _verify_legacy_system_alert_rows(
    config: DatabaseConfig, source: str, candidate: str
) -> dict[str, Any]:
    legacy_fields = (
        "id,event_type,description,status,created_at,resolved_at,resolved_by"
    )
    source_connection = config.connect(source)
    candidate_connection = config.connect(candidate)
    try:
        with source_connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {legacy_fields} FROM system_alerts ORDER BY id"
            )
            source_rows = cursor.fetchall()
        with candidate_connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {legacy_fields},alert_code,source_domain,case_key,"
                "reason,details,claimed_by,claimed_at,resolution_reason "
                "FROM system_alerts ORDER BY id"
            )
            candidate_rows = cursor.fetchall()
    finally:
        source_connection.close()
        candidate_connection.close()
    if len(source_rows) != len(candidate_rows):
        raise UpgradeBlocked("legacy system_alerts row count changed")
    for before, after in zip(source_rows, candidate_rows, strict=True):
        for field in (
            "id", "event_type", "description", "created_at", "resolved_at",
            "resolved_by",
        ):
            if before[field] != after[field]:
                raise UpgradeBlocked(
                    f"legacy system_alerts field changed: {field}"
                )
        expected_status = (
            "open" if before["status"] == "pending" else "resolved"
        )
        event_type = str(before["event_type"]).strip() or "LEGACY"
        description = str(before["description"]).strip()
        expected_reason = description[:500] or "Legacy system alert"
        if (
            after["status"] != expected_status
            or after["alert_code"] != event_type
            or after["source_domain"] != "LEGACY"
            or after["case_key"] != f"legacy-alert:{before['id']}"
            or after["reason"] != expected_reason
        ):
            raise UpgradeBlocked("legacy system_alerts projection mismatch")
        details = after["details"]
        if isinstance(details, str):
            details = json.loads(details)
        if details != {
            "legacy_event_type": event_type,
            "migration": "system_alert_current_projection_v1",
        }:
            raise UpgradeBlocked("legacy system_alerts details mismatch")
    return {
        "mode": "legacy_migrated",
        "row_count": len(source_rows),
        "status_mapping": "pending_to_open_resolved_unchanged",
    }


def _table_projection_evidence(
    config: DatabaseConfig,
    database: str,
    table: str,
    columns: list[str],
) -> dict[str, Any]:
    if (
        not IDENTIFIER.fullmatch(table)
        or not columns
        or any(not IDENTIFIER.fullmatch(name) for name in columns)
    ):
        raise UpgradeBlocked("preserved table projection is invalid")
    connection = config.connect(database)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name=%s",
                (database, table),
            )
            available = {
                _normalized_row(row)["column_name"]
                for row in cursor.fetchall()
            }
            missing = set(columns) - available
            if missing:
                raise UpgradeBlocked(
                    f"candidate {table} lost legacy columns: "
                    + ",".join(sorted(missing))
                )
            projection = ",".join(f"`{name}`" for name in columns)
            cursor.execute(
                "SELECT column_name FROM information_schema.key_column_usage "
                "WHERE table_schema=%s AND table_name=%s "
                "AND constraint_name='PRIMARY' ORDER BY ordinal_position",
                (database, table),
            )
            primary = [
                _normalized_row(row)["column_name"]
                for row in cursor.fetchall()
            ]
            ordering = (
                ",".join(f"`{name}`" for name in primary)
                if primary
                else projection
            )
            cursor.execute(
                f"SELECT {projection} FROM `{table}` "
                f"ORDER BY {ordering}"
            )
            rows = cursor.fetchall()
    finally:
        connection.close()
    return {
        "columns": columns,
        "row_count": len(rows),
        "rows_sha256": _sha256_bytes(_canonical_json(rows)),
    }


def _verify_matching_records_preservation(
    config: DatabaseConfig,
    source: str,
    candidate: str,
    source_snapshot: Mapping[str, Any],
    source_resume_state: str,
) -> dict[str, Any]:
    source_columns = [
        row["column_name"] for row in source_snapshot["columns"]
        if row["table_name"] == "matching_records"
    ]
    before = _table_projection_evidence(
        config, source, "matching_records", source_columns
    )
    after = _table_projection_evidence(
        config, candidate, "matching_records", source_columns
    )
    if after != before:
        raise UpgradeBlocked("matching_records legacy data changed")
    connection = config.connect(candidate)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS n FROM matching_records "
                "WHERE sent_resume_at IS NOT NULL"
            )
            non_null_count = int(cursor.fetchone()["n"])
    finally:
        connection.close()
    if source_resume_state == "absent" and non_null_count:
        raise UpgradeBlocked("sent_resume_at was inferred or backfilled")
    return {
        **after,
        "source_resume_state": source_resume_state,
        "sent_resume_non_null_count": non_null_count,
    }


def _verify_orders_preservation(
    config: DatabaseConfig,
    source: str,
    candidate: str,
    source_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    source_columns = [
        row["column_name"] for row in source_snapshot["columns"]
        if row["table_name"] == "orders"
    ]
    before = _table_projection_evidence(
        config, source, "orders", source_columns
    )
    after = _table_projection_evidence(
        config, candidate, "orders", source_columns
    )
    if after != before:
        raise UpgradeBlocked("orders legacy data changed")
    return after


def verify_candidate(
    config: DatabaseConfig,
    source: str,
    candidate: str,
    operation_receipt_path: Path,
) -> dict[str, Any]:
    receipt = read_receipt(operation_receipt_path)
    if receipt.get("status") not in VERIFYABLE_CANDIDATE_STATUSES:
        raise UpgradeBlocked("candidate has not completed schema/backfill")
    source_snapshot = _schema_snapshot(config, source)
    source_alert_state = _system_alert_projection_state(source_snapshot)
    source_resume_state = _matching_records_resume_delivery_state(
        source_snapshot
    )
    source_data = _table_evidence(config, source)
    candidate_data = _table_evidence(config, candidate)
    for table, evidence in source_data.items():
        actual = candidate_data.get(table)
        if not actual:
            raise UpgradeBlocked(f"preserved table is missing: {table}")
        if (
            actual.get("count") != evidence.get("count")
            or actual.get("primary_key_sha256")
            != evidence.get("primary_key_sha256")
        ):
            raise UpgradeBlocked(f"preserved table changed: {table}")
        if (
            table not in {"orders", "matching_records"}
            and not (
                table == "system_alerts"
                and source_alert_state == "absent"
            )
            and actual.get("checksum") != evidence.get("checksum")
        ):
            raise UpgradeBlocked(f"preserved table checksum changed: {table}")
    system_alert_preservation = (
        _verify_legacy_system_alert_rows(config, source, candidate)
        if source_alert_state == "absent"
        else {"mode": "current_unchanged", "row_count": source_data[
            "system_alerts"
        ]["count"]}
    )
    matching_records_preservation = _verify_matching_records_preservation(
        config,
        source,
        candidate,
        source_snapshot,
        source_resume_state,
    )
    orders_preservation = _verify_orders_preservation(
        config, source, candidate, source_snapshot
    )
    states = _owned_classification(_schema_snapshot(config, candidate))
    if any(state != "exact" for state in states.values()):
        raise UpgradeBlocked(f"candidate owned schema not exact: {states}")
    connection = config.connect(candidate)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS n FROM orders o "
                "LEFT JOIN v_order_details v ON v.case_no=o.case_no "
                "WHERE v.case_no IS NULL OR "
                "v.lifecycle_version<>o.lifecycle_version"
            )
            view_mismatches = int(cursor.fetchone()["n"])
    finally:
        connection.close()
    if view_mismatches:
        raise UpgradeBlocked("v_order_details lifecycle_version mismatch")
    receipt.update(
        status="verified", verified_at=_now(), source_data=source_data,
        candidate_data=candidate_data, owned_objects=states,
        view_mismatches=0,
        system_alert_preservation=system_alert_preservation,
        matching_records_preservation=matching_records_preservation,
        orders_preservation=orders_preservation,
    )
    write_receipt(operation_receipt_path, receipt)
    return receipt


def complete_cutover_after_restart(
    switch_receipt_path: Path,
    restart_port: Any,
    smoke_port: Any,
) -> dict[str, Any]:
    """Restart selected targets, run read smokes, and close the cutover."""

    receipt = read_receipt(switch_receipt_path)
    if receipt.get("status") != "switched":
        raise UpgradeBlocked("switch receipt is not restart eligible")
    post_restart: dict[str, Any] = {}
    try:
        runtime_receipts = restart_and_run_read_smoke(
            RELEASE_MANIFEST.required_restart_targets,
            RELEASE_MANIFEST.post_cutover_smoke_ids,
            restart_port,
            smoke_port,
        )
        smoke_by_id = {
            item["smoke_id"]: item
            for item in runtime_receipts["smoke_receipts"]
        }
        validators = _post_restart_validators(smoke_by_id)
        verification_receipts = run_manifest_verifications(
            RELEASE_MANIFEST.verification_contracts,
            phase="post-restart",
            validators=validators,
        )
        post_restart.update(
            runtime_receipts,
            verification_receipts=tuple(
                {
                    "verification_id": item.verification_id,
                    "phase": item.phase,
                    "status": item.status,
                    "evidence": dict(item.evidence),
                }
                for item in verification_receipts
            ),
        )
    finally:
        shutdown = getattr(restart_port, "shutdown", None)
        post_restart["shutdown_receipts"] = (
            tuple(shutdown()) if callable(shutdown) else ()
        )
    receipt.update(
        status="completed",
        completed_at=_now(),
        post_restart=post_restart,
    )
    write_receipt(switch_receipt_path, receipt)
    return receipt


def _post_restart_validators(
    smoke_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    def aggregate_smokes() -> Mapping[str, Any]:
        return {
            "status": "passed",
            "smoke_ids": tuple(smoke_by_id),
        }

    validators: dict[str, Any] = {
        smoke_id: (lambda item=item: item)
        for smoke_id, item in smoke_by_id.items()
    }
    validators["application-read-smoke"] = aggregate_smokes
    return validators


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in (
        "check", "dry-run", "backup", "restore", "apply", "verify",
        "switch", "complete-restart", "rollback-switch",
    ):
        modes.add_argument(f"--{name}", action="store_true")
    parser.add_argument("--environment-file", default=str(ROOT / ".env"))
    parser.add_argument("--source-database")
    parser.add_argument("--candidate-database", required=True)
    parser.add_argument("--plan-receipt")
    parser.add_argument("--operation-receipt")
    parser.add_argument("--source-dump")
    parser.add_argument("--source-backup-receipt")
    parser.add_argument("--switch-receipt")
    parser.add_argument("--mysqldump", default="mysqldump")
    parser.add_argument("--mysql", default="mysql")
    parser.add_argument("--mysql-container")
    parser.add_argument(
        "--release-manifest",
        action="append",
        default=[],
        help="Validated release manifest; repeat to apply an ordered chain",
    )
    parser.add_argument(
        "--rehearsal",
        action="store_true",
        help="Require isolated lu_test_* source and candidate databases",
    )
    parser.add_argument("--api-port", type=int, default=18022)
    parser.add_argument("--streamlit-port", type=int, default=18522)
    parser.add_argument("--startup-timeout-seconds", type=int, default=30)
    parser.add_argument("--runtime-evidence-directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    environment_file = Path(args.environment_file)
    try:
        configure_release_manifests(
            Path(path) for path in args.release_manifest
        )
        config, configured_source = config_from_env(environment_file)
        source = (args.source_database or configured_source).strip()
        if not source:
            raise UpgradeBlocked(
                "source database must be explicit when .env has no DB_DATABASE"
            )
        candidate = args.candidate_database
        if args.rehearsal:
            validate_rehearsal_database_names(source, candidate)
        else:
            validate_database_names(source, candidate)
        mode = next(
            name.replace("_", "-")
            for name in (
                "check", "dry_run", "backup", "restore", "apply", "verify",
                "switch", "complete_restart", "rollback_switch",
            )
            if getattr(args, name)
        )
        if mode in {"check", "dry-run"}:
            result = build_plan(config, source, candidate)
            if mode == "dry-run":
                if not args.plan_receipt:
                    raise UpgradeBlocked("--dry-run requires --plan-receipt")
                write_receipt(args.plan_receipt, result)
        elif mode == "backup":
            if not args.source_dump or not args.source_backup_receipt:
                raise UpgradeBlocked(
                    "--backup requires --source-dump and "
                    "--source-backup-receipt"
                )
            result = create_source_dump(
                config, source, Path(args.source_dump),
                Path(args.source_backup_receipt), mysqldump=args.mysqldump,
                mysql_container=args.mysql_container,
            )
        elif mode == "restore":
            required = (
                args.source_dump, args.source_backup_receipt,
                args.operation_receipt,
            )
            if not all(required):
                raise UpgradeBlocked("restore receipt arguments are required")
            result = restore_candidate(
                config, source, candidate, Path(args.source_dump),
                Path(args.source_backup_receipt),
                Path(args.operation_receipt), mysql=args.mysql,
                mysql_container=args.mysql_container,
            )
        elif mode == "apply":
            if not args.plan_receipt or not args.operation_receipt:
                raise UpgradeBlocked("apply requires plan and operation receipts")
            result = apply_schema(
                config, source, candidate, Path(args.plan_receipt),
                Path(args.operation_receipt),
                mysql_container=args.mysql_container,
            )
        elif mode == "verify":
            if not args.operation_receipt:
                raise UpgradeBlocked("verify requires operation receipt")
            result = verify_candidate(
                config, source, candidate, Path(args.operation_receipt)
            )
        elif mode == "switch":
            if not args.operation_receipt or not args.switch_receipt:
                raise UpgradeBlocked("switch receipts are required")
            result = switch_environment(
                environment_file, source, candidate,
                Path(args.operation_receipt), Path(args.switch_receipt),
            )
        elif mode == "complete-restart":
            if not args.switch_receipt or not args.runtime_evidence_directory:
                raise UpgradeBlocked(
                    "complete-restart requires switch receipt and runtime "
                    "evidence directory"
                )
            _, database_environment = _read_env_bytes(environment_file)
            runtime_config = CandidateRuntimeConfig(
                project_root=ROOT,
                api_port=args.api_port,
                streamlit_port=args.streamlit_port,
                startup_timeout_seconds=args.startup_timeout_seconds,
                database_environment={
                    **database_environment,
                    "DB_DATABASE": candidate,
                },
                database_config=config,
                candidate_database=candidate,
                evidence_directory=Path(args.runtime_evidence_directory),
            )
            result = complete_cutover_after_restart(
                Path(args.switch_receipt),
                EphemeralCandidateRestartPort(runtime_config),
                CandidateReadSmokePort(runtime_config),
            )
        else:
            if not args.switch_receipt:
                raise UpgradeBlocked("rollback-switch requires switch receipt")
            result = rollback_environment(
                environment_file, Path(args.switch_receipt)
            )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
