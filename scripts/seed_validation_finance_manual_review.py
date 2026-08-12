"""Seed one unresolved bank row through the canonical finance-import intake."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.identities import ActorContext, IdempotencyKey
from subsystems.anomalies.finance_import_anomaly_consumer import (
    consume_finance_import_anomaly_events,
)
from subsystems.finance_import.ingestion import ingest_finance_workbook


_DATABASE_PATTERN = re.compile(r"lu_test_dataset_[a-z0-9_]+")
_INGESTION_KEY_PREFIX = "validation-dataset-v1-finance-manual-review"


def seed(scenario_id: str, *, incoming_amount: int | None = None) -> dict[str, object]:
    _require_dataset_database()
    existing_batch_identity = _existing_batch_identity(scenario_id)
    if existing_batch_identity is not None:
        delivery = _deliver_anomaly_projection()
        return _verify_seeded_row(existing_batch_identity, delivery.delivered_count)
    with TemporaryDirectory(prefix="lu-validation-finance-") as directory:
        workbook = _write_unresolved_workbook(Path(directory), scenario_id, incoming_amount)
        receipt = _ingest_with_replay(workbook, scenario_id)
    delivery = _deliver_anomaly_projection()
    return _verify_seeded_row(receipt.batch_identity, delivery.delivered_count)


def _existing_batch_identity(scenario_id: str) -> str | None:
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT contract.batch_identity FROM finance_import_ingestion_receipts receipt "
                "INNER JOIN finance_import_batch_contracts contract ON contract.batch_id=receipt.batch_id "
                "WHERE receipt.idempotency_key=%s",
                (_ingestion_key(scenario_id),),
            )
            row = cursor.fetchone()
    finally:
        connection.close()
    return None if row is None else str(row["batch_identity"])


def _require_dataset_database() -> None:
    from infrastructure.mysql.mysql_adapter import DB_CONFIG

    if not _DATABASE_PATTERN.fullmatch(str(DB_CONFIG["database"])):
        raise ValueError("DB_DATABASE must match lu_test_dataset_[a-z0-9_]+")


def _write_unresolved_workbook(
    directory: Path,
    scenario_id: str,
    incoming_amount: int | None,
) -> Path:
    workbook = directory / f"validation-manual-review-{_safe_scenario_id(scenario_id)}.xlsx"
    debit, credit = _bank_amount_columns(incoming_amount)
    rows = [
        ["說明"],
        ["序號", "交易日期", "交易時間", "帳務日期", "摘要", "支出金額", "存入金額", "帳戶餘額", "備註"],
        ["0001", "2026/08/04", "09:08:07", "2026/08/04", "轉帳", debit, credit, "9000", f"驗收用未分類銀行流水:{scenario_id}"],
    ]
    pd.DataFrame(rows).to_excel(workbook, sheet_name="交易明細", index=False, header=False)
    return workbook


def _ingest_with_replay(workbook: Path, scenario_id: str):
    actor = ActorContext("validation-dataset-seed")
    key = IdempotencyKey(_ingestion_key(scenario_id))
    receipt = ingest_finance_workbook(str(workbook), key, actor)
    if ingest_finance_workbook(str(workbook), key, actor) != receipt:
        raise RuntimeError("finance import replay returned a different receipt")
    return receipt


def _deliver_anomaly_projection():
    connection = get_connection()
    try:
        result = consume_finance_import_anomaly_events(connection)
    finally:
        connection.close()
    if result.failed_count:
        raise RuntimeError("finance import anomaly projection failed")
    return result


def _verify_seeded_row(batch_identity: str, delivered_count: int) -> dict[str, object]:
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT CONCAT('finance-import-row:',finance_import_row_id) AS row_identity,"
                "classification_type,disposition FROM "
                "finance_import_classification_events WHERE batch_id=("
                "SELECT batch_id FROM finance_import_batch_contracts "
                "WHERE batch_identity=%s)",
                (batch_identity,),
            )
            row = cursor.fetchone()
            cursor.execute(
                "SELECT workflow_status,predicate_active FROM "
                "anomaly_current_alerts WHERE definition_code=%s "
                "AND source_identity=%s",
                ("finance_import_manual_review", row["row_identity"]),
            )
            alert = cursor.fetchone()
    finally:
        connection.close()
    if row is None or alert is None:
        raise RuntimeError("finance manual-review scenario was not projected")
    return {
        "batch_identity": batch_identity,
        "row_identity": row["row_identity"],
        "classification_type": row["classification_type"],
        "disposition": row["disposition"],
        "workflow_status": alert["workflow_status"],
        "predicate_active": int(alert["predicate_active"]),
        "anomaly_events_delivered": delivered_count,
    }


def _ingestion_key(scenario_id: str) -> str:
    return f"{_INGESTION_KEY_PREFIX}:{_safe_scenario_id(scenario_id)}"


def _safe_scenario_id(scenario_id: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "-", scenario_id).strip("-")
    if not value:
        raise ValueError("scenario_id must contain letters, numbers, underscores, or hyphens")
    return value[:100]


def _bank_amount_columns(incoming_amount: int | None) -> tuple[str, str]:
    if incoming_amount is None:
        return "300", ""
    if incoming_amount <= 0:
        raise ValueError("incoming_amount must be positive")
    return "", str(incoming_amount)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--incoming-amount", type=int)
    arguments = parser.parse_args()
    print(seed(arguments.scenario_id, incoming_amount=arguments.incoming_amount))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
