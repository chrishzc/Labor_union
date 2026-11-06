"""
File: transaction_classifier.py
Description: 純函式正規化銀行流水分類，驗證既有案件與對象身分證據且不直接核銷。
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


def extract_name_from_row_text(row: Mapping[str, Any], names: Sequence[str]) -> str | None:
    if not names:
        return None
    memo = row.get("memo")
    prefix_match = extract_client_name_from_memo(memo, names)
    if prefix_match:
        return prefix_match

    cp_name = row.get("counterparty_name")
    if cp_name and isinstance(cp_name, str):
        normalized_cp = unicodedata.normalize("NFKC", cp_name).strip()
        for name in names:
            if name and (normalized_cp == name or normalized_cp.startswith(name)):
                return name

    search_targets = []
    for val in (memo, cp_name, row.get("summary")):
        if val and isinstance(val, str):
            search_targets.append(unicodedata.normalize("NFKC", val))
    bank_refs = row.get("bank_references")
    if isinstance(bank_refs, Mapping):
        for val in bank_refs.values():
            if val and isinstance(val, str):
                search_targets.append(unicodedata.normalize("NFKC", val))
    combined = " ".join(search_targets)
    for name in names:
        if name and name in combined:
            return name
    return None


def _is_valid_fee_diff(debit: Any, due_amount: Any) -> bool:
    if debit is None or due_amount is None:
        return False
    try:
        diff = Decimal(str(due_amount)) - Decimal(str(debit))
        return Decimal("0") <= diff <= Decimal("100")
    except Exception:
        return False


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


def _classify_outgoing_by_name_month_fee(
    row: Mapping[str, Any],
    all_staff_names: Sequence[str],
    staff_payout_candidates: Sequence[Mapping[str, Any]],
    all_client_names: Sequence[str],
    taishin_client_refund_candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    staff_pool = sorted(
        set(all_staff_names) | {c["name"] for c in staff_payout_candidates if c.get("name")},
        key=len,
        reverse=True,
    )
    client_pool = sorted(
        set(all_client_names) | {c["name"] for c in taishin_client_refund_candidates if c.get("name")},
        key=len,
        reverse=True,
    )
    if not staff_pool and not client_pool:
        return None

    matched_staff = extract_name_from_row_text(row, staff_pool) if staff_pool else None
    matched_client = extract_name_from_row_text(row, client_pool) if client_pool else None

    if matched_staff and matched_client:
        memo_text = unicodedata.normalize("NFKC", str(row.get("memo") or ""))
        is_staff_kw = any(k in memo_text for k in ("服務人員", "月嫂", "薪資"))
        is_client_kw = any(k in memo_text for k in ("退款", "退費", "客戶"))
        if is_staff_kw and not is_client_kw:
            matched_client = None
        elif is_client_kw and not is_staff_kw:
            matched_staff = None
        else:
            return _review("counterparty_identity_type_conflict")

    trans_date = row.get("transaction_date")
    debit_val = row.get("debit")

    if matched_staff is not None:
        matching_obligations = [
            c for c in staff_payout_candidates if c.get("name") == matched_staff
        ]
        if not matching_obligations:
            return _review("outgoing_staff_payout_no_open_obligation")
        if len({c["staff_id"] for c in matching_obligations}) != 1:
            return _review("outgoing_staff_payout_name_ambiguous")

        month_matched = [
            c for c in matching_obligations if _is_same_month(trans_date, c.get("due_date"))
        ]
        if not month_matched:
            return _result(
                "staff_salary", [matching_obligations[0]["staff_id"]],
                "outgoing_staff_payout_month_no_match",
            )

        fee_matched = [
            c for c in month_matched if _is_valid_fee_diff(debit_val, c.get("amount_due_ntd"))
        ]
        if len(month_matched) > 1 and _is_valid_fee_diff(
            debit_val, sum(c["amount_due_ntd"] for c in month_matched)
        ):
            if fee_matched:
                return _result(
                    "staff_salary", [matching_obligations[0]["staff_id"]],
                    "outgoing_staff_payout_multiple_fee_matches",
                )
            return _result(
                "staff_salary", [month_matched[0]["staff_id"]],
                "unique_staff_payout_name_month_fee_matched",
            )
        if len(fee_matched) == 1:
            cand = fee_matched[0]
            diff = Decimal(str(cand["amount_due_ntd"])) - Decimal(str(debit_val))
            if diff == 0:
                reason = (
                    "unique_staff_payout_name_and_month_matched"
                    if len(matching_obligations) == 1
                    else "staff_payout_disambiguated_by_month_and_amount"
                )
            else:
                reason = "unique_staff_payout_name_month_fee_matched"
            return _result("staff_salary", [cand["staff_id"]], reason)
        if len(fee_matched) > 1:
            return _result(
                "staff_salary", [matching_obligations[0]["staff_id"]],
                "outgoing_staff_payout_multiple_fee_matches",
            )
        return _result(
            "staff_salary", [matching_obligations[0]["staff_id"]],
            "outgoing_staff_payout_amount_mismatch" if len(month_matched) == 1
            else "outgoing_staff_payout_target_ambiguous",
        )

    if matched_client is not None:
        is_taishin = row["format_id"] == "taishin"
        allowed_types = {"subsidy_return"} if is_taishin else {"refund", "adjustment"}
        matching_obligations = [
            c for c in taishin_client_refund_candidates
            if c.get("name") == matched_client
            and (c.get("obligation_type") is None or c["obligation_type"] in allowed_types)
        ]
        if not matching_obligations:
            return _review("taishin_client_refund_no_open_obligation")
        if len({c["client_id"] for c in matching_obligations}) != 1:
            return _review("outgoing_client_refund_name_ambiguous")

        month_matched = [
            c for c in matching_obligations if _is_same_month(trans_date, c.get("due_date"))
        ]
        if not month_matched:
            return _result(
                "client_subsidy_return" if is_taishin else "client_refund",
                [matching_obligations[0]["client_id"]],
                "taishin_client_refund_month_no_match",
            )

        fee_matched = [
            c for c in month_matched if _is_valid_fee_diff(debit_val, c.get("amount_due_ntd"))
        ]
        by_case = {}
        for item in month_matched:
            by_case.setdefault(item.get("case_no"), []).append(item)
        grouped_matches = [
            group[0] for group in by_case.values()
            if len(group) > 1 and _is_valid_fee_diff(
                debit_val, sum(item["amount_due_ntd"] for item in group)
            )
        ]
        if grouped_matches:
            if len(grouped_matches) != 1 or fee_matched:
                return _result(
                    "client_subsidy_return" if is_taishin else "client_refund",
                    [matching_obligations[0]["client_id"]],
                    "taishin_client_refund_multiple_exact_matches",
                )
            fee_matched = grouped_matches
            reason = "taishin_unique_client_refund_name_month_fee_matched"
        else:
            reason = None
        if len(fee_matched) == 1:
            cand = fee_matched[0]
            diff = Decimal(str(cand["amount_due_ntd"])) - Decimal(str(debit_val))
            if reason is None and diff == 0:
                reason = (
                    "taishin_unique_client_refund_name_and_month_matched"
                    if len(matching_obligations) == 1
                    else "taishin_client_refund_disambiguated_by_month_and_amount"
                )
            elif reason is None:
                reason = "taishin_unique_client_refund_name_month_fee_matched"
            kind = "client_subsidy_return" if cand.get("obligation_type") == "subsidy_return" else "client_refund"
            return _result(kind, [cand["client_id"]], reason)
        if len(fee_matched) > 1:
            return _result(
                "client_subsidy_return" if is_taishin else "client_refund",
                [matching_obligations[0]["client_id"]],
                "taishin_client_refund_multiple_exact_matches",
            )
        return _result(
            "client_subsidy_return" if is_taishin else "client_refund",
            [matching_obligations[0]["client_id"]],
            "taishin_client_refund_amount_mismatch" if len(month_matched) == 1
            else "outgoing_client_refund_target_ambiguous",
        )

    return None


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
    all_staff_names: Sequence[str] = (),
    staff_payout_candidates: Sequence[Mapping[str, Any]] = (),
    known_virtual_accounts: set[str] | frozenset[str] | None = None,
    known_case_suffixes: set[str] | frozenset[str] | None = None,
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

    fallback_review: dict[str, Any] | None = None
    if direction == "outgoing":
        memo = row.get("memo")
        government_memo = isinstance(memo, str) and any(marker in memo for marker in ("新竹市政府", "新竹市府"))
        if not government_memo:
            fee_result = _classify_outgoing_by_name_month_fee(
                row,
                all_staff_names,
                staff_payout_candidates,
                all_client_names,
                taishin_client_refund_candidates,
            )
            if fee_result is not None:
                ids = fee_result["matched_identity_ids"]
                if ids:
                    is_staff = fee_result["classification_type"] == "staff_salary"
                    suffix = extract_sinopac_memo_case_suffix(memo)
                    case_ids = _ids_for_account(
                        (staff_case_suffixes if is_staff else client_refund_case_suffixes) or {}, suffix
                    )
                    account = row.get("counterparty_account")
                    if format_id in {"sinopac", "legacy"} and not account:
                        key = "transaction_reference" if format_id == "legacy" else "交易參考編號"
                        account = extract_sinopac_account_reference(row["bank_references"].get(key))
                    account_ids = (
                        _ids_for_account(staff_accounts, account) if is_staff
                        else _ids_for_account(client_refund_accounts, account)
                        + _ids_for_account(client_subsidy_return_accounts, account)
                    )
                    other_ids = (
                        _ids_for_account(client_refund_accounts, account)
                        + _ids_for_account(client_subsidy_return_accounts, account)
                        if is_staff else _ids_for_account(staff_accounts, account)
                    )
                    if other_ids or any(candidates and set(candidates) != set(ids) for candidates in (account_ids, case_ids)):
                        return _review("counterparty_identity_type_conflict")
                    return {**fee_result, "resolved_counterparty_account": account}
                if fee_result["reason"] in {
                    "counterparty_identity_type_conflict",
                    "outgoing_staff_payout_name_ambiguous",
                    "outgoing_client_refund_name_ambiguous",
                }:
                    return fee_result
                fallback_review = fee_result

    if format_id in {"legacy", "sinopac"}:
        if direction == "incoming":
            cancellation_code = resolve_finance_cancellation_code(row)["cancellation_code"]
            if cancellation_code is not None and (
                known_virtual_accounts is None or cancellation_code in known_virtual_accounts
            ):
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
            if cancellation_code is not None:
                return _review("sinopac_virtual_account_case_not_found")
            return _review("sinopac_invalid_or_missing_virtual_account")
        sinopac_result = _classify_sinopac_outgoing(
            row,
            staff_accounts,
            client_refund_accounts,
            staff_case_suffixes,
            client_refund_case_suffixes,
        )
        if sinopac_result["classification_type"] == "non_business_review" and fallback_review is not None:
            return fallback_review
        return sinopac_result

    if format_id == "taishin":
        memo = row.get("memo")
        memo_text = unicodedata.normalize("NFKC", memo) if isinstance(memo, str) else ""
        government_memo = bool(memo_text and ("新竹市政府" in memo_text or "新竹市府" in memo_text))
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

        is_staff_kw = any(k in memo_text for k in ("服務人員", "月嫂", "薪資", "補助款"))
        is_refund_kw = any(k in memo_text for k in ("退款", "退費", "客戶"))
        suffix = extract_sinopac_memo_case_suffix(memo)

        if suffix is not None and (known_case_suffixes is None or suffix in known_case_suffixes):
            staff_case_map = staff_case_suffixes or {}
            refund_case_map = client_refund_case_suffixes or {}
            memo_staff_ids = _ids_for_account(staff_case_map, suffix)
            memo_refund_ids = _ids_for_account(refund_case_map, suffix)

            if memo_staff_ids and memo_refund_ids:
                if is_staff_kw and not is_refund_kw:
                    memo_refund_ids = []
                elif is_refund_kw and not is_staff_kw:
                    memo_staff_ids = []
                else:
                    return _review("counterparty_identity_type_conflict")

            if len(memo_staff_ids) > 1 or len(memo_refund_ids) > 1:
                return _review("counterparty_account_multiple_matches")
            if memo_staff_ids:
                return _result(
                    "staff_salary",
                    memo_staff_ids,
                    "taishin_unique_staff_case_suffix_in_memo",
                    suffix,
                )
            if memo_refund_ids:
                return _result(
                    "client_refund",
                    memo_refund_ids,
                    "taishin_unique_client_refund_case_suffix_in_memo",
                    suffix,
                )
            if known_case_suffixes is not None and suffix in known_case_suffixes:
                if is_staff_kw and not is_refund_kw:
                    return _result(
                        "staff_salary",
                        [],
                        "taishin_staff_case_suffix_in_memo",
                        suffix,
                    )
                if is_refund_kw and not is_staff_kw:
                    return _result(
                        "client_refund",
                        [],
                        "taishin_client_refund_case_suffix_in_memo",
                        suffix,
                    )

        if is_staff_kw and not is_refund_kw:
            account = row.get("counterparty_account")
            staff_ids = _ids_for_account(staff_accounts, account)
            if len(staff_ids) == 1:
                return _result(
                    "staff_salary",
                    staff_ids,
                    "taishin_unique_staff_account",
                    account,
                )
            if len(staff_ids) > 1:
                return _review("counterparty_account_multiple_matches")

        taishin_result = _classify_taishin_outgoing(
            row,
            client_refund_accounts,
            staff_accounts,
            client_subsidy_return_accounts,
        )
        if (
            taishin_result["classification_type"] != "non_business_review"
            or taishin_result["reason"] in {"counterparty_identity_type_conflict", "counterparty_account_multiple_matches"}
        ):
            return taishin_result
        if fallback_review is not None:
            return fallback_review
        if all_client_names or taishin_client_refund_candidates or all_staff_names or staff_payout_candidates:
            return _review("taishin_outgoing_unrecognized")
        return taishin_result

    return _review("unsupported_bank_direction")
