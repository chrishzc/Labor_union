"""
File: bootstrap_line_configuration.py
Description: 驗證、初始化或受控修復 MySQL 中的 canonical LINE 設定。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domains.line.configuration import LineConfigurationKind
from api.schemas.line_config import LineMenusConfig
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from infrastructure.mysql.mysql_adapter import DB_CONFIG, get_connection
from shared_kernel.identities import ActorContext, CorrelationId
from subsystems.line.capabilities import LineCapability
from subsystems.line.configuration_application import LineConfigurationApplication
from subsystems.line.message_configuration import (
    validate_message_schedules,
    validate_message_templates,
)

CONFIG_FILES = {
    LineConfigurationKind.MESSAGE_TEMPLATES: ROOT / "config" / "message_templates.json",
    LineConfigurationKind.MESSAGE_SCHEDULES: ROOT / "config" / "message_schedules.json",
    LineConfigurationKind.RICH_MENUS: ROOT / "config" / "line_menu.json",
    LineConfigurationKind.LIFF: ROOT / "config" / "liff_settings.json",
    LineConfigurationKind.CUSTOMER_SERVICE: ROOT / "config" / "customer_service.json",
}


def _canonical_definitions_fingerprint(definitions: dict[LineConfigurationKind, dict[str, object]]) -> str:
    payload = {
        kind.value: definitions[kind]
        for kind in sorted(definitions, key=lambda item: item.value)
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _require_target_database(target: str) -> None:
    if not target or target != str(DB_CONFIG.get("database") or ""):
        raise ValueError("target database must exactly match configured DB_DATABASE")
    if not re.fullmatch(r"lu_test_[a-z0-9_]+", target):
        raise ValueError("target database must be an explicitly named lu_test_* database")
    if os.getenv("APP_ENV", "development").strip().lower() in {"prod", "production"}:
        raise ValueError("production environment is not permitted for this operator CLI")


def _check_connected_identity(target: str) -> None:
    configured_host = os.getenv("DB_HOST", "").strip()
    if not configured_host:
        raise RuntimeError("DB_HOST must be configured explicitly")
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS database_name, @@hostname AS server")
            identity = cursor.fetchone()
            cursor.execute(
                "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN "
                "('line_configuration_revisions','line_configuration_current') "
                "ORDER BY TABLE_NAME"
            )
            tables = cursor.fetchall()
        if not identity or identity.get("database_name") != target:
            raise RuntimeError("connected database does not match --target-database")
        if not str(identity.get("server") or "").strip():
            raise RuntimeError("connected MySQL server identity is unavailable")
        if [row.get("TABLE_NAME") for row in tables] != [
            "line_configuration_current",
            "line_configuration_revisions",
        ]:
            raise RuntimeError("canonical LINE configuration schema is incomplete")
    finally:
        connection.close()


def _validate_backup(path_value: str | None, target: str) -> dict[str, object]:
    if not path_value:
        raise ValueError("--apply requires --backup-receipt")
    path = Path(path_value).expanduser().resolve()
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError("backup receipt does not exist or is empty")
    header = path.read_bytes()[:1_048_576]
    if not header.startswith((b"-- MySQL dump", b"-- MariaDB dump")):
        raise ValueError("backup receipt is not a MySQL dump")
    marker = f"Current Database: `{target}`".encode()
    if marker not in header and f"USE `{target}`".encode() not in header:
        raise ValueError("backup receipt does not identify the target database")
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "target_database": target}


def _read_plan(path_value: str | None, target: str, fingerprint: str) -> dict[str, object]:
    if not path_value:
        raise ValueError("--apply requires --plan-receipt from a prior --dry-run")
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise ValueError("dry-run plan receipt does not exist")
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("dry-run plan receipt is not valid UTF-8 JSON") from exc
    if plan.get("mode") != "dry-run" or plan.get("target_database") != target:
        raise ValueError("dry-run plan receipt belongs to another target")
    if plan.get("definitions_fingerprint") != fingerprint:
        raise ValueError("LINE configuration definition drift detected")
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write only missing revision-0 LINE configuration into MySQL.",
    )
    parser.add_argument(
        "--repair-empty-rich-menus",
        action="store_true",
        help="Append a repair revision only when canonical Rich Menu configuration is exactly {}.",
    )
    parser.add_argument("--target-database", required=True)
    parser.add_argument("--confirm-apply")
    parser.add_argument("--plan-receipt", type=Path)
    parser.add_argument("--backup-receipt", type=Path)
    parser.add_argument("--receipt-path", type=Path)
    arguments = parser.parse_args()
    if not re.fullmatch(r"lu_test_[a-z0-9_]+", arguments.target_database):
        parser.error("target database must be an explicitly named lu_test_* database")
    definitions = _definitions()
    validate_message_templates(definitions[LineConfigurationKind.MESSAGE_TEMPLATES])
    validate_message_schedules(
        definitions[LineConfigurationKind.MESSAGE_SCHEDULES],
        definitions[LineConfigurationKind.MESSAGE_TEMPLATES],
    )
    LineMenusConfig.model_validate(definitions[LineConfigurationKind.RICH_MENUS])
    fingerprint = _canonical_definitions_fingerprint(definitions)
    if arguments.repair_empty_rich_menus and not arguments.apply:
        parser.error("--repair-empty-rich-menus requires --apply")
    if not arguments.apply:
        payload = {
            "mode": "dry-run",
            "target_database": arguments.target_database,
            "definitions_fingerprint": fingerprint,
            "configuration_kinds": sorted(kind.value for kind in definitions),
        }
        if arguments.receipt_path:
            arguments.receipt_path.parent.mkdir(parents=True, exist_ok=True)
            arguments.receipt_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    if not arguments.target_database:
        parser.error("--apply requires explicit --target-database")
    try:
        _require_target_database(arguments.target_database)
        expected = f"APPLY {arguments.target_database}"
        if arguments.confirm_apply != expected:
            parser.error(f"--confirm-apply must exactly equal {expected!r}")
        _read_plan(arguments.plan_receipt, arguments.target_database, fingerprint)
        backup = _validate_backup(arguments.backup_receipt, arguments.target_database)
        if not arguments.receipt_path:
            parser.error("--apply requires --receipt-path for a terminal receipt")
        _check_connected_identity(arguments.target_database)
    except ValueError as exc:
        parser.error(str(exc))
    load_dotenv(ROOT / ".env")
    actor = ActorContext(
        "system:line-configuration-bootstrap",
        tuple(sorted({LineCapability.CONFIG_MANAGE.value})),
    )
    results = LineConfigurationApplication(open_line_unit_of_work).bootstrap_missing(
        definitions,
        actor,
        reason="initial canonical LINE configuration bootstrap",
        correlation_id=CorrelationId("line-config-bootstrap:v1"),
    )
    payload = {
        "mode": "apply",
        "receipt_status": "committed",
        "target_database": arguments.target_database,
        "definitions_fingerprint": fingerprint,
        "applied_count": len(results),
        "backup_receipt": backup,
    }
    if arguments.repair_empty_rich_menus:
        repair = LineConfigurationApplication(open_line_unit_of_work).repair_empty_rich_menu_configuration(
            definitions[LineConfigurationKind.RICH_MENUS], actor,
            correlation_id=CorrelationId("line-config-repair:rich-menus-empty:v1"),
        )
        payload["rich_menu_repaired"] = bool(repair)
    arguments.receipt_path.parent.mkdir(parents=True, exist_ok=True)
    arguments.receipt_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def _definitions() -> dict[LineConfigurationKind, dict[str, object]]:
    result = {}
    for kind, path in CONFIG_FILES.items():
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"{path} must contain a JSON object")
        result[kind] = value
    return result


if __name__ == "__main__":
    raise SystemExit(main())
