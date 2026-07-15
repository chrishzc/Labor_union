"""Pure client-ledger transaction aggregation used by the later DB writer."""

from __future__ import annotations

from decimal import Decimal


ACTIVE_RECEIPT_STAGES = ("deposit", "first_payment", "second_payment")


def calculate_client_payment_state(receivables: dict, transactions: list[dict]) -> dict:
    """Return net client receipts for the three active collection stages only."""
    if set(ACTIVE_RECEIPT_STAGES) - set(receivables):
        raise ValueError("receivables must define all active receipt stages")
    stage_amounts = {stage: Decimal("0") for stage in ACTIVE_RECEIPT_STAGES}
    references = set()
    for transaction in transactions:
        reference = transaction.get("external_reference")
        if not reference or reference in references:
            raise ValueError("duplicate or empty external_reference")
        references.add(reference)
        amount = Decimal(str(transaction.get("amount")))
        if amount <= 0:
            raise ValueError("transaction amount must be positive")
        if transaction.get("transaction_status") != "succeeded":
            continue
        stage = transaction.get("stage")
        if stage not in stage_amounts:
            raise ValueError("unknown payment stage")
        transaction_type = transaction.get("transaction_type")
        direction = 1 if transaction_type == "receipt" else -1 if transaction_type == "reversal" else None
        if direction is None:
            raise ValueError("invalid transaction type for stage")
        stage_amounts[stage] += direction * amount
    for stage, amount in stage_amounts.items():
        if amount < 0 or amount > Decimal(str(receivables[stage])):
            raise ValueError(f"{stage} net amount is outside the receivable range")
    received = sum(stage_amounts.values())
    return {
        "deposit_received": float(stage_amounts.get("deposit", 0)),
        "first_payment_received": float(stage_amounts.get("first_payment", 0)),
        "second_payment_received": float(stage_amounts.get("second_payment", 0)),
        "amount_received": float(received),
    }
