"""
File: create_admin.py
Description: 提供離線建立一般管理員與唯一 root bootstrap 的維運入口。
"""

from __future__ import annotations

import argparse
import hashlib
import getpass
import json
import os
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from subsystems.access.authentication_session import (
    ROLE_LEVELS,
    bootstrap_root_admin,
    create_admin_user,
)
from infrastructure.mysql.mysql_adapter import DB_CONFIG, get_connection


def _require_target_database(target: str) -> None:
    configured = str(DB_CONFIG.get("database") or "")
    if not target or target != configured:
        raise ValueError("target database must exactly match configured DB_DATABASE")
    if not re.fullmatch(r"lu_test_[a-z0-9_]+", target):
        raise ValueError("target database must be an explicitly named lu_test_* database")
    if os.getenv("APP_ENV", "development").strip().lower() in {"prod", "production"}:
        raise ValueError("production environment is not permitted for this operator CLI")


def _check_connected_identity(target: str) -> None:
    if not os.getenv("DB_HOST", "").strip():
        raise RuntimeError("DB_HOST must be configured explicitly")
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS database_name, @@hostname AS server")
            identity = cursor.fetchone()
            cursor.execute(
                "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN "
                "('admin_users','admin_root_account') ORDER BY TABLE_NAME"
            )
            tables = cursor.fetchall()
        if not identity or identity.get("database_name") != target:
            raise RuntimeError("connected database does not match --target-database")
        if not str(identity.get("server") or "").strip():
            raise RuntimeError("connected MySQL server identity is unavailable")
        if [row.get("TABLE_NAME") for row in tables] != ["admin_root_account", "admin_users"]:
            raise RuntimeError("canonical Access Control schema is incomplete")
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
    if f"Current Database: `{target}`".encode() not in header and f"USE `{target}`".encode() not in header:
        raise ValueError("backup receipt does not identify the target database")
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "target_database": target}


def _plan(args) -> dict[str, object]:
    return {
        "mode": "dry-run",
        "target_database": args.target_database,
        "username": args.username,
        "display_name": args.display_name,
        "role": args.role,
        "bootstrap_root": bool(args.bootstrap_root),
    }


def _read_plan(path_value: str | None, expected: dict[str, object]) -> dict[str, object]:
    if not path_value:
        raise ValueError("--apply requires --plan-receipt from a prior --dry-run")
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise ValueError("dry-run plan receipt does not exist")
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("dry-run plan receipt is not valid UTF-8 JSON") from exc
    if plan != expected:
        raise ValueError("dry-run plan receipt does not match the requested admin operation")
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description="建立工會管理後台帳號")
    parser.add_argument("--username")
    parser.add_argument("--display-name")
    parser.add_argument("--role", choices=sorted(ROLE_LEVELS), default="system_admin")
    parser.add_argument("--line-user-id", default=None)
    parser.add_argument("--bootstrap-root", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--target-database", required=True)
    parser.add_argument("--confirm-apply")
    parser.add_argument("--plan-receipt", type=Path)
    parser.add_argument("--backup-receipt", type=Path)
    parser.add_argument("--receipt-path", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"lu_test_[a-z0-9_]+", args.target_database):
        parser.error("target database must be an explicitly named lu_test_* database")

    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run are mutually exclusive")
    if not args.apply:
        payload = _plan(args)
        if args.receipt_path:
            args.receipt_path.parent.mkdir(parents=True, exist_ok=True)
            args.receipt_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    if not args.target_database:
        parser.error("--apply requires explicit --target-database")
    if not args.username or not args.display_name:
        parser.error("--apply requires explicit --username and --display-name")
    try:
        _require_target_database(args.target_database)
        expected_confirmation = f"APPLY {args.target_database}"
        if args.confirm_apply != expected_confirmation:
            parser.error(f"--confirm-apply must exactly equal {expected_confirmation!r}")
        _read_plan(args.plan_receipt, _plan(args))
        backup = _validate_backup(args.backup_receipt, args.target_database)
        if not args.receipt_path:
            parser.error("--apply requires --receipt-path for a terminal receipt")
        _check_connected_identity(args.target_database)
    except ValueError as exc:
        parser.error(str(exc))

    username = args.username or input("管理員帳號：").strip()
    display_name = args.display_name or input("顯示名稱：").strip()
    password = getpass.getpass("密碼（至少 12 個字元）：")
    confirmation = getpass.getpass("再次輸入密碼：")
    if password != confirmation:
        print("[Error] 兩次輸入的密碼不同")
        return 1

    try:
        if args.bootstrap_root:
            confirmation_text = input("此動作只可建立唯一 root。輸入 BOOTSTRAP_ROOT 確認：").strip()
            if confirmation_text != "BOOTSTRAP_ROOT":
                print("[Error] 未確認 root bootstrap")
                return 1
            admin_id = bootstrap_root_admin(
                username=username,
                password=password,
                display_name=display_name,
                linked_line_user_id=args.line_user_id,
            )
        else:
            admin_id = create_admin_user(
                username=username,
                password=password,
                display_name=display_name,
                role=args.role,
                linked_line_user_id=args.line_user_id,
            )
    except ValueError as exc:
        print(f"[Error] {exc}")
        return 1

    account_kind = "root" if args.bootstrap_root else "管理員"
    payload = {
        "mode": "apply",
        "receipt_status": "committed",
        "target_database": args.target_database,
        "account_kind": account_kind,
        "admin_id": admin_id,
        "username": username,
        "role": args.role,
        "backup_receipt": backup,
    }
    args.receipt_path.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
