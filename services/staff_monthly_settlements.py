"""Create and finalize explicit caregiver monthly settlement snapshots."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from services.db_service import get_connection


def _money(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value if value is not None else 0))
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be a decimal") from exc
    return result


def _month_start(value: Any) -> date:
    if isinstance(value, datetime):
        value = value.date()
    elif isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("settlement_month must be an ISO date") from exc
    if not isinstance(value, date) or value.day != 1:
        raise ValueError("settlement_month must be the first day of a month")
    return value


def _load_staff_payment(cursor, payment_id: int) -> dict[str, Any] | None:
    cursor.execute(
        """SELECT sp.id, sp.assignment_id, sp.case_no, sp.staff_id,
                  sp.service_salary, sp.floor_fee_amount, sp.adjustment_amount,
                  sp.total_payable, sp.payment_status,
                  a.case_no AS assignment_case_no, a.staff_id AS assignment_staff_id,
                  a.status AS assignment_status
           FROM staff_payments sp
           JOIN case_staff_assignments a ON a.id = sp.assignment_id
           WHERE sp.id = %s FOR UPDATE""",
        (payment_id,),
    )
    return cursor.fetchone()


def _build_detail(source: dict[str, Any], request: dict[str, Any], staff_id: int) -> dict[str, Any]:
    if source is None:
        raise ValueError("staff_payment does not exist")
    if source["staff_id"] != staff_id or source["assignment_staff_id"] != staff_id:
        raise ValueError("staff_payment belongs to another staff")
    if source["case_no"] != source["assignment_case_no"]:
        raise ValueError("staff_payment case does not match assignment")
    if source["assignment_id"] != request.get("assignment_id", source["assignment_id"]):
        raise ValueError("staff_payment assignment does not match request")
    if source.get("assignment_status") in {"cancelled", "replaced"}:
        raise ValueError("cancelled or replaced assignment cannot be settled")
    if source.get("payment_status") == "cancelled":
        raise ValueError("cancelled staff_payment cannot be settled")

    service_salary = _money(source.get("service_salary"), "service_salary")
    floor_fee = _money(source.get("floor_fee_amount"), "floor_fee_amount")
    adjustment = _money(source.get("adjustment_amount"), "adjustment_amount")
    legacy = _money(request.get("legacy_subsidy_payable", 0), "legacy_subsidy_payable")
    if service_salary < 0 or floor_fee < 0 or legacy < 0:
        raise ValueError("payable components cannot be negative")

    legacy_status = str(request.get("legacy_subsidy_status") or "not_applicable")
    review_note = str(request.get("review_note") or "").strip() or None
    review_required = False
    if legacy == 0:
        if legacy_status != "not_applicable":
            raise ValueError("zero legacy subsidy must be not_applicable")
    elif legacy_status != "confirmed" or not review_note:
        legacy_status = "review_required"
        review_required = True

    payable = service_salary + legacy + floor_fee + adjustment
    if payable < 0:
        raise ValueError("payable amount cannot be negative")
    assert payable == service_salary + legacy + floor_fee + adjustment
    return {
        "staff_payment_id": int(source["id"]),
        "case_no": str(source["case_no"]),
        "assignment_id": int(source["assignment_id"]),
        "staff_id": int(staff_id),
        "service_salary": service_salary,
        "legacy_subsidy_payable": legacy,
        "floor_fee_amount": floor_fee,
        "adjustment_amount": adjustment,
        "payable_amount": payable,
        "legacy_subsidy_status": legacy_status,
        "review_required": review_required,
        "review_note": review_note,
    }


def _same_detail(existing: dict[str, Any], expected: dict[str, Any]) -> bool:
    identity_fields = ("staff_payment_id", "case_no", "assignment_id", "staff_id")
    money_fields = (
        "service_salary", "legacy_subsidy_payable", "floor_fee_amount",
        "adjustment_amount", "payable_amount",
    )
    return (
        all(str(existing[field]) == str(expected[field]) for field in identity_fields)
        and all(_money(existing[field], field) == expected[field] for field in money_fields)
        and existing["legacy_subsidy_status"] == expected["legacy_subsidy_status"]
        and bool(existing["review_required"]) == expected["review_required"]
        and (existing.get("review_note") or None) == expected["review_note"]
    )


def _other_active_settlement(
    cursor: Any,
    payment_ids: list[int],
    current_settlement_id: int | None,
) -> dict[str, Any] | None:
    placeholders = ", ".join(["%s"] * len(payment_ids))
    params: list[Any] = list(payment_ids)
    current_filter = ""
    if current_settlement_id is not None:
        current_filter = " AND sms.id <> %s"
        params.append(current_settlement_id)
    cursor.execute(
        f"""SELECT d.staff_payment_id, sms.id AS settlement_id,
                   sms.staff_id, sms.settlement_month, sms.revision, sms.status
            FROM staff_monthly_settlement_details d
            JOIN staff_monthly_settlements sms ON sms.id = d.settlement_id
            WHERE d.staff_payment_id IN ({placeholders})
              AND sms.status <> 'cancelled'{current_filter}
            ORDER BY d.staff_payment_id, sms.id
            LIMIT 1 FOR UPDATE""",
        tuple(params),
    )
    return cursor.fetchone()


def create_staff_monthly_settlement(
    staff_id: int,
    settlement_month: date | str,
    revision: int,
    details: list[dict[str, Any]],
) -> dict[str, Any]:
    """Persist one explicit staff/month/revision payable snapshot."""
    month = _month_start(settlement_month)
    if not isinstance(revision, int) or revision < 1:
        raise ValueError("revision must be a positive integer")
    if not details:
        raise ValueError("details are required")
    payment_ids = [int(item["staff_payment_id"]) for item in details]
    if len(payment_ids) != len(set(payment_ids)):
        raise ValueError("duplicate staff_payment_id in settlement")

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT id, staff_id, settlement_month, revision, total_payable,
                          total_paid, status, finalized_at
                   FROM staff_monthly_settlements
                   WHERE staff_id = %s AND settlement_month = %s AND revision = %s
                   FOR UPDATE""",
                (staff_id, month, revision),
            )
            existing = cursor.fetchone()

            conflict = _other_active_settlement(
                cursor,
                payment_ids,
                int(existing["id"]) if existing else None,
            )
            if conflict is not None:
                return {
                    "result": "review_required",
                    "reason": "staff_payment_already_in_active_settlement",
                    "staff_payment_id": int(conflict["staff_payment_id"]),
                    "settlement_id": int(conflict["settlement_id"]),
                }

            built = []
            for request in details:
                source = _load_staff_payment(cursor, int(request["staff_payment_id"]))
                built.append(_build_detail(source, request, staff_id))
            total_payable = sum((item["payable_amount"] for item in built), Decimal("0"))

            if existing:
                cursor.execute(
                    """SELECT staff_payment_id, case_no, assignment_id, staff_id,
                              service_salary, legacy_subsidy_payable, floor_fee_amount,
                              adjustment_amount, payable_amount, legacy_subsidy_status,
                              review_required, review_note
                       FROM staff_monthly_settlement_details
                       WHERE settlement_id = %s ORDER BY staff_payment_id""",
                    (existing["id"],),
                )
                current = cursor.fetchall()
                expected = sorted(built, key=lambda item: item["staff_payment_id"])
                current = sorted(current, key=lambda item: int(item["staff_payment_id"]))
                identical = (
                    _money(existing["total_payable"], "total_payable") == total_payable
                    and len(current) == len(expected)
                    and all(_same_detail(old, new) for old, new in zip(current, expected))
                )
                if not identical:
                    return {"result": "review_required", "reason": "existing_snapshot_differs"}
                return {
                    "result": "existing",
                    "settlement": {**existing, "details": expected},
                }

            needs_review = any(item["review_required"] for item in built)
            status = "review_required" if needs_review else "draft"
            cursor.execute(
                """INSERT INTO staff_monthly_settlements
                       (staff_id, settlement_month, revision, total_payable, total_paid, status)
                   VALUES (%s, %s, %s, %s, 0, %s)""",
                (staff_id, month, revision, total_payable, status),
            )
            settlement_id = cursor.lastrowid
            for item in built:
                cursor.execute(
                    """INSERT INTO staff_monthly_settlement_details
                           (settlement_id, staff_payment_id, case_no, assignment_id,
                            staff_id, service_salary, legacy_subsidy_payable,
                            floor_fee_amount, adjustment_amount, payable_amount,
                            legacy_subsidy_status, review_required, review_note)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        settlement_id, item["staff_payment_id"], item["case_no"],
                        item["assignment_id"], item["staff_id"], item["service_salary"],
                        item["legacy_subsidy_payable"], item["floor_fee_amount"],
                        item["adjustment_amount"], item["payable_amount"],
                        item["legacy_subsidy_status"], item["review_required"],
                        item["review_note"],
                    ),
                )
        connection.commit()
        return {
            "result": "review_required" if needs_review else "created",
            "settlement": {
                "id": settlement_id,
                "staff_id": staff_id,
                "settlement_month": month,
                "revision": revision,
                "total_payable": total_payable,
                "total_paid": Decimal("0"),
                "status": status,
                "details": built,
            },
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def finalize_staff_monthly_settlement(settlement_id: int) -> dict[str, Any]:
    """Finalize a review-free settlement without changing its snapshot."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT id, staff_id, settlement_month, revision, total_payable,
                          total_paid, status, finalized_at
                   FROM staff_monthly_settlements WHERE id = %s FOR UPDATE""",
                (settlement_id,),
            )
            settlement = cursor.fetchone()
            if not settlement:
                raise ValueError("settlement does not exist")
            if settlement["status"] == "finalized":
                return {"result": "finalized", "settlement": settlement}
            if settlement["status"] not in {"draft", "review_required"}:
                raise ValueError("settlement cannot be finalized from current status")

            cursor.execute(
                """SELECT payable_amount, review_required
                   FROM staff_monthly_settlement_details
                   WHERE settlement_id = %s FOR UPDATE""",
                (settlement_id,),
            )
            details = cursor.fetchall()
            if not details:
                raise ValueError("settlement has no details")
            total = sum((_money(item["payable_amount"], "payable_amount") for item in details), Decimal("0"))
            if total != _money(settlement["total_payable"], "total_payable"):
                raise ValueError("settlement total does not match details")
            if any(bool(item["review_required"]) for item in details):
                cursor.execute(
                    "UPDATE staff_monthly_settlements SET status = 'review_required' WHERE id = %s",
                    (settlement_id,),
                )
                connection.commit()
                settlement["status"] = "review_required"
                return {"result": "review_required", "settlement": settlement}

            cursor.execute(
                """UPDATE staff_monthly_settlements
                   SET status = 'finalized', finalized_at = CURRENT_TIMESTAMP
                   WHERE id = %s""",
                (settlement_id,),
            )
        connection.commit()
        settlement["status"] = "finalized"
        return {"result": "finalized", "settlement": settlement}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
