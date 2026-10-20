"""Plan NAS security settings; --apply explicitly installs fixed runtime grants.

No schema reset or business-row migration is performed here. Existing databases
must complete the canonical preserve-data upgrade first, with writers stopped
and source backup retained. Credentials are read from files, never arguments.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pymysql

from infrastructure.mysql.nas_permissions import (
    PROFILES, install_permissions, legacy_account_plan, permission_plan, retire_legacy_account,
)


def configure(settings: Path, *, apply=False):
    from scripts.compact_fresh_schema import load_compact_plan
    from scripts.verify_validation_schema_manifest import verify_database_objects
    schema_plan = load_compact_plan()
    config = json.loads(settings.read_text(encoding="utf-8"))
    if config.get("format") != "nas-db-security-settings/v1":
        raise ValueError("invalid NAS security settings")
    database = config["database"]
    connection = pymysql.connect(host=config["host"], port=int(config.get("port", 3306)),
        user=config["admin_user"], password=Path(config["admin_password_file"]).read_text(encoding="utf-8").strip(),
        database=database, charset="utf8mb4", autocommit=True, connect_timeout=5, read_timeout=30,
        ssl={"ca": config["ca_file"], "check_hostname": True})
    try:
        with connection.cursor() as cursor:
            if verify_database_objects(cursor, database, schema_plan["expected"]):
                raise ValueError("NAS business schema is incomplete")
        plan = permission_plan(connection, database)
        old_account = legacy_account_plan(connection, database)
        if apply:
            credentials = {profile: Path(config["password_files"][profile]).read_text(encoding="utf-8").strip()
                           for profile in PROFILES}
            # Check credentials for existing identities before any non-transactional
            # CREATE/GRANT/REVOKE. A wrong settings file must not partly change grants.
            for profile in PROFILES:
                if plan["accounts"][profile] not in plan["existing_accounts"]:
                    continue
                probe = pymysql.connect(host=config["host"], port=int(config.get("port", 3306)),
                    user=plan["accounts"][profile], password=credentials[profile], database=database,
                    connect_timeout=5, ssl={"ca": config["ca_file"], "check_hostname": True})
                probe.close()
            plan = install_permissions(connection, database, credentials)
            # Confirm each actual credential works before retiring the old identity.
            for profile in PROFILES:
                probe = pymysql.connect(host=config["host"], port=int(config.get("port", 3306)),
                    user=plan["accounts"][profile], password=credentials[profile], database=database,
                    connect_timeout=5, ssl={"ca": config["ca_file"], "check_hostname": True})
                try:
                    from infrastructure.mysql.nas_permissions import verify_runtime_permissions
                    verify_runtime_permissions(probe, profile, database,
                        expected_tables=plan["tables"], expected_views=plan["views"])
                finally:
                    probe.close()
            retire_legacy_account(connection, database)
        return {"status": "applied" if apply else "planned", "database": database,
                "procedure_states": plan["procedures"], "legacy_account_present": old_account,
                "business_rows_changed": False}
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(configure(args.settings, apply=args.apply), ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as error:
        # Driver errors can contain SQL, credential paths or other connection data.
        print(json.dumps({"status": "blocked", "error_type": type(error).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
