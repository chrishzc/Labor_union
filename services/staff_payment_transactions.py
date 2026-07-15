"""Write and recalculate assignment-based caregiver transfer transactions."""

from __future__ import annotations

from decimal import Decimal

from services.db_service import get_connection
from services.payment_rules import evaluate_payment_boundary


def calculate_staff_payment_state(total_payable, transactions: list[dict]) -> dict:
    total = Decimal(str(total_payable))
    result = evaluate_payment_boundary(
        "transaction_net",
        positive_types=["transfer"],
        negative_types=["return", "reversal"],
        transactions=transactions,
    )
    if not result["valid"]:
        raise ValueError(result["error"])
    paid = Decimal(str(result["net_amount"]))
    if paid < 0 or paid > total:
        raise ValueError("transaction net amount is outside the payable range")
    status = "paid" if paid == total else "partially_paid" if paid > 0 else "pending"
    return {"amount_paid": float(paid), "payment_status": status}


def record_staff_payment_transaction(staff_payment_id, transaction_type, transaction_status,
                                     amount, occurred_at, external_reference, notes=None) -> dict:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, total_payable FROM staff_payments WHERE id = %s FOR UPDATE", (staff_payment_id,))
            payment = cursor.fetchone()
            if not payment:
                raise ValueError("staff payment does not exist")
            cursor.execute("""SELECT transaction_type, transaction_status, amount, occurred_at, external_reference
                              FROM staff_payment_transactions WHERE staff_payment_id = %s FOR UPDATE""", (staff_payment_id,))
            transactions = cursor.fetchall()
            transactions.append({"transaction_type": transaction_type, "transaction_status": transaction_status,
                                 "amount": amount, "occurred_at": occurred_at, "external_reference": external_reference})
            state = calculate_staff_payment_state(payment["total_payable"], transactions)
            cursor.execute("""INSERT INTO staff_payment_transactions
                (staff_payment_id, case_no, staff_id, transaction_type, transaction_status, amount, occurred_at, external_reference, notes)
                SELECT id, case_no, staff_id, %s, %s, %s, %s, %s, %s FROM staff_payments WHERE id = %s""",
                (transaction_type, transaction_status, amount, occurred_at, external_reference, notes, staff_payment_id))
            paid_at = occurred_at if state["payment_status"] == "paid" else None
            cursor.execute("UPDATE staff_payments SET amount_paid = %s, payment_status = %s, paid_at = %s WHERE id = %s",
                           (state["amount_paid"], state["payment_status"], paid_at, staff_payment_id))
        conn.commit()
        return state
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
