"""Read-only command-line verification for a registered validation dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

import pymysql


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from subsystems.validation_dataset.inspection import (
    FOUNDATION_DATASET_ID,
    inspect_dataset,
)


_DATABASE_PATTERN = re.compile(r"lu_test_dataset_[a-z0-9_]+")


def verify_dataset(arguments) -> dict[str, object]:
    if not _DATABASE_PATTERN.fullmatch(arguments.database):
        raise ValueError("database must match lu_test_dataset_[a-z0-9_]+")
    connection = pymysql.connect(host=arguments.host, port=arguments.port, user=arguments.user, password=arguments.password, database=arguments.database, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
    try:
        inspection = inspect_dataset(connection, arguments.dataset_id)
    finally:
        connection.close()
    payload = inspection.payload()
    payload["valid"] = inspection.verdict in {"pass", "blocked_as_expected"}
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--dataset-id", default=FOUNDATION_DATASET_ID)
    result = verify_dataset(parser.parse_args())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
