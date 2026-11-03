"""Preview or explicitly reset only an unused, locally configured initial root."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json

from api.dependencies.admin_auth import get_access_control_connection_factory
from infrastructure.mysql.mysql_adapter import _database_config_from_environment
from subsystems.access.incomplete_root_reset import (
    IncompleteRootResetError, preview_incomplete_root_reset, reset_incomplete_root_setup,
)


MESSAGES = {
    "development_required": "僅允許 development／local／test 環境。",
    "local_database_required": "僅允許本機 union_db 或 lu_test_* 資料庫。",
    "loopback_required": "僅允許 localhost 資料庫，不處理 NAS 或遠端資料庫。",
    "database_mismatch": "實際連線資料庫與確認目標不同，已停止。",
    "root_missing": "目前沒有 root，請直接開啟網站建立帳號。",
    "root_already_used": "root 已被使用、變更過安全設定或建立過登入 session，拒絕初始重置。",
    "other_admins_exist": "已有其他管理員，拒絕初始重置。",
    "root_already_enrolled": "root 已綁定或使用過 TOTP，拒絕初始重置。",
    "external_reference": "存在非預期的帳號引用，拒絕初始重置。",
    "root_has_business_references": "root 已被業務資料引用，拒絕初始重置。",
    "admin_version_conflict": "帳號狀態已變更，請重新檢查，未重試。",
}


def main(argv=None, *, confirm=input) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="檢查並要求確認後清除未完成的初始 root")
    args = parser.parse_args(argv)
    try:
        config = _database_config_from_environment()
        if str(config["host"]).lower() not in {"127.0.0.1", "localhost", "::1"}:
            raise IncompleteRootResetError("loopback_required")
        database = config["database"]
        factory = get_access_control_connection_factory()
        preview = preview_incomplete_root_reset(connection_factory=factory, target_database=database)
        print(json.dumps({"status": "preview", **asdict(preview)}, ensure_ascii=False))
        if not args.apply:
            return 0
        print("請先停止網站服務。只清除未完成的初始 root 及待綁定資料，保留業務資料、稽核紀錄及金鑰。")
        phrase = f"RESET ROOT {database} {preview.account_id}"
        if confirm(f"確認請輸入 {phrase}：").strip() != phrase:
            print(json.dumps({"status": "cancelled", "changed": False}))
            return 1
        reset_incomplete_root_setup(connection_factory=factory, target_database=database,
            expected_account_id=preview.account_id, expected_version=preview.version)
        print(json.dumps({"status": "passed", "root_setup_required": True}, ensure_ascii=False))
        return 0
    except IncompleteRootResetError as error:
        print(json.dumps({"status": "blocked", "code": error.code, "message": MESSAGES[error.code]}, ensure_ascii=False))
        return 2
    except (EOFError, KeyboardInterrupt):
        print(json.dumps({"status": "cancelled", "changed": False}))
        return 1
    except Exception:
        print(json.dumps({"status": "blocked", "message": "檢查或重置失敗；請確認本機資料庫結構與管理權限。未完成的交易會回滾。"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
