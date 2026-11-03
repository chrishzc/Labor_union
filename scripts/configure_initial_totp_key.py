"""Explicitly initialize a persistent TOTP key for an empty local account database."""
from __future__ import annotations

import argparse
from io import StringIO
import json
import os
from pathlib import Path
import re
import tempfile

from cryptography.fernet import Fernet
from dotenv import dotenv_values, load_dotenv
import pymysql

from subsystems.access.totp import TotpError, totp_cipher_from_settings


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
KEYRING = "ACCESS_CONTROL_TOTP_KEYRING"
ACTIVE = "ACCESS_CONTROL_TOTP_ACTIVE_KEY_VERSION"


class ConfigurationBlocked(ValueError):
    """Only safe operator messages may be supplied here."""


def _check_overrides(settings):
    names = set(settings) | set(os.environ)
    for name in names:
        if name in {"APP_ENV", "DEPLOYMENT_PROFILE", KEYRING, ACTIVE} or name.startswith("DB_"):
            if name in os.environ and os.environ[name] != (settings.get(name) or ""):
                raise ConfigurationBlocked("程序環境變數與 .env 不同，請先排除設定覆寫後重試。")


def _runtime(env_file):
    load_dotenv(env_file, override=False)
    from infrastructure.mysql.mysql_adapter import _database_config_from_environment, get_connection
    config = _database_config_from_environment()
    if os.getenv("APP_ENV", "").lower() not in {"development", "dev", "local", "test"}:
        raise ConfigurationBlocked("僅允許本機 development／local／test 環境。")
    if (str(config["host"]).lower() not in {"localhost", "127.0.0.1", "::1"}
            or os.getenv("DEPLOYMENT_PROFILE", "").lower() == "nas"):
        raise ConfigurationBlocked("僅允許本機資料庫，不處理 NAS 或遠端主機。")
    database = config["database"]
    if database != "union_db" and not re.fullmatch(r"lu_test_[a-z0-9_]+", database):
        raise ConfigurationBlocked("僅允許 union_db 或 lu_test_* 資料庫。")
    return database, get_connection


def _require_empty_accounts(factory, database):
    conn = factory()
    try:
        if str(getattr(conn, "host", "")).lower() not in {"localhost", "127.0.0.1", "::1"}:
            raise ConfigurationBlocked("實際連線不是本機資料庫，已停止。")
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            conn.begin()
            cursor.execute("SELECT DATABASE() AS database_name")
            if cursor.fetchone()["database_name"] != database:
                raise ConfigurationBlocked("實際資料庫與設定目標不同，已停止。")
            for table in ("admin_users", "admin_root_account", "admin_totp_factors",
                          "admin_totp_recovery_codes", "admin_sessions",
                          "admin_password_login_challenges", "admin_mfa_enrollment_challenges"):
                cursor.execute(f"SELECT 1 FROM `{table}` LIMIT 1")
                if cursor.fetchone() is not None:
                    raise ConfigurationBlocked("已有帳號或驗證資料，拒絕建立或替換金鑰；請恢復原金鑰。")
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


def _persist(env_file, original):
    text = original.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    # Replace all duplicates so dotenv and launcher readers see the same settings.
    text = re.sub(r"(?m)^[ \t]*(?:export[ \t]+)?ACCESS_CONTROL_TOTP_(?:KEYRING|ACTIVE_KEY_VERSION)[ \t]*=[^\r\n]*(?:\r?\n|$)", "", text)
    if text and not text.endswith(("\n", "\r")):
        text += newline
    text += f"{KEYRING}=v1:{Fernet.generate_key().decode('ascii')}{newline}{ACTIVE}=v1{newline}"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=env_file.parent, prefix=".env.totp-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        if env_file.read_bytes() != original:
            raise ConfigurationBlocked(".env 已被其他程序修改，未覆寫，請重新檢查。")
        os.replace(temporary, env_file)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None, *, confirm=input, env_file=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="確認空帳號資料庫後，建立並保存金鑰")
    args = parser.parse_args(argv)
    env_file = Path(env_file) if env_file is not None else ENV_FILE
    try:
        original = env_file.read_bytes()
        settings = dotenv_values(stream=StringIO(original.decode("utf-8")))
        _check_overrides(settings)
        try:
            totp_cipher_from_settings(settings.get(KEYRING) or "", settings.get(ACTIVE) or "")
        except TotpError:
            pass
        else:
            print(json.dumps({"status": "passed", "changed": False, "message": "金鑰格式有效，已保留；請重新啟動網站。"}, ensure_ascii=False))
            return 0
        database, factory = _runtime(env_file)
        _require_empty_accounts(factory, database)
        print(json.dumps({"status": "preview", "database": database, "changed": False}, ensure_ascii=False))
        if not args.apply:
            return 0
        print("請先停止網站。只更新本機 .env 的 TOTP 金鑰，不修改資料庫；金鑰不會顯示，請妥善保管 .env。")
        phrase = f"INITIALIZE TOTP {database}"
        if confirm(f"確認請輸入 {phrase}：").strip() != phrase:
            print(json.dumps({"status": "cancelled", "changed": False}))
            return 1
        _require_empty_accounts(factory, database)
        _persist(env_file, original)
        print(json.dumps({"status": "passed", "changed": True, "message": "金鑰已保存。請完整重新啟動網站，再建立 root 並綁定 TOTP。"}, ensure_ascii=False))
        return 0
    except ConfigurationBlocked as error:
        print(json.dumps({"status": "blocked", "message": str(error)}, ensure_ascii=False))
        return 2
    except (EOFError, KeyboardInterrupt):
        print(json.dumps({"status": "cancelled", "changed": False}))
        return 1
    except Exception:
        print(json.dumps({"status": "blocked", "message": "設定未完成；請確認 .env、資料庫結構及檔案權限。不會輸出金鑰或連線憑證。"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
