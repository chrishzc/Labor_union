"""Create a database-backed administrator account for the internal Web UI."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.admin_auth_service import ROLE_LEVELS, create_admin_user


def main() -> int:
    parser = argparse.ArgumentParser(description="建立工會管理後台帳號")
    parser.add_argument("--username")
    parser.add_argument("--display-name")
    parser.add_argument("--role", choices=sorted(ROLE_LEVELS), default="system_admin")
    parser.add_argument("--line-user-id", default=None)
    args = parser.parse_args()

    username = args.username or input("管理員帳號：").strip()
    display_name = args.display_name or input("顯示名稱：").strip()
    password = getpass.getpass("密碼（至少 12 個字元）：")
    confirmation = getpass.getpass("再次輸入密碼：")
    if password != confirmation:
        print("[Error] 兩次輸入的密碼不同")
        return 1

    try:
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

    print(f"[OK] 管理員已建立：id={admin_id}, username={username}, role={args.role}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
