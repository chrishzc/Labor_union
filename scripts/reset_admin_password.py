"""Reset a database-backed administrator password."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from subsystems.access.authentication_session import reset_admin_password


def main() -> int:
    parser = argparse.ArgumentParser(description="重設工會管理後台帳號密碼")
    parser.add_argument("--username")
    args = parser.parse_args()

    username = args.username or input("管理員帳號：").strip()
    password = getpass.getpass("新密碼（至少 12 個字元）：")
    confirmation = getpass.getpass("再次輸入新密碼：")
    if password != confirmation:
        print("[Error] 兩次輸入的密碼不同")
        return 1

    try:
        admin_id = reset_admin_password(username=username, new_password=password)
    except ValueError as exc:
        print(f"[Error] {exc}")
        return 1

    print(f"[OK] 管理員密碼已重設：id={admin_id}, username={username}")
    print("[OK] 該管理員既有登入 Session 已撤銷，請重新登入。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
