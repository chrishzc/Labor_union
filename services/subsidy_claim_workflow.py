"""Transactional workflow for exact P0 government subsidy claim batches."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from services.db_service import get_connection


ITEM_FIELDS = frozenset({
    "case_no", "assignment_id", "staff_id", "claimed_hours", "unit_price", "requested_amount",
})
APPROVAL_FIELDS = frozenset({"item_id", "approved_amount"})

assert "requested_amount" in ITEM_FIELDS and "approved_amount" in APPROVAL_FIELDS


def _decimal(value: Any, field: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError(f"{field} must be a non-negative decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a non-negative decimal") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a non-negative decimal")
    return result


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _normalize_items(items: list[dict]) -> list[dict]:
    if not isinstance(items, list) or not items:
        raise ValueError("items must be a non-empty list")
    normalized = []
    assignment_ids = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict) or set(item) != ITEM_FIELDS:
            raise ValueError(f"items[{index}] must contain the exact snapshot fields")
        assignment_id = _positive_int(item["assignment_id"], f"items[{index}].assignment_id")
        staff_id = _positive_int(item["staff_id"], f"items[{index}].staff_id")
        if not isinstance(item["case_no"], str) or not item["case_no"]:
            raise ValueError(f"items[{index}].case_no must be a non-empty string")
        if assignment_id in assignment_ids:
            raise ValueError("items must not repeat assignment_id")
        assignment_ids.add(assignment_id)
        hours = _decimal(item["claimed_hours"], f"items[{index}].claimed_hours")
        unit_price = _decimal(item["unit_price"], f"items[{index}].unit_price")
        requested = _decimal(item["requested_amount"], f"items[{index}].requested_amount")
        if requested != hours * unit_price:
            raise ValueError(f"items[{index}].requested_amount must equal claimed_hours * unit_price")
        normalized.append({
            "case_no": item["case_no"],
            "assignment_id": assignment_id,
            "staff_id": staff_id,
            "claimed_hours": hours,
            "unit_price": unit_price,
            "requested_amount": requested,
        })
    return normalized


def _normalize_approvals(approvals: list[dict]) -> list[dict]:
    if not isinstance(approvals, list):
        raise ValueError("item_approvals must be a list")
    normalized = []
    item_ids = set()
    for index, approval in enumerate(approvals):
        if not isinstance(approval, dict) or set(approval) != APPROVAL_FIELDS:
            raise ValueError(f"item_approvals[{index}] must contain item_id and approved_amount")
        item_id = _positive_int(approval["item_id"], f"item_approvals[{index}].item_id")
        if item_id in item_ids:
            raise ValueError("item_approvals must not repeat item_id")
        item_ids.add(item_id)
        normalized.append({
            "item_id": item_id,
            "approved_amount": _decimal(
                approval["approved_amount"], f"item_approvals[{index}].approved_amount",
            ),
        })
    return normalized


def _batch_payload(batch: dict, items: list[dict]) -> dict:
    return {
        "id": batch["id"],
        "application_year": batch["application_year"],
        "quarter": batch["quarter"],
        "revision": batch["revision"],
        "status": batch["status"],
        "requested_amount": batch["requested_amount"],
        "approved_amount": batch.get("approved_amount", Decimal("0")),
        "paid_amount": batch.get("paid_amount", Decimal("0")),
        "items": items,
    }


def _review(reason: str, batch: dict | None = None, items: list[dict] | None = None) -> dict:
    return {
        "result": "review_required",
        "reason": reason,
        "batch": _batch_payload(batch, items or []) if batch else None,
    }


def _same_snapshot(batch: dict, stored_items: list[dict], expected: list[dict]) -> bool:
    if Decimal(str(batch["requested_amount"])) != sum(
        (item["requested_amount"] for item in expected), Decimal("0"),
    ):
        return False
    stored_by_assignment = {int(item["assignment_id"]): item for item in stored_items}
    if set(stored_by_assignment) != {item["assignment_id"] for item in expected}:
        return False
    for item in expected:
        stored = stored_by_assignment[item["assignment_id"]]
        if (
            str(stored["case_no"]) != item["case_no"]
            or int(stored["staff_id"]) != item["staff_id"]
            or Decimal(str(stored["claimed_hours"])) != item["claimed_hours"]
            or Decimal(str(stored["unit_price"])) != item["unit_price"]
            or Decimal(str(stored["requested_amount"])) != item["requested_amount"]
        ):
            return False
    return True


def _fetch_batch_items(cursor, batch_id: int, *, lock: bool = False) -> list[dict]:
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT id, batch_id, case_no, assignment_id, staff_id, claimed_hours, "
        "unit_price, requested_amount, approved_amount, paid_amount "
        "FROM subsidy_claim_batch_items WHERE batch_id = %s ORDER BY id" + suffix,
        (batch_id,),
    )
    return cursor.fetchall()


def create_subsidy_claim_batch(application_year: int, quarter: int, revision: int,
                               items: list[dict]) -> dict:
    application_year = _positive_int(application_year, "application_year")
    if isinstance(quarter, bool) or quarter not in (1, 2, 3, 4):
        raise ValueError("quarter must be 1, 2, 3, or 4")
    revision = _positive_int(revision, "revision")
    normalized = _normalize_items(items)
    requested_total = sum((item["requested_amount"] for item in normalized), Decimal("0"))

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM subsidy_claim_batches "
                "WHERE application_year = %s AND quarter = %s AND revision = %s FOR UPDATE",
                (application_year, quarter, revision),
            )
            existing = cursor.fetchone()
            if existing:
                stored_items = _fetch_batch_items(cursor, existing["id"], lock=True)
                if not _same_snapshot(existing, stored_items, normalized):
                    conn.rollback()
                    return _review("batch revision already exists with a different snapshot", existing, stored_items)
                conn.commit()
                return {"result": "created", "idempotent": True, "batch": _batch_payload(existing, stored_items)}

            assignment_ids = [item["assignment_id"] for item in normalized]
            placeholders = ",".join(["%s"] * len(assignment_ids))
            cursor.execute(
                "SELECT id, case_no, staff_id FROM case_staff_assignments "
                f"WHERE id IN ({placeholders}) FOR UPDATE",
                tuple(assignment_ids),
            )
            assignments = {int(row["id"]): row for row in cursor.fetchall()}
            if set(assignments) != set(assignment_ids):
                conn.rollback()
                return _review("one or more assignments do not exist")
            for item in normalized:
                assignment = assignments[item["assignment_id"]]
                if str(assignment["case_no"]) != item["case_no"] or int(assignment["staff_id"]) != item["staff_id"]:
                    conn.rollback()
                    return _review("assignment case_no or staff_id does not match the snapshot")

            cursor.execute(
                "INSERT INTO subsidy_claim_batches "
                "(application_year, quarter, revision, status, requested_amount, approved_amount, paid_amount) "
                "VALUES (%s,%s,%s,'draft',%s,0,0)",
                (application_year, quarter, revision, requested_total),
            )
            batch_id = cursor.lastrowid
            persisted_items = []
            for item in normalized:
                cursor.execute(
                    "INSERT INTO subsidy_claim_batch_items "
                    "(batch_id, case_no, assignment_id, staff_id, claimed_hours, unit_price, "
                    "requested_amount, approved_amount, paid_amount) VALUES (%s,%s,%s,%s,%s,%s,%s,0,0)",
                    (batch_id, item["case_no"], item["assignment_id"], item["staff_id"],
                     item["claimed_hours"], item["unit_price"], item["requested_amount"]),
                )
                persisted_items.append({
                    "id": cursor.lastrowid,
                    "batch_id": batch_id,
                    **item,
                    "approved_amount": Decimal("0"),
                    "paid_amount": Decimal("0"),
                })
            batch = {
                "id": batch_id,
                "application_year": application_year,
                "quarter": quarter,
                "revision": revision,
                "status": "draft",
                "requested_amount": requested_total,
                "approved_amount": Decimal("0"),
                "paid_amount": Decimal("0"),
            }
        conn.commit()
        return {"result": "created", "idempotent": False, "batch": _batch_payload(batch, persisted_items)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def submit_subsidy_claim_batch(batch_id: int, submitted_at) -> dict:
    batch_id = _positive_int(batch_id, "batch_id")
    if submitted_at is None:
        raise ValueError("submitted_at is required")
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM subsidy_claim_batches WHERE id = %s FOR UPDATE", (batch_id,))
            batch = cursor.fetchone()
            if not batch:
                raise ValueError("subsidy claim batch does not exist")
            items = _fetch_batch_items(cursor, batch_id, lock=True)
            item_total = sum((Decimal(str(item["requested_amount"])) for item in items), Decimal("0"))
            if not items or item_total != Decimal(str(batch["requested_amount"])):
                conn.rollback()
                return _review("batch requested total does not match its complete item snapshot", batch, items)
            if batch["status"] == "submitted":
                conn.commit()
                return {"result": "submitted", "idempotent": True, "batch": _batch_payload(batch, items)}
            if batch["status"] != "draft":
                raise ValueError("only a draft batch can be submitted")
            cursor.execute(
                "UPDATE subsidy_claim_batches SET status = 'submitted', submitted_at = %s WHERE id = %s",
                (submitted_at, batch_id),
            )
            batch = {**batch, "status": "submitted", "submitted_at": submitted_at}
        conn.commit()
        return {"result": "submitted", "idempotent": False, "batch": _batch_payload(batch, items)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def approve_subsidy_claim_batch(batch_id: int, item_approvals: list[dict], approved_at) -> dict:
    batch_id = _positive_int(batch_id, "batch_id")
    if approved_at is None:
        raise ValueError("approved_at is required")
    approvals = _normalize_approvals(item_approvals)
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM subsidy_claim_batches WHERE id = %s FOR UPDATE", (batch_id,))
            batch = cursor.fetchone()
            if not batch:
                raise ValueError("subsidy claim batch does not exist")
            items = _fetch_batch_items(cursor, batch_id, lock=True)
            approvals_by_id = {item["item_id"]: item["approved_amount"] for item in approvals}
            item_ids = {int(item["id"]) for item in items}
            complete_and_exact = set(approvals_by_id) == item_ids and all(
                approvals_by_id[int(item["id"])] == Decimal(str(item["requested_amount"]))
                for item in items
            )

            if batch["status"] == "approved":
                stored_exact = all(
                    Decimal(str(item["approved_amount"])) == Decimal(str(item["requested_amount"]))
                    for item in items
                )
                if complete_and_exact and stored_exact:
                    conn.commit()
                    return {"result": "approved", "idempotent": True, "batch": _batch_payload(batch, items)}
                conn.rollback()
                return _review("approved batch cannot be overwritten", batch, items)
            if batch["status"] != "submitted":
                raise ValueError("only a submitted batch can be approved")
            if not complete_and_exact:
                conn.rollback()
                return _review("P0 approval requires every item at its full requested amount", batch, items)

            approved_total = sum(approvals_by_id.values(), Decimal("0"))
            if approved_total != Decimal(str(batch["requested_amount"])):
                conn.rollback()
                return _review("approved total must equal requested total", batch, items)
            for item in items:
                item_id = int(item["id"])
                cursor.execute(
                    "UPDATE subsidy_claim_batch_items SET approved_amount = %s WHERE id = %s",
                    (approvals_by_id[item_id], item_id),
                )
                item["approved_amount"] = approvals_by_id[item_id]
            cursor.execute(
                "UPDATE subsidy_claim_batches SET status = 'approved', approved_amount = %s, "
                "approved_at = %s WHERE id = %s",
                (approved_total, approved_at, batch_id),
            )
            batch = {**batch, "status": "approved", "approved_amount": approved_total, "approved_at": approved_at}
        conn.commit()
        return {"result": "approved", "idempotent": False, "batch": _batch_payload(batch, items)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
