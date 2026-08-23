"""
File: provision_admin_entry_target_state.py
Description: 以明確 operator 命令 provision、attest、backup 或 restore 管理端 12-entry runtime state。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from infrastructure.file.admin_entry_target_store import FileAdminEntryTargetStore
from subsystems.access.admin_entry_target_control import (
    EntryTargetError,
    EntryTargetState,
    make_initial_state,
    state_from_mapping,
)


def _read_template(path: Path) -> EntryTargetState:
    try:
        payload = json.loads(path.read_bytes().decode("utf-8"))
        state = state_from_mapping(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, EntryTargetError) as exc:
        raise EntryTargetError("validation", "entry_target_template_invalid", "Entry target template 無效") from exc
    if state != make_initial_state():
        raise EntryTargetError("validation", "entry_target_template_not_frozen", "Entry target template 非 frozen 12-entry state")
    return state


def provision_state(template_path: Path, output_path: Path, *, _allow_test_path: bool = False) -> dict[str, object]:
    state = _read_template(template_path)
    store = FileAdminEntryTargetStore(output_path, _allow_test_path=_allow_test_path)
    return store.create(state)


def attest_state(state_path: Path, *, _allow_test_path: bool = False) -> dict[str, object]:
    return FileAdminEntryTargetStore(state_path, _allow_test_path=_allow_test_path).attest()


def backup_state(state_path: Path, backup_path: Path, *, _allow_test_path: bool = False) -> dict[str, object]:
    return FileAdminEntryTargetStore(state_path, _allow_test_path=_allow_test_path).backup_to(backup_path)


def restore_state(backup_path: Path, output_path: Path, *, _allow_test_path: bool = False) -> dict[str, object]:
    return FileAdminEntryTargetStore(backup_path, _allow_test_path=_allow_test_path).restore_to(output_path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provision admin entry target runtime state")
    commands = parser.add_subparsers(dest="command", required=True)

    provision = commands.add_parser("provision")
    provision.add_argument("--template", required=True, type=Path)
    provision.add_argument("--output", required=True, type=Path)

    attest = commands.add_parser("attest")
    attest.add_argument("--state", required=True, type=Path)

    backup = commands.add_parser("backup")
    backup.add_argument("--state", required=True, type=Path)
    backup.add_argument("--output", required=True, type=Path)

    restore = commands.add_parser("restore")
    restore.add_argument("--backup", required=True, type=Path)
    restore.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "provision":
            receipt = provision_state(args.template, args.output)
        elif args.command == "attest":
            receipt = attest_state(args.state)
        elif args.command == "backup":
            receipt = backup_state(args.state, args.output)
        else:
            receipt = restore_state(args.backup, args.output)
    except EntryTargetError as error:
        print(json.dumps({"status": "blocked", "code": error.code}, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
