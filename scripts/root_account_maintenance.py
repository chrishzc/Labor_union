"""Interactive Windows host adapter for Access-owned root account maintenance."""

import getpass
import os
import subprocess
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pymysql

from scripts.nas_database_maintenance import MaintenanceBlocked, digest, load_settings
from subsystems.access.root_account_maintenance import (
    ChangeRootPassword,
    RenameRoot,
    RootMaintenanceCommitUnknown,
    RootMaintenanceRejected,
    apply_root_change,
    normalize_new_username,
    prepare_new_totp,
    read_commit_outcome,
    verify_root,
)
from subsystems.access.totp import (
    TOTP_TIME_STEP_SECONDS,
    TotpError,
    TotpSecretUnavailableError,
    generate_totp_secret,
    totp_cipher_from_settings,
)


ROOT = Path(__file__).resolve().parents[1]


def _target_settings(root: Path):
    env_file = root / ".env"
    # Reuse the shared MySQL and TLS settings parser. Root maintenance
    # needs neither backup credentials nor access to the backup directory.
    settings = load_settings(env_file, settings_file=None)
    runtime = settings["runtime"]
    if not all(runtime.get(key) for key in ("DB_HOST", "DB_DATABASE", "DB_USER")):
        raise RootMaintenanceRejected("請先在 .env 設定資料庫連線資訊（DB_HOST、DB_DATABASE、DB_USER）。")
    settings_keys = (
        "DB_HOST", "DB_PORT", "DB_DATABASE", "DB_USER", "DB_PASSWORD", "DB_PASSWORD_FILE",
        "DB_SSL_MODE", "DB_SSL_CA", "DB_SSL_CERT", "DB_SSL_KEY",
        "ACCESS_CONTROL_TOTP_KEYRING", "ACCESS_CONTROL_TOTP_ACTIVE_KEY_VERSION",
    )
    if any(key in os.environ and os.environ[key] != runtime.get(key) for key in settings_keys):
        raise RootMaintenanceRejected("目前執行環境與部署設定不同。")
    if bool(runtime.get("DB_SSL_CERT")) != bool(runtime.get("DB_SSL_KEY")):
        raise RootMaintenanceRejected("MySQL 用戶端憑證與私鑰須成對設定。")
    return settings


def _connection_factory(settings):
    runtime = settings["runtime"]
    password = runtime.get("DB_PASSWORD")
    if runtime.get("DB_PASSWORD_FILE"):
        password_file = Path(runtime["DB_PASSWORD_FILE"])
        if not password_file.is_absolute():
            password_file = settings["environment_file"].parent / password_file
        password = password_file.read_text(encoding="utf-8").strip()
    if not password:
        raise RootMaintenanceRejected("未設定維護所需的資料庫憑證。")

    def connect():
        try:
            conn = pymysql.connect(
                host=settings["host"], port=settings["port"], database=settings["database"],
                user=runtime["DB_USER"], password=password, charset="utf8mb4",
                autocommit=False, connect_timeout=5, read_timeout=15, write_timeout=15,
                **settings["tls"],
            )
        except (pymysql.MySQLError, OSError):
            raise RootMaintenanceRejected("無法連線至 MySQL 資料庫，請確認服務狀態與連線設定。") from None
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT DATABASE(), UTC_TIMESTAMP(6)")
                target, database_time = cursor.fetchone()
                if target != settings["database"]:
                    raise RootMaintenanceRejected("資料庫回報的目標不符。")
                drift = datetime.now(timezone.utc) - database_time.replace(tzinfo=timezone.utc)
                if abs(drift.total_seconds()) >= TOTP_TIME_STEP_SECONDS:
                    raise RootMaintenanceRejected("Windows 與資料庫的時鐘偏差過大。")
            conn.rollback()
            return conn
        except BaseException:
            conn.close()
            raise

    return connect


def _require_stopped_runtime(root: Path) -> None:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(root / "scripts/launchers/manage_windows.ps1"),
         "-Action", "root-maintenance-check"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=30,
    )
    if result.returncode:
        raise RootMaintenanceRejected("無法確認管理服務已停止。請先選擇「2 停止全部」。")


def _secret(prompt: str) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass(prompt)


