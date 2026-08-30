"""Safely upgrade the known legacy canonical Rich Menu defaults."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.schemas.line_config import LineMenusConfig
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.configuration import LineConfigurationKind
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from infrastructure.mysql.mysql_adapter import DB_CONFIG, get_connection
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.capabilities import LineCapability
from subsystems.line.configuration_application import LineConfigurationApplication

KNOWN_LEGACY_SHA256 = (
    "10fc62aca2d2a689e15eec622a34353d692b5e2eaba74357e6faaba1f2a9e422"
)
TARGET_PATH = ROOT / "config" / "line_menu.json"
RECEIPT_CONTRACT = "line-menu-merge-defaults/v1"


def _require_target_database(target: str) -> None:
    configured = str(DB_CONFIG.get("database") or "").strip()
    if not target or target != configured:
        raise ValueError("target database must exactly match configured DB_DATABASE")
    if target == "union_db" or not target.startswith("lu_test_"):
        raise ValueError("target database must be an explicitly named lu_test_* database")
    if os.getenv("APP_ENV", "development").strip().lower() in {"prod", "production"}:
        raise ValueError("production credential gate refused this operator CLI")


def _check_connected_identity(target: str) -> dict[str, str]:
    configured_host = os.getenv("DB_HOST", "").strip()
    if not configured_host:
        raise RuntimeError("configured DB_HOST is required for the connected-host check")
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS database_name, @@hostname AS server")
            identity = cursor.fetchone()
    finally:
        connection.close()
    if not identity or identity.get("database_name") != target:
        raise RuntimeError("connected database does not match the explicit target")
    server = str(identity.get("server") or "").strip()
    if not server:
        raise RuntimeError("connected MySQL server identity is unavailable")
    return {"database": target, "configured_host": configured_host, "server": server}


def _validate_backup(path_value: Path | None, target: str) -> dict[str, object]:
    if path_value is None:
        raise ValueError("--apply requires --backup-receipt")
    path = path_value.expanduser().resolve()
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError("backup receipt does not exist or is empty")
    data = path.read_bytes()
    if not data.startswith((b"-- MySQL dump", b"-- MariaDB dump")):
        raise ValueError("backup receipt is not a MySQL dump")
    if (
        f"Current Database: `{target}`".encode() not in data[:1_048_576]
        and f"USE `{target}`".encode() not in data[:1_048_576]
    ):
        raise ValueError("backup receipt does not identify the target database")
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "target_database": target}


def _read_plan(path: Path | None, target: str, target_hash: str) -> dict[str, object]:
    if path is None:
        raise ValueError("--apply requires --plan-receipt from a prior --dry-run")
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError("dry-run plan receipt does not exist")
    try:
        plan = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("dry-run plan receipt is not valid UTF-8 JSON") from error
    if (
        plan.get("contract") != RECEIPT_CONTRACT
        or plan.get("mode") != "dry-run"
        or plan.get("target_database") != target
        or plan.get("target_hash") != target_hash
    ):
        raise ValueError("Rich Menu dry-run plan drift detected")
    return plan


def _read_terminal(path: Path | None, target: str) -> dict[str, object]:
    if path is None:
        raise ValueError("--verify/--replay requires --receipt-path")
    resolved = path.expanduser().resolve()
    try:
        receipt = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("terminal receipt is not valid UTF-8 JSON") from error
    if receipt.get("contract") != RECEIPT_CONTRACT or receipt.get("target_database") != target:
        raise ValueError("terminal receipt belongs to another target")
    if receipt.get("receipt_status") != "committed":
        raise ValueError("terminal receipt is not committed")
    return receipt


# Kept cohesive so the fingerprint gate remains visibly adjacent to its only write path.
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Append the new canonical revision when the current revision is the known legacy value.",
    )
    parser.add_argument("--target-database", required=True)
    parser.add_argument("--confirm-apply")
    parser.add_argument("--plan-receipt", type=Path)
    parser.add_argument("--backup-receipt", type=Path)
    parser.add_argument("--receipt-path", type=Path)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--replay", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.apply and (arguments.verify or arguments.replay):
        parser.error("--apply, --verify, and --replay are mutually exclusive")
    if arguments.verify and arguments.replay:
        parser.error("--verify and --replay are mutually exclusive")
    try:
        _require_target_database(arguments.target_database)
        if arguments.verify or arguments.replay:
            receipt = _read_terminal(arguments.receipt_path, arguments.target_database)
            receipt["status"] = "verified" if arguments.verify else "replayed"
            print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
            return 0
    except (ValueError, RuntimeError) as error:
        parser.error(str(error))
    target = _target_definition()
    target_json = canonical_line_payload_json(target)
    load_dotenv(ROOT / ".env")
    actor = _actor()
    application = LineConfigurationApplication(open_line_unit_of_work)
    current = application.get(LineConfigurationKind.RICH_MENUS, actor)
    current_hash = definition_sha256(current.definition_json)
    target_hash = definition_sha256(target_json)
    print(f"Current Rich Menu revision: {current.revision.value}")
    print(f"Current definition SHA-256: {current_hash}")
    if current_hash == target_hash:
        print("Canonical Rich Menu defaults already match the merge defaults.")
        return 0
    if current_hash != KNOWN_LEGACY_SHA256:
        print("Blocked: current Rich Menu revision is not the known legacy definition.")
        return 2
    if not arguments.apply:
        if arguments.plan_receipt:
            arguments.plan_receipt.parent.mkdir(parents=True, exist_ok=True)
            arguments.plan_receipt.write_text(
                json.dumps(
                    {
                        "contract": RECEIPT_CONTRACT,
                        "mode": "dry-run",
                        "target_database": arguments.target_database,
                        "current_hash": current_hash,
                        "target_hash": target_hash,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        print("Eligible for upgrade; dry-run completed without a DB write.")
        return 0
    expected_confirmation = f"APPLY {arguments.target_database}"
    if arguments.confirm_apply != expected_confirmation:
        parser.error(f"--confirm-apply must exactly equal {expected_confirmation!r}")
    try:
        plan = _read_plan(arguments.plan_receipt, arguments.target_database, target_hash)
        backup = _validate_backup(arguments.backup_receipt, arguments.target_database)
        identity = _check_connected_identity(arguments.target_database)
        if not arguments.receipt_path:
            raise ValueError("--apply requires --receipt-path for terminal receipt")
    except (ValueError, RuntimeError) as error:
        parser.error(str(error))
    result = application.apply(
        kind=LineConfigurationKind.RICH_MENUS,
        expected_revision=current.revision,
        definition=target,
        actor=actor,
        reason="upgrade known legacy Rich Menu defaults to merge interface",
        idempotency_key=IdempotencyKey("line-menu-merge-defaults:20260811:v1"),
        correlation_id=CorrelationId("line-menu-merge-defaults:20260811:v1"),
    )
    verified = application.get(LineConfigurationKind.RICH_MENUS, actor)
    verified_hash = definition_sha256(verified.definition_json)
    if verified_hash != target_hash:
        parser.error("post-apply verification found Rich Menu definition drift")
    terminal = {
        **plan,
        "mode": "apply",
        "receipt_status": "committed",
        "target_database": arguments.target_database,
        "connected_identity": identity,
        "backup_receipt": backup,
        "revision": result.snapshot.revision.value,
        "verified_hash": verified_hash,
        "replay_key": plan["target_hash"],
    }
    arguments.receipt_path.parent.mkdir(parents=True, exist_ok=True)
    arguments.receipt_path.write_text(
        json.dumps(terminal, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Applied canonical Rich Menu revision {result.snapshot.revision.value}.")
    return 0


def definition_sha256(definition_json: str) -> str:
    return hashlib.sha256(definition_json.encode("utf-8")).hexdigest()


def _target_definition() -> dict[str, object]:
    raw = json.loads(TARGET_PATH.read_text(encoding="utf-8"))
    validated = LineMenusConfig.model_validate(raw)
    return validated.model_dump(mode="json")


def _actor() -> ActorContext:
    permissions = {
        LineCapability.CONFIG_READ.value,
        LineCapability.CONFIG_MANAGE.value,
    }
    return ActorContext(
        "system:line-menu-merge-default-upgrade",
        tuple(sorted(permissions)),
    )


if __name__ == "__main__":
    raise SystemExit(main())
