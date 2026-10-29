"""Manual bank facts and display-only accounting warning policy."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

STATEMENT_COLUMNS = (
    "帳號", "交易日", "計息日", "入帳日", "摘要", "幣別", "支出", "存入", "餘額",
    "票據號碼", "銷帳編號", "交易參考編號", "備註", "更正註記", "存摺備註",
)


def validate_manual_statement(fields: dict[str, str | int | None]) -> dict[str, str | int | None]:
    if set(fields) - set(STATEMENT_COLUMNS):
        raise ValueError("unknown_statement_column")
    values = {column: fields.get(column) for column in STATEMENT_COLUMNS}
    try:
        date.fromisoformat(str(values["交易日"]))
    except (ValueError, TypeError):
        raise ValueError("invalid_transaction_date") from None
    amounts = []
    for column in ("支出", "存入"):
        value = values[column]
        if value is None or value == "":
            amounts.append(0)
            continue
        try:
            amount = Decimal(str(value))
            if not amount.is_finite() or amount != amount.to_integral_value() or amount < 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            raise ValueError("invalid_statement_amount") from None
        values[column] = int(amount)
        amounts.append(int(amount))
    if sum(value > 0 for value in amounts) != 1:
        raise ValueError("one_statement_direction_required")
    if not any(str(values[column] or "").strip() for column in ("銷帳編號", "備註")):
        raise ValueError("statement_reference_required")
    return values


def accounting_warning(direction: str, expected: int, actual: int, has_payment: bool) -> str | None:
    """No tolerance, allocation or settlement rules are changed here."""
    difference = expected - actual
    if direction == "receivable" and difference < 0:
        return "over_received"
    if direction == "payable" and difference < 0:
        return "over_paid"
    if direction == "payable" and has_payment and difference > 100:
        return "under_paid"
    return None


def bank_import_type(format_id: str, direction: str) -> str:
    if format_id == "sinopac":
        return {"incoming": "receivable", "outgoing": "payable"}.get(direction, "review")
    if format_id == "taishin":
        return {"incoming": "government_subsidy", "outgoing": "subsidy_return"}.get(direction, "review")
    return "legacy"
