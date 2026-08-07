"""Application-owned transaction for importing one finance workbook."""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

from scripts.imports.finance_statement_normalizer import normalize_workbook
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.finance_import.identity_maps import load_finance_identity_maps
from services.finance_import_dispatch import dispatch_finance_import_row
from services.finance_import_review_alerts import (
    project_finance_import_review_alert,
)
from subsystems.finance_import.staging import stage_finance_rows
from domains.client_finance.order_amount_calculation import calculate_order_amounts


PAYMENT_STAGES = (
    ("deposit", "deposit_received"),
    ("first_payment", "first_payment_received"),
    ("second_payment", "second_payment_received"),
)


def allocate_receipt(
    receivables: dict[str, Any],
    current_state: dict[str, Any],
    amount: Any,
) -> list[tuple[str, Decimal]]:
    """Compatibility helper for the existing client-ledger unit contract."""
    remaining = Decimal(str(amount))
    assert remaining > 0
    allocations: list[tuple[str, Decimal]] = []
    for stage, received_key in PAYMENT_STAGES:
        stage_remaining = Decimal(str(receivables[stage])) - Decimal(
            str(current_state[received_key])
        )
        if stage_remaining <= 0:
            continue
        allocation = min(remaining, stage_remaining)
        allocations.append((stage, allocation))
        remaining -= allocation
        if remaining == 0:
            return allocations
    raise ValueError("receipt exceeds the remaining client receivable")


def build_snapshot_plan(order: dict[str, Any]) -> dict[str, Any] | None:
    """Compatibility projection for historical snapshot tests."""
    if order.get("deposit_service_days") is None:
        return None
    service_start_date = order.get("actual_start_date") or order.get("start_date")
    if not service_start_date or not order.get("deposit_date"):
        return None
    return calculate_order_amounts(
        {
            "case_no": order["case_no"],
            "service_days": order.get("service_days"),
            "service_hours_per_day": order.get("service_hours_per_day"),
            "identity_status": order.get("identity_status"),
            "client_floor_fee": order.get("floor_fee", 0),
            "service_start_date": service_start_date,
            "actual_completion_date": order.get("actual_end_date"),
        },
        collection_schedule={
            "deposit_service_days": order["deposit_service_days"],
            "deposit_due_date": order["deposit_date"],
        },
    )


def _order_for_snapshot(cursor: Any, case_no: str) -> dict[str, Any] | None:
    """Compatibility query; identity eligibility remains clients-owned."""
    cursor.execute(
        """SELECT o.case_no, o.service_days, o.service_hours_per_day,
                  c.identity_status, o.floor_fee, o.deposit_date,
                  o.deposit_service_days, o.start_date, o.actual_start_date,
                  o.actual_end_date
           FROM orders o
           JOIN clients c ON c.id = o.client_id
           WHERE o.case_no = %s
           FOR UPDATE""",
        (case_no,),
    )
    return cursor.fetchone()


def import_finance_workbook(
    excel_path: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Normalize, stage, dispatch and project one workbook atomically."""
    assert callable(get_connection), "database connection factory is required"
    if not isinstance(excel_path, str) or not excel_path.strip():
        raise ValueError("excel_path is required")
    if not isinstance(dry_run, bool):
        raise TypeError("dry_run must be a boolean")
    source_path = os.path.abspath(excel_path)
    normalized_result = normalize_workbook(source_path)
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            identity_maps = load_finance_identity_maps(cursor)
            staging = stage_finance_rows(
                cursor,
                normalized_result,
                identity_maps,
            )
            batch_id = int(staging["batch_id"])
            inserted_rows = 0
            skipped_existing = 0
            pending_rows: list[int] = []
            reconciled_counts: dict[str, int] = {}
            row_results: list[dict[str, Any]] = []

            for staged_row in staging["staged_rows"]:
                classification_type = str(staged_row.get("classification_type"))
                row_manifest = {
                    "dedup_fingerprint": staged_row.get("dedup_fingerprint"),
                    "classification_type": classification_type,
                    "staging_result": staged_row.get("result"),
                    "dispatch_result": None,
                    "reason": None,
                    "finance_alert_action": None,
                }
                if staged_row.get("result") == "skipped_existing":
                    skipped_existing += 1
                    row_results.append(row_manifest)
                    continue
                inserted_rows += 1
                row_id = int(staged_row["row_id"])
                dispatch = dispatch_finance_import_row(
                    cursor,
                    row_id,
                    batch_id,
                )
                row_manifest.update(
                    {
                        "dispatch_result": dispatch["result"],
                        "reason": dispatch.get("reason"),
                        "finance_alert_action": dispatch.get(
                            "finance_alert_action"
                        ),
                    }
                )
                row_results.append(row_manifest)
                if dispatch["result"] in {"reconciled", "existing"}:
                    reconciled_counts[classification_type] = (
                        reconciled_counts.get(classification_type, 0) + 1
                    )
                else:
                    pending_rows.append(row_id)

            cursor.execute(
                """UPDATE finance_import_batches
                   SET status='completed', completed_at=CURRENT_TIMESTAMP,
                       failure_message=NULL
                   WHERE id=%s AND status='staged'""",
                (batch_id,),
            )
            if getattr(cursor, "rowcount", 1) != 1:
                raise RuntimeError("finance import batch completion failed")
            alert_projection = project_finance_import_review_alert(
                cursor,
                batch_id,
            )

        manifest = {
            "mode": "dry_run" if dry_run else "apply",
            "source_path": source_path,
            "format_manifest": {
                "format_id": normalized_result.get("format_id"),
                "sheet_name": normalized_result.get("sheet_name"),
                "header_row": normalized_result.get("header_row"),
                "normalized_row_count": len(
                    normalized_result["normalized_rows"]
                ),
            },
            "batch_id": None if dry_run else batch_id,
            "inserted_rows": inserted_rows,
            "skipped_existing": skipped_existing,
            "reconciled_counts": reconciled_counts,
            "pending_rows": [] if dry_run else pending_rows,
            "row_results": row_results,
            "alert_action": alert_projection,
            "transaction_outcome": "rolled_back" if dry_run else "committed",
        }
        if dry_run:
            connection.rollback()
        else:
            connection.commit()
        return manifest
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
