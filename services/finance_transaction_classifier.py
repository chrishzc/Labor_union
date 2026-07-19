"""Pure classification of normalized finance rows; classification is not reconciliation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


REQUIRED_ROW_FIELDS = frozenset(
    {
        "format_id",
        "source_file",
        "source_bank_account",
        "sheet_name",
        "source_row",
        "source_reference",
        "transaction_date",
        "transaction_time",
        "posting_date",
        "value_date",
        "debit",
        "credit",
        "direction",
        "balance",
        "currency",
        "summary",
        "memo",
        "counterparty_name",
        "counterparty_account",
        "cancellation_code",
        "bank_references",
        "warnings",
        "raw_payload",
    }
)

CLASSIFICATION_TYPES = frozenset(
    {
        "client_receipt",
        "government_subsidy",
        "client_subsidy_return",
        "staff_salary",
        "staff_legacy_subsidy",
        "non_business_review",
    }
)


def _validate_normalized_row(row: Mapping[str, Any]) -> None:
    missing = sorted(REQUIRED_ROW_FIELDS - set(row))
    if missing:
        raise ValueError(f"normalized finance row 缺少欄位：{', '.join(missing)}")
    if row["format_id"] not in {"legacy", "taishin", "sinopac"}:
        raise ValueError("normalized finance row 的 format_id 無效")
    if row["direction"] not in {"incoming", "outgoing", "unknown"}:
        raise ValueError("normalized finance row 的 direction 無效")
    if not isinstance(row["source_row"], int) or row["source_row"] < 1:
        raise ValueError("normalized finance row 的 source_row 必須是一基底正整數")
    if not isinstance(row["bank_references"], Mapping):
        raise ValueError("normalized finance row 的 bank_references 必須是 mapping")
    if not isinstance(row["warnings"], list) or len(row["warnings"]) != len(set(row["warnings"])):
        raise ValueError("normalized finance row 的 warnings 必須是不重複字串陣列")
    if not all(isinstance(item, str) for item in row["warnings"]):
        raise ValueError("normalized finance row 的 warnings 必須是不重複字串陣列")
    if not isinstance(row["raw_payload"], Mapping):
        raise ValueError("normalized finance row 的 raw_payload 必須是 mapping")


def _ids_for_account(accounts: Mapping[str, Any], account: str | None) -> list[Any]:
    if account is None or account not in accounts:
        return []
    value = accounts[account]
    if value is None:
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        candidates = list(value)
    elif isinstance(value, (set, frozenset)):
        candidates = list(value)
    else:
        candidates = [value]
    return list(dict.fromkeys(candidates))


def _result(
    classification_type: str,
    matched_ids: list[Any],
    reason: str,
    resolved_counterparty_account: str | None = None,
) -> dict[str, Any]:
    assert classification_type in CLASSIFICATION_TYPES
    return {
        "classification_type": classification_type,
        "matched_identity_ids": matched_ids,
        "resolved_counterparty_account": resolved_counterparty_account,
        "reason": reason,
    }


def _review(reason: str) -> dict[str, Any]:
    return _result("non_business_review", [], reason)


def _valid_client_virtual_account(row: Mapping[str, Any]) -> bool:
    value = row["bank_references"].get("銷帳編號")
    return isinstance(value, str) and re.fullmatch(r"99781699[0-9]{6}", value) is not None


def _classify_taishin_outgoing(
    row: Mapping[str, Any],
    client_refund_accounts: Mapping[str, Any],
    staff_accounts: Mapping[str, Any],
) -> dict[str, Any]:
    account = row["counterparty_account"]
    if account is None:
        return _review("counterparty_account_missing")
    if not isinstance(account, str):
        return _review("counterparty_account_invalid")

    client_ids = _ids_for_account(client_refund_accounts, account)
    staff_ids = _ids_for_account(staff_accounts, account)
    if len(client_ids) == 1 and not staff_ids:
        return _result(
            "client_subsidy_return",
            client_ids,
            "taishin_unique_client_refund_account",
            account,
        )
    if len(staff_ids) == 1 and not client_ids:
        return _result(
            "staff_legacy_subsidy",
            staff_ids,
            "taishin_unique_staff_account",
            account,
        )
    if client_ids and staff_ids:
        return _review("counterparty_identity_type_conflict")
    if len(client_ids) > 1 or len(staff_ids) > 1:
        return _review("counterparty_account_multiple_matches")
    return _review("counterparty_account_no_match")


def _classify_sinopac_outgoing(
    row: Mapping[str, Any],
    staff_accounts: Mapping[str, Any],
) -> dict[str, Any]:
    def contains_complete_account(text: str, account: str) -> bool:
        if account.isdecimal():
            return re.search(rf"(?<![0-9]){re.escape(account)}(?![0-9])", text) is not None
        return (
            re.search(
                rf"(?<![0-9A-Za-z]){re.escape(account)}(?![0-9A-Za-z])",
                text,
            )
            is not None
        )

    def matches(text: Any) -> tuple[list[str], list[Any]]:
        if not isinstance(text, str):
            return [], []
        matched_accounts: list[str] = []
        matched_staff_ids: list[Any] = []
        for account in staff_accounts:
            if (
                not isinstance(account, str)
                or not account
                or not contains_complete_account(text, account)
            ):
                continue
            ids = _ids_for_account(staff_accounts, account)
            if not ids:
                continue
            matched_accounts.append(account)
            matched_staff_ids.extend(ids)
        return (
            list(dict.fromkeys(matched_accounts)),
            list(dict.fromkeys(matched_staff_ids)),
        )

    matched_accounts, staff_ids = matches(row["memo"])
    source = "memo"
    if not matched_accounts:
        matched_accounts, staff_ids = matches(
            row["bank_references"].get("存摺備註")
        )
        source = "passbook_memo"

    if not matched_accounts:
        return _review("sinopac_staff_account_no_match")
    if len(matched_accounts) > 1:
        return _review("sinopac_multiple_staff_accounts_matched")
    if len(staff_ids) != 1:
        return _review("sinopac_staff_account_identity_ambiguous")
    return _result(
        "staff_salary",
        staff_ids,
        f"sinopac_unique_staff_account_in_{source}",
        matched_accounts[0],
    )


def classify_finance_transaction(
    row: Mapping[str, Any],
    client_refund_accounts: Mapping[str, Any],
    staff_accounts: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify one normalized bank row without selecting a ledger target."""

    _validate_normalized_row(row)
    format_id = row["format_id"]
    direction = row["direction"]

    if direction == "unknown":
        return _review("direction_unknown")

    if format_id in {"legacy", "sinopac"}:
        if direction == "incoming":
            if _valid_client_virtual_account(row):
                return _result("client_receipt", [], "sinopac_valid_virtual_account")
            return _review("sinopac_invalid_or_missing_virtual_account")
        return _classify_sinopac_outgoing(row, staff_accounts)

    if format_id == "taishin":
        if direction == "incoming":
            memo = row["memo"]
            if isinstance(memo, str) and "新竹市政府" in memo:
                return _result("government_subsidy", [], "taishin_government_memo")
            return _review("taishin_incoming_not_government")
        return _classify_taishin_outgoing(row, client_refund_accounts, staff_accounts)

    return _review("unsupported_bank_direction")
