"""Pure client-ledger transaction aggregation used by the later DB writer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation


ACTIVE_RECEIPT_STAGES = ("deposit", "first_payment", "second_payment")


def _positive_id(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _amount(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a positive finite amount")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive finite amount") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f"{field} must be a positive finite amount")
    return amount


def _same_ledger_and_stage(
    reversal: Mapping[str, object],
    receipt: Mapping[str, object],
) -> bool:
    required_identity = ("client_payment_id", "case_no", "stage")
    if any(field not in reversal or field not in receipt for field in required_identity):
        raise ValueError(
            "reversal and receipt must include client_payment_id, case_no, and stage"
        )
    return all(reversal[field] == receipt[field] for field in required_identity)


def calculate_client_payment_state(
    receivables: Mapping[str, object],
    transactions: Sequence[Mapping[str, object]],
) -> dict:
    """Return net client receipts for the three active collection stages only."""
    if set(ACTIVE_RECEIPT_STAGES) - set(receivables):
        raise ValueError("receivables must define all active receipt stages")
    normalized_receivables: dict[str, Decimal] = {}
    for stage in ACTIVE_RECEIPT_STAGES:
        value = receivables[stage]
        if isinstance(value, bool):
            raise ValueError(f"{stage} receivable must be a finite non-negative amount")
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(
                f"{stage} receivable must be a finite non-negative amount"
            ) from exc
        if not amount.is_finite() or amount < 0:
            raise ValueError(
                f"{stage} receivable must be a finite non-negative amount"
            )
        normalized_receivables[stage] = amount

    stage_amounts = {stage: Decimal("0") for stage in ACTIVE_RECEIPT_STAGES}
    references: set[str] = set()
    rows_by_id: dict[int, Mapping[str, object]] = {}
    normalized: list[tuple[Mapping[str, object], Decimal]] = []

    for transaction in transactions:
        if not isinstance(transaction, Mapping):
            raise TypeError("transactions must contain mappings")
        reference = transaction.get("external_reference")
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError("duplicate or empty external_reference")
        if reference in references:
            raise ValueError("duplicate or empty external_reference")
        references.add(reference)

        amount = _amount(transaction.get("amount"), "transaction amount")
        stage = transaction.get("stage")
        if stage not in stage_amounts:
            raise ValueError("unknown payment stage")
        transaction_type = transaction.get("transaction_type")
        if transaction_type not in {"receipt", "reversal"}:
            raise ValueError("invalid transaction type for stage")
        if transaction.get("transaction_status") not in {
            "succeeded",
            "failed",
            "reversed",
        }:
            raise ValueError("invalid transaction status")

        reversal_of = transaction.get("reversal_of_transaction_id")
        if transaction_type == "receipt":
            if reversal_of is not None:
                raise ValueError("receipt reversal_of_transaction_id must be None")
        else:
            _positive_id(reversal_of, "reversal_of_transaction_id")

        transaction_id = transaction.get("id")
        if transaction_id is not None:
            transaction_id = _positive_id(transaction_id, "transaction id")
            if transaction_id in rows_by_id:
                raise ValueError("duplicate transaction id")
            rows_by_id[transaction_id] = transaction
        normalized.append((transaction, amount))

    reversed_by_receipt: dict[int, Decimal] = {}
    for transaction, amount in normalized:
        transaction_type = transaction["transaction_type"]
        status = transaction["transaction_status"]
        if transaction_type == "receipt":
            if status == "succeeded":
                stage_amounts[str(transaction["stage"])] += amount
            continue

        receipt_id = _positive_id(
            transaction.get("reversal_of_transaction_id"),
            "reversal_of_transaction_id",
        )
        receipt = rows_by_id.get(receipt_id)
        if (
            receipt is None
            or receipt.get("transaction_type") != "receipt"
            or receipt.get("transaction_status") != "succeeded"
        ):
            raise ValueError(
                "reversal must reference an existing succeeded receipt"
            )
        if not _same_ledger_and_stage(transaction, receipt):
            raise ValueError(
                "reversal must reference a receipt in the same payment, case, and stage"
            )
        if status != "succeeded":
            continue
        reversed_total = reversed_by_receipt.get(receipt_id, Decimal("0")) + amount
        if reversed_total > _amount(receipt.get("amount"), "receipt amount"):
            raise ValueError("succeeded reversals exceed the original receipt amount")
        reversed_by_receipt[receipt_id] = reversed_total
        stage_amounts[str(transaction["stage"])] -= amount

    for stage, amount in stage_amounts.items():
        if amount < 0 or amount > normalized_receivables[stage]:
            raise ValueError(f"{stage} net amount is outside the receivable range")
    received = sum(stage_amounts.values())
    return {
        "deposit_received": float(stage_amounts.get("deposit", 0)),
        "first_payment_received": float(stage_amounts.get("first_payment", 0)),
        "second_payment_received": float(stage_amounts.get("second_payment", 0)),
        "amount_received": float(received),
    }

