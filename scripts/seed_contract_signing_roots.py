"""Seed only explicitly declared contract-signing master source facts."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys

import pymysql


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from subsystems.validation_dataset.staff_master_source import (
    StaffMasterSourceFact,
    apply_staff_master_source,
)


_DATABASE_PATTERN = re.compile(r"lu_test_dataset_[a-z0-9_]+")
_DEFAULT_SOURCE = Path("validation/external_inputs/contract_signing_staff_master_v1.json")


def seed(arguments) -> dict[str, object]:
    _require_database(arguments.database, arguments.confirm_database)
    source = _load_source(arguments.source)
    connection = _connect(arguments)
    try:
        with connection.cursor() as cursor:
            staff_id = apply_staff_master_source(cursor, source)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return {"database": arguments.database, "staff_id": staff_id}


def _require_database(database: str, confirmation: str) -> None:
    if not _DATABASE_PATTERN.fullmatch(database):
        raise ValueError("database must match lu_test_dataset_[a-z0-9_]+")
    if confirmation != database:
        raise ValueError("confirmation must exactly match database")


def _load_source(path: Path) -> StaffMasterSourceFact:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contract") != "labor-union-validation-staff-master/v1":
        raise ValueError("unsupported staff-master source contract")
    staff = payload.get("staff")
    if not isinstance(staff, dict):
        raise ValueError("staff-master source is missing")
    return StaffMasterSourceFact(
        str(staff["name"]), str(staff["identity_card"]), str(staff["phone"]),
        date.fromisoformat(str(staff["birthday"])), str(staff["city"]),
        int(staff["care_babies"]),
    )


def _connect(arguments):
    return pymysql.connect(
        host=arguments.host, port=arguments.port, user=arguments.user,
        password=arguments.password, database=arguments.database,
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--source", type=Path, default=_DEFAULT_SOURCE)
    print(json.dumps(seed(parser.parse_args()), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
