"""Pure classification of normalized finance rows; classification is not reconciliation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any
import unicodedata

from scripts.imports.finance_normalized_row import validate_normalized_row
from domains.finance_import.cancellation_code import resolve_finance_cancellation_code


CLASSIFICATION_TYPES = frozenset(
    {
        "client_receipt",
        "client_refund",
        "government_subsidy",
        "client_subsidy_return",
        "staff_salary",
        "staff_legacy_subsidy",
        "non_business_review",
    }
)


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
    projection = resolve_finance_cancellation_code(row)
    return projection["cancellation_code"] is not None


def _normalized_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = unicodedata.normalize("NFKC", value).strip()
    return normalized or None


def _incoming_amount(row: Mapping[str, Any]) -> int | None:
    amount = row.get("credit")
    if isinstance(amount, bool) or not isinstance(amount, (int, float, Decimal)):
        return None
    if isinstance(amount, float) and not amount.is_integer():
        return None
    if isinstance(amount, Decimal) and amount != amount.to_integral_value():
        return None
    return int(amount)


def _receipt_candidate_matches(
    row: Mapping[str, Any], candidate: Mapping[str, Any]
) -> bool:
    client_name = _normalized_text(row.get("counterparty_name"))
    client_account = _normalized_text(row.get("counterparty_account"))
    amount = _incoming_amount(row)
    if client_name is None or client_account is None or amount is None:
        return False
    candidate_name = _normalized_text(candidate.get("name"))
    candidate_account = _normalized_text(candidate.get("account"))
    open_amounts = candidate.get("open_amounts")
    if candidate_name != client_name or candidate_account != client_account:
        return False
    if not isinstance(open_amounts, Sequence) or isinstance(open_amounts, str):
        return False
    return amount in open_amounts


def _classify_client_receipt_heuristic(
    row: Mapping[str, Any], client_receipt_candidates: Sequence[Mapping[str, Any]]
) -> dict[str, Any] | None:
    matched_client_ids = {
        candidate.get("client_id")
        for candidate in client_receipt_candidates
        if isinstance(candidate, Mapping)
        and isinstance(candidate.get("client_id"), int)
        and not isinstance(candidate.get("client_id"), bool)
        and _receipt_candidate_matches(row, candidate)
    }
    if len(matched_client_ids) == 1:
        return _result(
            "client_receipt",
            sorted(matched_client_ids),
            "client_receipt_heuristic:name+account+amount",
        )
    if len(matched_client_ids) > 1:
        return _review("client_receipt_heuristic_ambiguous")
    return None


def _classify_taishin_outgoing(
    row: Mapping[str, Any],
    client_refund_accounts: Mapping[str, Any],
    staff_accounts: Mapping[str, Any],
    client_subsidy_return_accounts: Mapping[str, Any],
) -> dict[str, Any]:
    account = row["counterparty_account"]
    if account is None:
        return _review("counterparty_account_missing")
    if not isinstance(account, str):
        return _review("counterparty_account_invalid")

    refund_client_ids = _ids_for_account(client_refund_accounts, account)
    subsidy_return_client_ids = _ids_for_account(
        client_subsidy_return_accounts, account
    )
    staff_ids = _ids_for_account(staff_accounts, account)
    owner_categories = sum(
        bool(ids)
        for ids in (refund_client_ids, subsidy_return_client_ids, staff_ids)
    )
    if owner_categories > 1:
        return _review("counterparty_identity_type_conflict")
    if len(refund_client_ids) == 1:
        return _result(
            "client_refund",
            refund_client_ids,
            "taishin_unique_client_refund_account",
            account,
        )
    if len(subsidy_return_client_ids) == 1:
        return _result(
            "client_subsidy_return",
            subsidy_return_client_ids,
            "taishin_unique_client_subsidy_return_account",
            account,
        )
    if len(staff_ids) == 1:
        return _result(
            "staff_legacy_subsidy",
            staff_ids,
            "taishin_unique_staff_account",
            account,
        )
    if (
        len(refund_client_ids) > 1
        or len(subsidy_return_client_ids) > 1
        or len(staff_ids) > 1
    ):
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
    client_subsidy_return_accounts: Mapping[str, Any] | None = None,
    client_receipt_candidates: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Classify one normalized bank row without selecting a ledger target."""

    validate_normalized_row(row)
    format_id = row["format_id"]
    direction = row["direction"]

    if direction == "unknown":
        return _review("direction_unknown")

    if client_subsidy_return_accounts is None:
        client_subsidy_return_accounts = client_refund_accounts
        client_refund_accounts = {}

    if format_id in {"legacy", "sinopac"}:
        if direction == "incoming":
            if _valid_client_virtual_account(row):
                return _result("client_receipt", [], "sinopac_valid_virtual_account")
            heuristic_result = _classify_client_receipt_heuristic(
                row, client_receipt_candidates
            )
            if heuristic_result is not None:
                return heuristic_result
            return _review("sinopac_invalid_or_missing_virtual_account")
        return _classify_sinopac_outgoing(row, staff_accounts)

    if format_id == "taishin":
        if direction == "incoming":
            memo = row["memo"]
            if isinstance(memo, str) and "新竹市政府" in memo:
                return _result("government_subsidy", [], "taishin_government_memo")
            return _review("taishin_incoming_not_government")
        return _classify_taishin_outgoing(
            row,
            client_refund_accounts,
            staff_accounts,
            client_subsidy_return_accounts,
        )

    return _review("unsupported_bank_direction")