def _protected_display(message: str, *, prompt: str) -> str:
    # CONOUT$ writes directly to the interactive console, outside PowerShell
    # output capture. Clear the display after reading the operator response.
    try:
        with open("CONOUT$", "w", encoding="utf-8") as console:
            print(message, file=console, flush=True)
        return _secret(prompt)
    finally:
        subprocess.run(["cmd.exe", "/d", "/c", "cls"], check=False)


def _selected_change(cipher):
    print("1 修改登入帳號  2 修改密碼  3 重新綁定 TOTP  0 返回")
    choice = input("請選擇：").strip()
    if choice == "0":
        return None
    if choice == "1":
        return RenameRoot(normalize_new_username(input("新登入帳號：")))
    if choice == "2":
        password = _secret("新密碼：")
        if _secret("再次輸入新密碼：") != password or not 10 <= len(password) <= 256:
            raise RootMaintenanceRejected("兩次新密碼須一致，且為 10 至 256 個字元。")
        return ChangeRootPassword(password)
    if choice == "3":
        seed = generate_totp_secret()
        code = _protected_display(
            f"在新驗證器手動新增 Labor Union Admin（時間型），輸入金鑰：{seed}",
            prompt="新驗證器的 TOTP 動態碼：",
        )
        return prepare_new_totp(cipher, seed, code)
    raise RootMaintenanceRejected("未選到可用的 root 維運操作。")


def _interactive(root: Path) -> None:
    _require_stopped_runtime(root)
    env_file = root / ".env"
    settings = _target_settings(root)
    original = digest(env_file)
    runtime = settings["runtime"]
    cipher = totp_cipher_from_settings(
        runtime.get("ACCESS_CONTROL_TOTP_KEYRING") or "",
        runtime.get("ACCESS_CONTROL_TOTP_ACTIVE_KEY_VERSION") or "",
    )
    target = f"{settings['host']}:{settings['port']}/{settings['database']}"
    print(f"維護目標：{target}")
    if input(f"請輸入 ROOT {target} 確認目標：").strip() != f"ROOT {target}":
        return
    connect = _connection_factory(settings)
    grant = verify_root(
        connect, cipher, input("目前 root 帳號："),
        _secret("目前 root 密碼："), _secret("目前 TOTP 動態碼："),
    )
    change = _selected_change(cipher)
    if change is None:
        return
    print(f"目前安全版本：{grant.version}。維運識別碼：{grant.operation_id}")
    if input("輸入 Y 確認變更：").strip().upper() != "Y":
        return
    _require_stopped_runtime(root)
    if original != digest(env_file):
        raise RootMaintenanceRejected("部署設定已變更，請重新驗證維護目標。")
    try:
        recovery_codes = apply_root_change(connect, grant, change)
    except RootMaintenanceCommitUnknown:
        try:
            outcome = read_commit_outcome(connect, grant)
        except Exception:
            outcome = "unknown"
        messages = {
            "committed": "已確認變更提交。若未收到新復原碼，請維持維護狀態並走受控復原。",
            "unchanged": "已確認變更未提交。請重新驗證後再操作。",
            "unknown": "提交結果不明，請維持維護狀態並查核安全版本與稽核。",
        }
        raise RootMaintenanceRejected(messages[outcome]) from None
    if recovery_codes:
        try:
            _protected_display(
                "請將新復原碼保存至受保護的位置，每組限用一次。\n"
                + "\n".join(recovery_codes),
                prompt="保存後請按 Enter 清除復原碼：",
            )
        except (Exception, KeyboardInterrupt):
            raise RootMaintenanceRejected(
                "變更已提交。若未保存新復原碼，請維持維護狀態並走受控復原。"
            ) from None
    print("root 帳號變更已提交，既有 root 登入已撤銷。")


def main() -> int:
    if os.name != "nt" or not all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)):
        print("root 帳號維護需要 Windows 主機上的互動終端。", file=sys.stderr)
        return 1
    try:
        _interactive(ROOT)
    except (KeyboardInterrupt, EOFError):
        print("互動已中斷。若已確認提交，請查核安全版本與稽核。", file=sys.stderr)
        return 1
    except (RootMaintenanceRejected, MaintenanceBlocked) as error:
        print(str(error), file=sys.stderr)
        return 1
    except (TotpError, TotpSecretUnavailableError, getpass.GetPassWarning):
        print("無法使用目前的驗證器金鑰或安全輸入介面。", file=sys.stderr)
        return 1
    except Exception:
        print("root 維護停止。請核對維護設定、安全版本與稽核。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
