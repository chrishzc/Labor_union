"""Plan or apply the bundled LINE common-QA catalog to one explicit MySQL target."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.dependencies.knowledge_retrieval import import_builtin_knowledge_catalog
from api.dependencies.line_ai_qa_catalog import (
    CATALOG_SOURCE_IDENTITY,
    load_line_ai_qa_catalog,
)
from infrastructure.mysql.mysql_adapter import DB_CONFIG, get_connection
from shared_kernel.identities import ActorContext
from subsystems.knowledge_retrieval.qa_catalog_import import build_qa_import_commands


CATALOG_PATH = PROJECT_ROOT / CATALOG_SOURCE_IDENTITY
REQUIRED_TABLES = (
    "admin_users",
    "knowledge_apply_receipts",
    "knowledge_indexes",
    "knowledge_item_events",
    "knowledge_item_versions",
    "knowledge_items",
    "knowledge_jobs",
)
ALLOWED_ENVIRONMENTS = frozenset(
    {"dev", "development", "local", "test", "staging", "prod", "production"}
)


def _require_runtime(target_database: str) -> str:
    configured_database = str(DB_CONFIG.get("database") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]+", target_database):
        raise ValueError("--target-database must be a simple MySQL database name")
    if target_database != configured_database:
        raise ValueError("--target-database must exactly match configured DB_DATABASE")
    if not os.getenv("DB_HOST", "").strip():
        raise ValueError("DB_HOST must be configured explicitly")
    environment = os.getenv("APP_ENV", "").strip().lower()
    if environment not in ALLOWED_ENVIRONMENTS:
        raise ValueError("APP_ENV must be explicitly configured")
    return environment


def _read_target(target_database: str, actor_username: str) -> dict[str, object]:
    source_identities = tuple(
        f"line-common-qa:{item.id}" for item in load_line_ai_qa_catalog()
    )
    placeholders = ",".join(["%s"] * len(source_identities))
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS database_name, @@hostname AS server")
            identity = cursor.fetchone()
            cursor.execute(
                "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN "
                f"({','.join(['%s'] * len(REQUIRED_TABLES))}) ORDER BY TABLE_NAME",
                REQUIRED_TABLES,
            )
            tables = tuple(row["TABLE_NAME"] for row in cursor.fetchall())
            cursor.execute(
                "SELECT id,username,enabled FROM admin_users WHERE username=%s",
                (actor_username.strip().lower(),),
            )
            actor = cursor.fetchone()
            cursor.execute(
                "SELECT id,source_identity,state,version,content,content_digest "
                f"FROM knowledge_items WHERE source_identity IN ({placeholders}) "
                "ORDER BY source_identity",
                source_identities,
            )
            rows = tuple(cursor.fetchall())
    finally:
        connection.close()

    if not identity or identity.get("database_name") != target_database:
        raise RuntimeError("connected database does not match --target-database")
    if not str(identity.get("server") or "").strip():
        raise RuntimeError("connected MySQL server identity is unavailable")
    if tables != tuple(sorted(REQUIRED_TABLES)):
        raise RuntimeError("canonical Knowledge schema is incomplete")
    if actor is None:
        raise RuntimeError("configured Knowledge import actor does not exist")
    if not bool(actor.get("enabled")):
        raise RuntimeError("configured Knowledge import actor is disabled")
    return {
        "database_name": str(identity["database_name"]),
        "server": str(identity["server"]),
        "actor_id": int(actor["id"]),
        "actor_username": str(actor["username"]),
        "rows": rows,
    }


def _state_fingerprint(rows) -> str:
    payload = [
        {
            "source_identity": str(row["source_identity"]),
            "state": str(row["state"]),
            "version": int(row["version"]),
            "content_digest": str(row["content_digest"]),
        }
        for row in rows
    ]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _build_plan(
    target_database: str, actor_username: str
) -> tuple[dict[str, object], dict[str, object]]:
    environment = _require_runtime(target_database)
    target = _read_target(target_database, actor_username)
    items = load_line_ai_qa_catalog()
    commands = build_qa_import_commands(
        items,
        ActorContext(str(target["actor_id"])),
        "builtin-line-common-qa-production-v1",
        "builtin-line-common-qa-production-v1",
    )
    rows = {str(row["source_identity"]): row for row in target["rows"]}
    command_by_identity = {command.source_identity: command for command in commands}
    missing = sorted(set(command_by_identity) - set(rows))
    preserved_modified = sorted(
        identity
        for identity, row in rows.items()
        if row["content"] != command_by_identity[identity].content
    )
    publish_candidates = sorted(
        identity
        for identity, row in rows.items()
        if identity in {
            f"line-common-qa:{item.id}" for item in items if item.enabled
        }
        and str(row["state"]) == "draft"
        and int(row["version"]) == 1
        and row["content"] == command_by_identity[identity].content
    )
    publish_after_import = sorted(
        identity
        for identity in missing
        if identity in {
            f"line-common-qa:{item.id}" for item in items if item.enabled
        }
    )
    plan = {
        "mode": "dry-run",
        "operation": "import_builtin_knowledge_catalog",
        "environment": environment,
        "target_database": target_database,
        "target_server": target["server"],
        "actor_id": target["actor_id"],
        "actor_username": target["actor_username"],
        "catalog_source": CATALOG_SOURCE_IDENTITY,
        "catalog_sha256": hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest(),
        "catalog_count": len(items),
        "enabled_count": sum(1 for item in items if item.enabled),
        "existing_count": len(rows),
        "missing_count": len(missing),
        "missing_source_identities": missing,
        "preserved_modified_count": len(preserved_modified),
        "preserved_modified_source_identities": preserved_modified,
        "publish_candidate_count": len(set(publish_candidates + publish_after_import)),
        "publish_candidate_source_identities": sorted(
            set(publish_candidates + publish_after_import)
        ),
        "target_state_fingerprint": _state_fingerprint(target["rows"]),
    }
    return plan, target


def _read_plan(path_value: Path | None, expected: dict[str, object]) -> dict[str, object]:
    if path_value is None or not path_value.is_file():
        raise ValueError("--apply requires --plan-receipt from a prior dry-run")
    try:
        plan = json.loads(path_value.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("dry-run plan receipt is not valid UTF-8 JSON") from exc
    for key in (
        "operation",
        "environment",
        "target_database",
        "target_server",
        "actor_id",
        "actor_username",
        "catalog_sha256",
        "target_state_fingerprint",
    ):
        if plan.get(key) != expected.get(key):
            raise ValueError(f"dry-run plan drift detected: {key}")
    return plan


def _validate_backup(path_value: Path | None, target_database: str) -> dict[str, str]:
    if path_value is None or not path_value.is_file() or path_value.stat().st_size <= 0:
        raise ValueError("--apply requires a non-empty --backup-receipt")
    header = path_value.read_bytes()[:1_048_576]
    markers = (
        f"Current Database: `{target_database}`".encode(),
        f"USE `{target_database}`".encode(),
    )
    if not header.startswith((b"-- MySQL dump", b"-- MariaDB dump")):
        raise ValueError("backup receipt is not a MySQL or MariaDB dump")
    if not any(marker in header for marker in markers):
        raise ValueError("backup receipt does not identify the target database")
    digest = hashlib.sha256()
    with path_value.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path_value.resolve()),
        "sha256": digest.hexdigest(),
        "target_database": target_database,
    }


def _write_json(path: Path | None, payload: dict[str, object]) -> None:
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _apply(
    arguments: argparse.Namespace,
    plan: dict[str, object],
    target: dict[str, object],
) -> dict[str, object]:
    actor = ActorContext(str(target["actor_id"]))
    result = import_builtin_knowledge_catalog(
        actor,
        "builtin-line-common-qa-production-v1",
        "builtin-line-common-qa-production-v1",
    )
    final_target = _read_target(arguments.target_database, arguments.actor_username)
    return {
        "mode": "apply",
        "operation": "import_builtin_knowledge_catalog",
        "receipt_status": "committed",
        "environment": plan["environment"],
        "target_database": arguments.target_database,
        "target_server": final_target["server"],
        "actor_username": final_target["actor_username"],
        "catalog_sha256": plan["catalog_sha256"],
        **result,
        "final_target_state_fingerprint": _state_fingerprint(final_target["rows"]),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Read-only plan (default).")
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Import missing items and publish pristine enabled v1 items.",
    )
    parser.add_argument("--target-database", required=True)
    parser.add_argument("--actor-username", required=True)
    parser.add_argument("--confirm-apply")
    parser.add_argument("--plan-receipt", type=Path)
    parser.add_argument("--backup-receipt", type=Path)
    parser.add_argument("--receipt-path", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        current_plan, target = _build_plan(
            arguments.target_database, arguments.actor_username
        )
        if not arguments.apply:
            _write_json(arguments.receipt_path, current_plan)
            return 0

        confirmation = f"IMPORT BUILTIN QA INTO {arguments.target_database}"
        if arguments.confirm_apply != confirmation:
            parser.error(f"--confirm-apply must exactly equal {confirmation!r}")
        if arguments.receipt_path is None:
            parser.error("--apply requires --receipt-path for a terminal receipt")
        _read_plan(arguments.plan_receipt, current_plan)
        backup = _validate_backup(arguments.backup_receipt, arguments.target_database)
        payload = _apply(arguments, current_plan, target)
        payload["backup_receipt"] = backup
        _write_json(arguments.receipt_path, payload)
        return 0
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
