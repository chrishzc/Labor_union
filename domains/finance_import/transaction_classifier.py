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


TAISHIN_CLIENT_SUBSIDY_MEMO_REASON = "taishin_client_subsidy_case_suffix_in_memo"
TAISHIN_CASE_MEMO_REASON = "taishin_memo_case_requires_manual_scheme"


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
            )
        if memo_refund_ids:
            reference_key = 'transaction_reference' if row['format_id'] == 'legacy' else '交易參考編號'
            account = extract_sinopac_account_reference(row['bank_references'].get(reference_key))
            account_clients = _ids_for_account(client_refund_accounts, account)
            if (_ids_for_account(staff_accounts, account)
                    or (account_clients and set(account_clients) != set(memo_refund_ids))):
                return _review('counterparty_identity_type_conflict')
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
    for val in (memo, cp_name, None if row.get("format_id") == "sinopac" else row.get("summary")):
        if val and isinstance(val, str):
            search_targets.append(unicodedata.normalize("NFKC", val))
    bank_refs = row.get("bank_references")
    if isinstance(bank_refs, Mapping):
        values = (bank_refs.get("交易參考編號"),) if row.get("format_id") == "sinopac" else bank_refs.values()
        for val in values:
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
        if row["format_id"] == "taishin" and all_staff_names.count(matched_staff) > 1:
            return _review("outgoing_staff_payout_name_ambiguous")
        matching_obligations = [
            c for c in staff_payout_candidates if c.get("name") == matched_staff
        ]
        if not matching_obligations:
            return _review("outgoing_staff_payout_no_open_obligation")
        if len({c["staff_id"] for c in matching_obligations}) != 1:
            return _review("outgoing_staff_payout_name_ambiguous")

        if row['format_id'] in {'sinopac', 'taishin'}:
            reason = ('bank_transaction_date_missing' if trans_date is None
                      else 'bank_currency_not_twd' if row['format_id'] == 'taishin' and row.get('currency') is not None and str(row['currency']).upper() not in {'TWD', 'NTD'}
                      else 'due_date_missing' if any(c.get('due_date') is None for c in matching_obligations)
                      else None)
            if reason:
                return _result('staff_salary', [matching_obligations[0]['staff_id']], reason)
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
            ("staff_payout_amount_mismatch" if row["format_id"] in {"sinopac", "taishin"} else
             "outgoing_staff_payout_amount_mismatch" if len(month_matched) == 1
             else "outgoing_staff_payout_target_ambiguous"),
        )

    if matched_client is not None:
        matching_obligations = [
            c for c in taishin_client_refund_candidates
            if c.get("name") == matched_client
            and c.get("obligation_type") in {None, "refund", "adjustment"}
        ]
        if not matching_obligations:
            return _review("outgoing_client_refund_no_open_obligation")
        if len({c["client_id"] for c in matching_obligations}) != 1:
            return _review("outgoing_client_refund_name_ambiguous")

        if row["format_id"] == "sinopac":
            source_reason = (
                "bank_transaction_date_missing" if trans_date is None
                else "bank_currency_not_twd" if row.get("currency") is not None and str(row["currency"]).upper() not in {"TWD", "NTD"}
                else "due_date_missing" if any(c.get("due_date") is None for c in matching_obligations)
                else None
            )
            if source_reason:
                return _result("client_refund", [matching_obligations[0]["client_id"]], source_reason)

        month_matched = [
            c for c in matching_obligations if _is_same_month(trans_date, c.get("due_date"))
        ]
        if not month_matched:
            return _result(
                "client_refund",
                [matching_obligations[0]["client_id"]],
                "outgoing_client_refund_month_no_match",
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
                    "client_refund",
                    [matching_obligations[0]["client_id"]],
                    "outgoing_client_refund_multiple_fee_matches",
                )
            fee_matched = grouped_matches
            reason = "unique_client_refund_name_month_fee_matched"
        else:
            reason = None
        if len(fee_matched) == 1:
            cand = fee_matched[0]
            diff = Decimal(str(cand["amount_due_ntd"])) - Decimal(str(debit_val))
            if reason is None and diff == 0:
                reason = (
                    "unique_client_refund_name_and_month_matched"
                    if len(matching_obligations) == 1
                    else "client_refund_disambiguated_by_month_and_amount"
                )
            elif reason is None:
                reason = "unique_client_refund_name_month_fee_matched"
            return _result("client_refund", [cand["client_id"]], reason)
        if len(fee_matched) > 1:
            return _result(
                "client_refund",
                [matching_obligations[0]["client_id"]],
                "outgoing_client_refund_multiple_fee_matches",
            )
        return _result(
            "client_refund",
            [matching_obligations[0]["client_id"]],
            "outgoing_client_refund_amount_mismatch" if row["format_id"] == "sinopac" or len(month_matched) == 1
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
    staff_name_identities: Mapping[str, Sequence[int]] | None = None,
    client_name_identities: Mapping[str, Sequence[int]] | None = None,
    client_refund_identity_accounts: Mapping[str, Any] | None = None,
    client_case_suffixes: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify one normalized bank row without selecting a ledger target."""

    validate_normalized_row(row)
    format_id = row["format_id"]
    direction = row["direction"]
    if format_id == "sinopac" and client_refund_identity_accounts is not None:
        client_refund_accounts = client_refund_identity_accounts

    if direction == "unknown":
        return _review("direction_unknown")

    if client_subsidy_return_accounts is None:
        client_subsidy_return_accounts = client_refund_accounts
        client_refund_accounts = {}

    fallback_review: dict[str, Any] | None = None
    if direction == "outgoing" and format_id != "taishin":
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
                # Resolve the person from original evidence and the complete name
                # directory before an unpaid-only pool can select a namesake.
                is_staff_name = fee_result["classification_type"] == "staff_salary" or fee_result["reason"] in {
                    "outgoing_staff_payout_name_ambiguous", "outgoing_staff_payout_no_open_obligation",
                }
                is_client_name = fee_result["classification_type"] == "client_refund" or fee_result["reason"] in {
                    "outgoing_client_refund_name_ambiguous", "outgoing_client_refund_no_open_obligation",
                }
                if (format_id in {"sinopac", "legacy"} and is_staff_name) or (format_id == "sinopac" and is_client_name):
                    is_staff = is_staff_name
                    kind = "staff_salary" if is_staff else "client_refund"
                    identity_key = "staff_id" if is_staff else "client_id"
                    candidates = staff_payout_candidates if is_staff else tuple(
                        item for item in taishin_client_refund_candidates
                        if item.get("obligation_type") in {None, "refund", "adjustment"}
                    )
                    names = all_staff_names if is_staff else all_client_names
                    pool = sorted(set(names) | {item["name"] for item in candidates if item.get("name")}, key=len, reverse=True)
                    name = extract_name_from_row_text(row, pool)
                    directory = staff_name_identities if is_staff else client_name_identities
                    name_ids = set(directory.get(name, ())) if directory is not None else {
                        item[identity_key] for item in candidates if item.get("name") == name
                    }
                    case_ids = _ids_for_account(
                        (staff_case_suffixes if is_staff else client_refund_case_suffixes) or {},
                        extract_sinopac_memo_case_suffix(memo),
                    )
                    if is_staff:
                        matching_ids = name_ids.intersection(case_ids) if case_ids else name_ids
                        if case_ids and name_ids and not matching_ids:
                            return _review("counterparty_identity_type_conflict")
                        if len(matching_ids) != 1:
                            return _review("outgoing_staff_payout_name_ambiguous")
                        matched = sorted(matching_ids)
                        reason = fee_result["reason"]
                        if case_ids and ids != matched:
                            reason = "sinopac_unique_staff_case_suffix_in_memo"
                        return _result("staff_salary", matched, reason)
                    account = extract_sinopac_account_reference(row["bank_references"].get("交易參考編號"))
                    owners = _ids_for_account(client_refund_accounts, account)
                    other_ids = (
                        _ids_for_account(staff_accounts, account) + _ids_for_account(client_subsidy_return_accounts, account)
                    )
                    prefix = "client_refund"
                    if len(owners) == 1 and owners[0] in name_ids:
                        if other_ids or (case_ids and owners[0] not in case_ids):
                            return _review("counterparty_identity_type_conflict")
                        if ids != owners:
                            return _result(kind, owners, f"sinopac_unique_{prefix}_account_in_transaction_reference", account)
                    elif len(case_ids) == 1 and case_ids[0] in name_ids:
                        if other_ids or (owners and set(owners) != set(case_ids)):
                            return _review("counterparty_identity_type_conflict")
                        if ids != case_ids:
                            return _result(kind, case_ids, f"sinopac_unique_{prefix}_case_suffix_in_memo", account)
                    elif len(name_ids) > 1:
                        return _review(f"outgoing_{'staff_payout' if is_staff else 'client_refund'}_name_ambiguous")
                    elif len(name_ids) == 1 and fee_result["reason"].endswith("_no_open_obligation"):
                        if other_ids or (owners and set(owners) != name_ids) or (case_ids and not name_ids <= set(case_ids)):
                            return _review("counterparty_identity_type_conflict")
                        return _result(kind, sorted(name_ids), fee_result["reason"], account)
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

        # Identity is independent of an unpaid target, date and amount. The
        # application preflights subsidy purpose against same-case owner facts.
        staff_name = extract_name_from_row_text({'memo': memo}, sorted(set(all_staff_names), key=len, reverse=True))
        if staff_name is not None and staff_name_identities is not None:
            identities = tuple(staff_name_identities.get(staff_name, ()))
            if len(identities) != 1:
                return _review('outgoing_staff_payout_name_ambiguous')
            return _result('staff_legacy_subsidy', list(identities),
                'taishin_staff_subsidy_identity_pending_preflight', row.get('counterparty_account'))
        staff_result = _classify_outgoing_by_name_month_fee(
            {**row, "counterparty_name": None, "summary": None, "bank_references": {}},
            all_staff_names, staff_payout_candidates, (), (),
        )
        suffix = extract_sinopac_memo_case_suffix(memo)
        if staff_result is not None:
            if (staff_result["reason"] == "outgoing_staff_payout_no_open_obligation"
                    and suffix is not None
                    and (known_case_suffixes is None or suffix in known_case_suffixes)):
                return _review(TAISHIN_CASE_MEMO_REASON)
            if staff_result["reason"] == "outgoing_staff_payout_no_open_obligation" and staff_name_identities:
                name = extract_name_from_row_text({"memo": memo}, all_staff_names)
                identities = tuple(staff_name_identities.get(name, ()))
                if len(identities) == 1:
                    return _result("staff_salary", list(identities), staff_result["reason"], row.get("counterparty_account"))
            if staff_result["classification_type"] == "staff_salary":
                return {**staff_result, "resolved_counterparty_account": row.get("counterparty_account")}
            return staff_result
        if suffix is not None and (known_case_suffixes is None or suffix in known_case_suffixes):
            client_ids = _ids_for_account(client_case_suffixes or {}, suffix)
            client_name = extract_name_from_row_text({'memo': memo},
                sorted(client_name_identities or {}, key=len, reverse=True))
            named_clients = _ids_for_account(client_name_identities or {}, client_name)
            if named_clients and set(named_clients) != set(client_ids):
                return _review('counterparty_identity_type_conflict')
            # Combine purpose with a positively named role or the formal case
            # customer's identity; do not whitelist complete memo phrases.
            customer_subsidy = '補助' in memo_text and (
                any(word in memo_text for word in ('雇主', '客戶')) or len(named_clients) == 1)
            existing_subsidy = len(client_ids) == 1 and any(
                item.get('client_id') == client_ids[0] and item.get('obligation_type') == 'subsidy_return'
                for item in taishin_client_refund_candidates)
            if (customer_subsidy or existing_subsidy) and len(client_ids) == 1:
                return _result('client_subsidy_return', client_ids, TAISHIN_CLIENT_SUBSIDY_MEMO_REASON)
            return _review(TAISHIN_CASE_MEMO_REASON)
        return _review("taishin_outgoing_unrecognized")

    return _review("unsupported_bank_direction")
