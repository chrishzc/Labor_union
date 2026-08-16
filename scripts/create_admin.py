"""
File: create_admin.py
Description: 提供離線建立一般管理員與唯一 root bootstrap 的維運入口。
"""

from __future__ import annotations

import argparse
import getpass
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


def main() -> int:
    parser = argparse.ArgumentParser(description="建立工會管理後台帳號")
    parser.add_argument("--username")
    parser.add_argument("--display-name")
    parser.add_argument("--role", choices=sorted(ROLE_LEVELS), default="system_admin")
    parser.add_argument("--line-user-id", default=None)
    parser.add_argument("--bootstrap-root", action="store_true")
    args = parser.parse_args()

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
    print(f"[OK] {account_kind}已建立：id={admin_id}, username={username}, role={args.role}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
