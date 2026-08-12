"""Seed one fixed validation dataset through canonical domain workflows only."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time
import json
from pathlib import Path
import re
import sys

import pymysql


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from domains.bootstrap.case_architecture import (
    CaseArchitectureBootstrapIntent,
    ClientPaymentTermsRootFacts,
)
from domains.case_import.case_import import (
    CaseImportIntent,
    ClientImportAttribute,
    ImportedOrderRootFacts,
)
from infrastructure.mysql.case_import_repository import (
    CaseImportMySqlUnitOfWork,
    MySqlCaseImportRepository,
)
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.case_import.case_import_workflow import ApplyCaseImport, CaseImportWorkflow


DATASET_CONTRACT = "labor-union-validation-dataset/v1"
DEFAULT_MANIFEST = PROJECT_ROOT / "validation" / "datasets" / "dataset_v1_foundation.json"
_DATASET_DATABASE_PATTERN = re.compile(r"lu_test_dataset_[a-z0-9_]+")
_CLEAN_TABLES = (
    "clients", "orders", "client_finance_accounts", "client_payment_terms",
    "client_payment_terms_events", "payroll_case_accounts",
    "case_payroll_rate_policy_snapshots", "scheduling_aggregates",
    "case_architecture_bootstrap_events", "case_import_events",
    "case_import_receipts", "application_command_claims",
)


def load_dataset(path: Path) -> dict[str, object]:
    dataset = json.loads(path.read_text(encoding="utf-8"))
    if dataset.get("contract") != DATASET_CONTRACT:
        raise ValueError("unsupported validation dataset contract")
    if not isinstance(dataset.get("root_case"), dict):
        raise ValueError("dataset root_case is missing")
    return dataset


def require_dataset_database(database: str) -> str:
    if not _DATASET_DATABASE_PATTERN.fullmatch(database):
        raise ValueError("database must match lu_test_dataset_[a-z0-9_]+")
    return database


def connect(arguments):
    return pymysql.connect(
        host=arguments.host, port=arguments.port, user=arguments.user,
        password=arguments.password, database=require_dataset_database(arguments.database),
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, autocommit=False,
    )


def require_empty_dataset(connection) -> None:
    with connection.cursor() as cursor:
        occupied = [table for table in _CLEAN_TABLES if _table_count(cursor, table)]
    if occupied:
        raise RuntimeError("dataset database is not empty: " + ", ".join(occupied))


def _table_count(cursor, table_name: str) -> int:
    cursor.execute(f"SELECT COUNT(*) AS count FROM `{table_name}`")
    return int(cursor.fetchone()["count"])


def build_intent(dataset: dict[str, object]) -> CaseImportIntent:
    root = dataset["root_case"]
    attributes = root["client_attributes"]
    order = root["order_root_facts"]
    terms = root["client_payment_terms"]
    case_no = str(root["case_no"])
    return CaseImportIntent(
        case_no,
        _client_attributes(attributes),
        ImportedOrderRootFacts(
            case_no, int(order["service_days"]), int(order["service_hours_per_day"]),
            _date(order["planned_start_date"]), _date(order["planned_end_date"]),
            _time(order["service_start_time"]), _time(order["service_end_time"]),
            int(order["service_end_day_offset"]),
        ),
        CaseArchitectureBootstrapIntent(
            case_no,
            ClientPaymentTermsRootFacts(
                str(terms["policy_version"]), MoneyNTD(int(terms["client_hourly_rate_ntd"])),
                int(terms["deposit_service_days"]), _date(terms["deposit_due_date"]),
                _date(terms["first_payment_due_date"]), _optional_date(terms["second_payment_due_date"]),
            ),
            str(root["payroll_policy_version"]),
        ),
    )


def _client_attributes(values: dict[str, object]) -> tuple[ClientImportAttribute, ...]:
    return tuple(
        ClientImportAttribute(name, _attribute_value(name, value))
        for name, value in sorted(values.items())
    )


def _attribute_value(name: str, value: object):
    return datetime.fromisoformat(str(value)) if name == "created_at" else value


def _date(value: object) -> date:
    return date.fromisoformat(str(value))


def _optional_date(value: object) -> date | None:
    return None if value is None else _date(value)


def _time(value: object) -> time:
    return time.fromisoformat(str(value))


def apply_dataset(connection, dataset: dict[str, object]):
    intent = build_intent(dataset)
    case_no = intent.case_no
    workflow = CaseImportWorkflow(
        MySqlCaseImportRepository(connection),
        lambda: CaseImportMySqlUnitOfWork(connection),
    )
    preview = workflow.preview(intent, CorrelationId(f"dataset-preview-{case_no}"))
    command = ApplyCaseImport(
        intent, ExpectedVersion(0), preview.fingerprint,
        IdempotencyKey(f"dataset-case-import-{case_no}"),
        ActorContext("validation-dataset-seed"), "seed fixed validation root facts",
        CorrelationId(f"dataset-case-import-{case_no}"),
    )
    first = workflow.apply(command)
    if workflow.apply(command) != first:
        raise RuntimeError("case import replay returned a different receipt")
    return first


def seed(arguments) -> dict[str, object]:
    if arguments.confirm_database != arguments.database:
        raise ValueError("confirmation must exactly match database")
    dataset = load_dataset(arguments.manifest)
    connection = connect(arguments)
    try:
        require_empty_dataset(connection)
        receipt = apply_dataset(connection, dataset)
    finally:
        connection.close()
    return {
        "database": arguments.database,
        "dataset_id": dataset["dataset_id"],
        "case_no": receipt.case_no,
        "client_id": receipt.client_id,
        "import_event_id": receipt.import_event_id,
        "bootstrap_event_id": receipt.bootstrap_event_id,
        "replay_verified": True,
    }


def seed_into_integrated_dataset(arguments) -> dict[str, object]:
    """Append this manifest only when its root case is absent or identical."""
    if arguments.confirm_database != arguments.database:
        raise ValueError("confirmation must exactly match database")
    dataset = load_dataset(arguments.manifest)
    connection = connect(arguments)
    try:
        existing = _existing_root_case(connection, str(dataset["root_case"]["case_no"]))
        if existing is not None:
            _require_matching_root_case(existing, dataset)
            return {
                "database": arguments.database,
                "dataset_id": dataset["dataset_id"],
                "case_no": existing["case_no"],
                "client_id": int(existing["client_id"]),
                "result": "existing",
                "replay_verified": True,
            }
        receipt = apply_dataset(connection, dataset)
    finally:
        connection.close()
    return {
        "database": arguments.database,
        "dataset_id": dataset["dataset_id"],
        "case_no": receipt.case_no,
        "client_id": receipt.client_id,
        "import_event_id": receipt.import_event_id,
        "bootstrap_event_id": receipt.bootstrap_event_id,
        "result": "created",
        "replay_verified": True,
    }


def _existing_root_case(connection, case_no: str) -> dict[str, object] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT order_row.case_no,order_row.client_id,client.name,client.phone "
            "FROM orders order_row INNER JOIN clients client ON client.id=order_row.client_id "
            "WHERE order_row.case_no=%s",
            (case_no,),
        )
        return cursor.fetchone()


def _require_matching_root_case(existing: dict[str, object], dataset: dict[str, object]) -> None:
    root = dataset["root_case"]
    attributes = root["client_attributes"]
    if (
        existing["case_no"] != root["case_no"]
        or existing["name"] != attributes["name"]
        or existing["phone"] != attributes["phone"]
    ):
        raise RuntimeError("existing validation root differs from manifest; rebuild required")


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
