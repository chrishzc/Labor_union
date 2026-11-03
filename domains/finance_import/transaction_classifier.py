"""
File: transaction_classifier.py
Description: 純函式正規化財務流水分類，支援台新備註姓名與月份金額退款判定，不直接核銷。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any
import unicodedata

from domains.finance_import.normalized_row import validate_normalized_row
from domains.finance_import.cancellation_code import (
    extract_sinopac_account_reference,
    extract_sinopac_memo_case_suffix,
    resolve_finance_cancellation_code,
)


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
    client_refund_accounts: Mapping[str, Any],
    staff_case_suffixes: Mapping[str, Any] | None = None,
    client_refund_case_suffixes: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    memo = row.get("memo")
    suffix = extract_sinopac_memo_case_suffix(memo)
    if suffix is not None:
        staff_case_map = staff_case_suffixes or {}
        refund_case_map = client_refund_case_suffixes or {}
        memo_staff_ids = _ids_for_account(staff_case_map, suffix)
        memo_refund_ids = _ids_for_account(refund_case_map, suffix)

        if memo_staff_ids and memo_refund_ids:
            memo_text = unicodedata.normalize("NFKC", memo) if isinstance(memo, str) else ""
            if any(k in memo_text for k in ("退款", "退費")) and not any(k in memo_text for k in ("服務人員", "月嫂", "薪資")):
                memo_staff_ids = []
            elif any(k in memo_text for k in ("服務人員", "月嫂", "薪資")) and not any(k in memo_text for k in ("退款", "退費")):
                memo_refund_ids = []
            else:
                return _review("counterparty_identity_type_conflict")

        if len(memo_staff_ids) > 1 or len(memo_refund_ids) > 1:
            return _review("counterparty_account_multiple_matches")
        if memo_staff_ids:
            return _result(
                "staff_salary",
                memo_staff_ids,
                "sinopac_unique_staff_case_suffix_in_memo",
                suffix,
            )
        if memo_refund_ids:
            return _result(
                "client_refund",
                memo_refund_ids,
                "sinopac_unique_client_refund_case_suffix_in_memo",
                suffix,
            )

    reference_key = (
        "transaction_reference" if row["format_id"] == "legacy" else "交易參考編號"
    )
    account = extract_sinopac_account_reference(row["bank_references"].get(reference_key))
    staff_ids = _ids_for_account(staff_accounts, account)
    if row["format_id"] == "sinopac":
        client_ids = _ids_for_account(client_refund_accounts, account)
        if client_ids and staff_ids:
            return _review("counterparty_identity_type_conflict")
        if len(client_ids) > 1:
            return _review("counterparty_account_multiple_matches")
        if client_ids:
            return _result(
                "client_refund", client_ids,
                "sinopac_unique_client_refund_account_in_transaction_reference",
                account,
            )
    if not staff_ids:
        return _review("sinopac_staff_account_no_match")
    if len(staff_ids) != 1:
        return _review("sinopac_staff_account_identity_ambiguous")
    return _result(
        "staff_salary",
        staff_ids,
        "sinopac_unique_staff_account_in_transaction_reference",
        account,
    )


def extract_client_name_from_memo(
    memo: str | None, client_names: Sequence[str]
) -> str | None:
    """Extract matching client name from memo beginning using longest prefix match."""
    if not memo or not isinstance(memo, str):
        return None
    normalized_memo = unicodedata.normalize("NFKC", memo).strip()
    for name in client_names:
        if name and normalized_memo.startswith(name):
            return name
    return None


def _is_same_month(trans_date: Any, due_date: Any) -> bool:
    if not trans_date or not due_date:
        return False
    t_str = trans_date.isoformat() if hasattr(trans_date, "isoformat") else str(trans_date)
    d_str = due_date.isoformat() if hasattr(due_date, "isoformat") else str(due_date)
    try:
        t_parts = t_str[:10].split("-")
        d_parts = d_str[:10].split("-")
        return len(t_parts) >= 2 and len(d_parts) >= 2 and t_parts[0] == d_parts[0] and t_parts[1] == d_parts[1]
    except Exception:
        return False


def _is_same_amount(debit: Any, due_amount: Any) -> bool:
    if debit is None or due_amount is None:
        return False
    try:
        return Decimal(str(debit)) == Decimal(str(due_amount))
    except Exception:
        return False


def classify_finance_transaction(
    row: Mapping[str, Any],
    client_refund_accounts: Mapping[str, Any],
    staff_accounts: Mapping[str, Any],
    client_subsidy_return_accounts: Mapping[str, Any] | None = None,
    client_receipt_candidates: Sequence[Mapping[str, Any]] = (),
    staff_case_suffixes: Mapping[str, Any] | None = None,
    client_refund_case_suffixes: Mapping[str, Any] | None = None,
    all_client_names: Sequence[str] = (),
    taishin_client_refund_candidates: Sequence[Mapping[str, Any]] = (),
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
            reference_key = "transaction_reference" if format_id == "legacy" else "交易參考編號"
            account = extract_sinopac_account_reference(row["bank_references"].get(reference_key))
            staff_ids = _ids_for_account(staff_accounts, account)
            if len(staff_ids) == 1:
                return _result("non_business_review", staff_ids,
                               "sinopac_staff_return_requires_matching", account)
            if staff_ids:
                return _review("sinopac_staff_account_identity_ambiguous")
            heuristic_result = _classify_client_receipt_heuristic(
                row, client_receipt_candidates
            )
            if heuristic_result is not None:
                return heuristic_result
            return _review("sinopac_invalid_or_missing_virtual_account")
        return _classify_sinopac_outgoing(
            row,
            staff_accounts,
            client_refund_accounts,
            staff_case_suffixes,
            client_refund_case_suffixes,
        )

    if format_id == "taishin":
        memo = row["memo"]
        government_memo = isinstance(memo, str) and "新竹市政府" in memo
        if direction == "incoming":
            if government_memo:
                return _result("government_subsidy", [], "taishin_government_memo")
            return _review("taishin_incoming_not_government")
        if government_memo:
            account = row.get("counterparty_account")
            if any(_ids_for_account(accounts, account) for accounts in (
                client_refund_accounts, staff_accounts, client_subsidy_return_accounts,
            )):
                return _review("counterparty_identity_type_conflict")
            return _result("government_subsidy", [], "taishin_government_return_memo")

        if all_client_names or taishin_client_refund_candidates:
            names_pool = sorted(
                set(all_client_names) | {c["name"] for c in taishin_client_refund_candidates if c.get("name")},
                key=len,
                reverse=True,
            )
            matched_name = extract_client_name_from_memo(memo, names_pool)
            if matched_name is not None:
                matching_obligations = [
                    c for c in taishin_client_refund_candidates if c.get("name") == matched_name
                ]
                trans_date = row.get("transaction_date")
                debit_val = row.get("debit")

                if not matching_obligations:
                    return _review("taishin_client_refund_no_open_obligation")

                month_matched = [
                    c for c in matching_obligations if _is_same_month(trans_date, c.get("due_date"))
                ]
                exact_matched = [
                    c for c in month_matched if _is_same_amount(debit_val, c.get("amount_due_ntd"))
                ]

                if len(exact_matched) == 1:
                    cand = exact_matched[0]
                    reason = (
                        "taishin_unique_client_refund_name_and_month_matched"
                        if len(matching_obligations) == 1
                        else "taishin_client_refund_disambiguated_by_month_and_amount"
                    )
                    return _result(
                        "client_refund",
                        [cand["client_id"]],
                        reason,
                        matched_name,
                    )
                if len(exact_matched) > 1:
                    return _review("taishin_client_refund_multiple_exact_matches")
                if month_matched:
                    return _review("taishin_client_refund_amount_mismatch")
                return _review("taishin_client_refund_month_no_match")

            return _review("taishin_outgoing_unrecognized")

        return _classify_taishin_outgoing(
            row,
            client_refund_accounts,
            staff_accounts,
            client_subsidy_return_accounts,
        )

    return _review("unsupported_bank_direction")
