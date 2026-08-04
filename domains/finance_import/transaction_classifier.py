"""Pure classification of normalized finance rows; classification is not reconciliation."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

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


def _normalized_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def _bank_amount(row: Mapping[str, Any]) -> int | None:
    value = row.get("credit") or row.get("debit")
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


def _heuristic_client_receipt(
    row: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    scored = tuple(
        item for item in (_score_client_candidate(row, candidate) for candidate in candidates)
        if item is not None
    )
    if not scored:
        return None
    ranked = tuple(sorted(scored, key=lambda item: (-item[0], item[1])))
    best_score, client_id, evidence = ranked[0]
    runner_up_score = ranked[1][0] if len(ranked) > 1 else 0
    if best_score < 8 or best_score - runner_up_score < 3:
        return _review("client_receipt_heuristic_ambiguous")
    return _result(
        "client_receipt",
        [client_id],
        "client_receipt_heuristic:" + "+".join(evidence),
    )


def _score_client_candidate(row, candidate):
    client_id = candidate.get("client_id")
    if isinstance(client_id, bool) or not isinstance(client_id, int) or client_id < 1:
        return None
    evidence: list[str] = []
    score = 0
    name = _normalized_text(candidate.get("name"))
    bank_text = " ".join(
        _normalized_text(row.get(field))
        for field in ("counterparty_name", "memo", "summary")
    )
    if name and name in bank_text:
        score += 5
        evidence.append("name")
    account = _normalized_text(candidate.get("account"))
    if account and account == _normalized_text(row.get("counterparty_account")):
        score += 6
        evidence.append("account")
    amount = _bank_amount(row)
    open_amounts = candidate.get("open_amounts")
    if amount is not None and isinstance(open_amounts, Sequence) and amount in open_amounts:
        score += 4
        evidence.append("amount")
    if not evidence:
        return None
    return score, client_id, tuple(evidence)


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

    refund_ids = _ids_for_account(client_refund_accounts, account)
    subsidy_return_ids = _ids_for_account(
        client_subsidy_return_accounts,
        account,
    )
    staff_ids = _ids_for_account(staff_accounts, account)
    if len(refund_ids) == 1 and not subsidy_return_ids and not staff_ids:
        return _result(
            "client_refund",
            refund_ids,
            "taishin_unique_client_refund_account",
            account,
        )
    if len(subsidy_return_ids) == 1 and not refund_ids and not staff_ids:
        return _result(
            "client_subsidy_return",
            subsidy_return_ids,
            "taishin_unique_client_refund_account",
            account,
        )
    if len(staff_ids) == 1 and not refund_ids and not subsidy_return_ids:
        return _result(
            "staff_legacy_subsidy",
            staff_ids,
            "taishin_unique_staff_account",
            account,
        )
    if (refund_ids or subsidy_return_ids) and staff_ids:
        return _review("counterparty_identity_type_conflict")
    if refund_ids and subsidy_return_ids:
        return _review("counterparty_refund_purpose_ambiguous")
    if len(refund_ids) > 1 or len(subsidy_return_ids) > 1 or len(staff_ids) > 1:
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

    if format_id in {"legacy", "sinopac"}:
        if direction == "incoming":
            if _valid_client_virtual_account(row):
                return _result("client_receipt", [], "sinopac_valid_virtual_account")
            heuristic = _heuristic_client_receipt(row, client_receipt_candidates)
            if heuristic is not None:
                return heuristic
            return _review("sinopac_invalid_or_missing_virtual_account")
        return _classify_sinopac_outgoing(row, staff_accounts)

    if format_id == "taishin":
        if direction == "incoming":
            memo = row["memo"]
            if isinstance(memo, str) and "新竹市政府" in memo:
                return _result("government_subsidy", [], "taishin_government_memo")
            heuristic = _heuristic_client_receipt(row, client_receipt_candidates)
            if heuristic is not None:
                return heuristic
            return _review("taishin_incoming_not_government")
        return _classify_taishin_outgoing(
            row,
            client_refund_accounts,
            staff_accounts,
            client_subsidy_return_accounts or {},
        )

    return _review("unsupported_bank_direction")
