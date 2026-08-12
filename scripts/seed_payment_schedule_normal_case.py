"""Seed the numeric normal payment-and-scheduling case through Case Import."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.seed_validation_dataset import (
    apply_dataset,
    connect,
    load_dataset,
    require_dataset_database,
)


DEFAULT_MANIFEST = PROJECT_ROOT / "validation" / "datasets" / "dataset_v1_payment_schedule_normal.json"


def seed(arguments) -> dict[str, object]:
    database = require_dataset_database(arguments.database)
    if arguments.confirm_database != database:
        raise ValueError("confirmation must exactly match database")
    dataset = load_dataset(arguments.manifest)
    case_no = str(dataset["root_case"]["case_no"])
    connection = connect(arguments)
    try:
        existing = _existing_case(connection, case_no)
        if existing is not None:
            if not _matches_manifest(existing, dataset):
                raise RuntimeError(
                    "existing normal scenario root differs from manifest; rebuild required"
                )
            return {"database": database, "case_no": case_no, "result": "existing"}
        receipt = apply_dataset(connection, dataset)
    finally:
        connection.close()
    return {
        "database": database,
        "case_no": receipt.case_no,
        "client_id": receipt.client_id,
        "result": "created",
        "replay_verified": True,
    }


def _existing_case(connection, case_no: str) -> dict[str, object] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT order_row.case_no,client.name,client.phone "
            "FROM orders order_row JOIN clients client ON client.id=order_row.client_id "
            "WHERE order_row.case_no=%s",
            (case_no,),
        )
        return cursor.fetchone()


def _matches_manifest(existing: dict[str, object], dataset: dict[str, object]) -> bool:
    root = dataset["root_case"]
    client = root["client_attributes"]
    return (
        existing["case_no"] == root["case_no"]
        and existing["name"] == client["name"]
        and existing["phone"] == client["phone"]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    print(json.dumps(seed(parser.parse_args()), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
