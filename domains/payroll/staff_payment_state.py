"""Write and recalculate assignment-based caregiver transfer transactions."""

from __future__ import annotations

from decimal import Decimal

from domains.payroll.payment_rules import evaluate_payment_boundary


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


