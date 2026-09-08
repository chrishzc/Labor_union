"""Prepare the isolated Issue 218 browser fixture with a real line-agent login.

The browser acceptance needs an actual persisted, non-system-admin Session.  This
script deliberately creates that account only in a new ``lu_test_*`` schema and
writes its one-run credentials to a mode-600 file supplied by the operator.  It
does not launch a service, issue a Session, or alter browser storage: the normal
two-step Login page must create the session.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path
import re
import secrets
import stat
import sys

import pymysql
from cryptography.fernet import Fernet

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.bootstrap_disposable_mysql_schema import bootstrap
from subsystems.access.authentication_session import hash_admin_password
from subsystems.access.totp import TotpSecretCipher, generate_totp_secret


_DATABASE_PATTERN = re.compile(r"lu_test_[a-z0-9_]+\Z")
_USERNAME = "issue218-browser-line-agent"
_CASES = (
    ("SYN-218-NAME", None, date(2026, 9, 10), 5),
    ("SYN-218-START", "合成開始日案", None, 5),
    ("SYN-218-DAYS", "合成天數案", date(2026, 9, 12), None),
    ("SYN-218-BOTH", None, None, None),
)


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", default=os.getenv("DB_PASSWORD", ""))
    parser.add_argument("--database", required=True)
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--credential-file", required=True, type=Path)
    parser.add_argument(
        "--schema-ready",
        action="store_true",
        help="Seed a schema that was already created by the guarded bootstrap dry-run/apply flow.",
    )
    return parser.parse_args()


def _validate(arguments: argparse.Namespace) -> str:
    database = arguments.database.strip()
    if not _DATABASE_PATTERN.fullmatch(database):
        raise ValueError("database must match lu_test_*")
    if arguments.confirm_database != database:
        raise ValueError("confirm-database must exactly match database")
    credential_file = arguments.credential_file.resolve()
    if credential_file.exists():
        raise ValueError("credential-file already exists; refusing to overwrite it")
    if credential_file.parent != Path("/private/tmp"):
        raise ValueError("credential-file must be directly under /private/tmp")
    return database


def _bootstrap(arguments: argparse.Namespace) -> None:
    dry_run_arguments = argparse.Namespace(**vars(arguments))
    dry_run_arguments.base_only = False
    dry_run_arguments.max_schema_part = None
    # ``bootstrap`` is deliberately the same absent-schema-only guarded surface
    # used by the HTTP integration acceptance.
    bootstrap(dry_run_arguments)


def _seed(arguments: argparse.Namespace, database: str) -> dict[str, str | list[str]]:
    password = secrets.token_urlsafe(24)
    totp_secret = generate_totp_secret()
    keyring_key = Fernet.generate_key().decode("ascii")
    cipher = TotpSecretCipher({"issue218": keyring_key}, "issue218")
    encrypted = cipher.encrypt(totp_secret)
    connection = pymysql.connect(
        host=arguments.host,
        port=arguments.port,
        user=arguments.user,
        password=arguments.password,
        database=database,
        charset="utf8mb4",
        autocommit=False,
    )
    try:
        with connection.cursor() as cursor:
            for case_no, name, start_date, service_days in _CASES:
                cursor.execute(
                    "INSERT INTO clients (case_no,name,identity_status) VALUES (%s,%s,%s)",
                    (case_no, name, "一般"),
                )
                client_id = int(cursor.lastrowid)
                cursor.execute(
                    """
                    INSERT INTO orders (
                        case_no,client_id,status,lifecycle_version,start_date,end_date,
                        service_days,service_hours_per_day,floor_fee,actual_start_date,actual_end_date
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,NULL)
                    """,
                    (
                        case_no,
                        client_id,
                        "待補件",
                        7,
                        start_date,
                        date(2026, 10, 31),
                        service_days,
                        8,
                        "123.00",
                    ),
                )
            cursor.execute(
                """
                INSERT INTO admin_users (username,password_hash,display_name,linked_line_user_id,role)
                VALUES (%s,%s,%s,NULL,%s)
                """,
                (
                    _USERNAME,
                    hash_admin_password(password),
                    "Issue 218 Browser Line Agent",
                    "line_agent",
                ),
            )
            admin_id = int(cursor.lastrowid)
            cursor.execute(
                """
                INSERT INTO admin_totp_factors (
                    admin_user_id,factor_state,seed_ciphertext,encryption_key_version,
                    enrollment_challenge_hash,enrollment_expires_at,activated_at,created_at,updated_at
                ) VALUES (%s,'active',%s,%s,%s,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6),UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))
                """,
                (admin_id, encrypted.ciphertext, encrypted.key_version, "issue218-browser-fixture"),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return {
        "username": _USERNAME,
        "password": password,
        "totp_secret": totp_secret,
        "totp_keyring": f"issue218:{keyring_key}",
        "totp_key_version": "issue218",
        "cases": [case_no for case_no, *_rest in _CASES],
    }


def _write_credentials(path: Path, payload: dict[str, str | list[str]], database: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"database": database, **payload}, handle, ensure_ascii=False)
            handle.write("\n")
    finally:
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except FileNotFoundError:
            pass


def main() -> int:
    arguments = _parse_arguments()
    database = _validate(arguments)
    if not arguments.schema_ready:
        _bootstrap(arguments)
    credentials = _seed(arguments, database)
    _write_credentials(arguments.credential_file, credentials, database)
    print(
        json.dumps(
            {
                "status": "prepared",
                "database": database,
                "credential_file": str(arguments.credential_file),
                "actor_role": "line_agent",
                "actor_is_root": False,
                "session_issued": False,
                "cases": credentials["cases"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
