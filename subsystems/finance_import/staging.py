"""
File: staging.py
Description: 建立 Finance batch、canonical row、occurrence 與初始分類 staging，不自行 commit。
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
import json
from typing import Any, Mapping

from domains.finance_import.cancellation_code import (
    extract_sinopac_memo_case_suffix,
    resolve_finance_cancellation_code,
    sinopac_memo_case_suffixes,
)
from domains.finance_import.transaction_classifier import TAISHIN_CASE_MEMO_REASON, _is_same_month, classify_finance_transaction
from domains.finance_import.transaction_fingerprint import build_dedup_fingerprint
from subsystems.client_finance.virtual_account_resolution import (
    resolve_client_virtual_account,
    resolve_client_virtual_account_suffix,
)


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    item = getattr(value, "item", None)
    if callable(item):
        converted = item()
        if isinstance(converted, Decimal):
            return str(converted)
        if isinstance(converted, (datetime, date, time)):
            return converted.isoformat()
        if isinstance(converted, (str, int, float, bool)) or converted is None:
            return converted
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=_json_default,
    )


def _matched_identity_ids(value: Any) -> list[Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("stored matched_identity_ids must be valid JSON") from exc
    if not isinstance(value, list):
        raise ValueError("matched_identity_ids must be a JSON array")
    return value


def _append_occurrence(cursor: Any, batch_id: int, row_id: int, row: Mapping[str, Any]) -> None:
    cursor.execute(
        """INSERT INTO finance_import_occurrences (
               batch_id, finance_import_row_id, source_file,
               sheet_name, source_row, warnings
           ) VALUES (%s,%s,%s,%s,%s,%s)""",
        (
            batch_id,
            row_id,
            row.get("source_file"),
            row.get("sheet_name"),
            row.get("source_row"),
            _json(row.get("warnings")),
        ),
    )


def _identity_maps(
    identity_maps: Mapping[str, Any],
) -> tuple[
    Mapping[str, Any],
    Mapping[str, Any],
    Mapping[str, Any] | None,
    tuple[Any, ...],
    Mapping[str, Any],
    Mapping[str, Any],
    tuple[str, ...],
    tuple[Any, ...],
    tuple[str, ...],
    tuple[Any, ...],
    set[str] | frozenset[str] | None,
    set[str] | frozenset[str] | None,
]:
    if not isinstance(identity_maps, Mapping):
        raise ValueError("identity_maps must be a mapping")
    client_accounts = identity_maps.get("client_refund_accounts", {})
    staff_accounts = identity_maps.get("staff_accounts", {})
    subsidy_return_accounts = identity_maps.get("client_subsidy_return_accounts")
    receipt_candidates = identity_maps.get("client_receipt_candidates", ())
    staff_case_suffixes = identity_maps.get("staff_case_suffixes", {})
    client_refund_case_suffixes = identity_maps.get("client_refund_case_suffixes", {})
    all_client_names = tuple(identity_maps.get("all_client_names", ()))
    taishin_candidates = tuple(identity_maps.get("taishin_client_refund_candidates", ()))
    all_staff_names = tuple(identity_maps.get("all_staff_names", ()))
    staff_payout_candidates = tuple(identity_maps.get("staff_payout_candidates", ()))
    known_virtual_accounts = identity_maps.get("known_virtual_accounts")
    known_case_suffixes = identity_maps.get("known_case_suffixes")
    if not isinstance(client_accounts, Mapping) or not isinstance(
        staff_accounts, Mapping
    ):
        raise ValueError("identity account maps must be mappings")
    if subsidy_return_accounts is not None and not isinstance(
        subsidy_return_accounts, Mapping
    ):
        raise ValueError("identity account maps must be mappings")
    if not isinstance(receipt_candidates, tuple):
        raise ValueError("client receipt candidates must be a tuple")
    if not isinstance(staff_case_suffixes, Mapping) or not isinstance(
        client_refund_case_suffixes, Mapping
    ):
        raise ValueError("case suffix maps must be mappings")
    return (
        client_accounts,
        staff_accounts,
        subsidy_return_accounts,
        receipt_candidates,
        staff_case_suffixes,
        client_refund_case_suffixes,
        all_client_names,
        taishin_candidates,
        all_staff_names,
        staff_payout_candidates,
        known_virtual_accounts,
        known_case_suffixes,
    )


def classify_row_with_identity_maps(
    row: Mapping[str, Any],
    identity_maps: Mapping[str, Any],
) -> dict[str, Any]:
    (
        client_accounts,
        staff_accounts,
        subsidy_return_accounts,
        receipt_candidates,
        staff_case_suffixes,
        client_refund_case_suffixes,
        all_client_names,
        taishin_candidates,
        all_staff_names,
        staff_payout_candidates,
        known_virtual_accounts,
        known_case_suffixes,
    ) = _identity_maps(identity_maps)
    try:
        return classify_finance_transaction(
            row,
            client_accounts,
            staff_accounts,
            subsidy_return_accounts,
            receipt_candidates,
            staff_case_suffixes,
            client_refund_case_suffixes,
            all_client_names,
            taishin_candidates,
            all_staff_names,
            staff_payout_candidates,
            known_virtual_accounts,
            known_case_suffixes,
            staff_name_identities=identity_maps.get("staff_name_identities"),
            client_name_identities=identity_maps.get("client_name_identities"),
            client_refund_identity_accounts=identity_maps.get("client_refund_identity_accounts"),
            client_case_suffixes=identity_maps.get("client_case_suffixes"),
        )
    except TypeError:
        return classify_finance_transaction(
            row,
            client_accounts,
            staff_accounts,
            subsidy_return_accounts,
            receipt_candidates,
        )


def _has_unique_import_case(cursor, row, classification, identity_maps):
    from domains.finance_import.transaction_classifier import TAISHIN_CLIENT_SUBSIDY_SHARED_NAME_REASON

    kind = classification["classification_type"]
    if kind == 'client_subsidy_return' and classification['reason'] == TAISHIN_CLIENT_SUBSIDY_SHARED_NAME_REASON:
        return True  # Preserve the bank row until the refund month resolves the case.
    if kind == "non_business_review":
        if (row["format_id"] in {"sinopac", "legacy"} and row["direction"] == "incoming"
                and classification["reason"] == "sinopac_staff_return_requires_matching"):
            cursor.execute(
                "SELECT DISTINCT staff_id FROM staff_bank_accounts WHERE account_no=%s AND is_primary=1",
                (classification["resolved_counterparty_account"],),
            )
            return tuple(item["staff_id"] for item in cursor.fetchall()) == tuple(classification["matched_identity_ids"])
        if (row["format_id"] == "taishin" and row["direction"] == "outgoing"
                and classification["reason"] == TAISHIN_CASE_MEMO_REASON):
            suffix = extract_sinopac_memo_case_suffix(row.get("memo"))
            return resolve_client_virtual_account_suffix(cursor, suffix)["result"] == "resolved"
        return False
    if kind == "government_subsidy":
        return True
    if kind == "client_receipt":
        code = resolve_finance_cancellation_code(row)["cancellation_code"]
        if code:
            known_accounts = identity_maps.get("known_virtual_accounts")
            if known_accounts is not None:
                return code in known_accounts
            return resolve_client_virtual_account(cursor, code)["result"] == "resolved"
    elif (row["direction"] == "outgoing" and sinopac_memo_case_suffixes(row.get("memo"))
          and kind not in {"staff_salary", "staff_legacy_subsidy"}):
        suffix = extract_sinopac_memo_case_suffix(row.get("memo"))
        resolved = resolve_client_virtual_account_suffix(cursor, suffix)
        if resolved['result'] != 'resolved':
            return False
        if kind in {'client_refund','client_subsidy_return'}:
            owners = classification['matched_identity_ids']
            cursor.execute('SELECT client_id FROM orders WHERE case_no=%s', (resolved['case_no'],))
            case = cursor.fetchone()
            return len(owners) == 1 and case is not None and int(case['client_id']) == owners[0]
        return True

    owner_ids = classification["matched_identity_ids"]
    if len(owner_ids) != 1:
        return False
    if (kind == "staff_legacy_subsidy" and row["format_id"] == "taishin"
            and row["direction"] == "outgoing" and not sinopac_memo_case_suffixes(row.get("memo"))):
        return True
    owner_id = owner_ids[0]
    owner_column = "client_id"
    if kind in {"staff_salary", "staff_legacy_subsidy"}:
        owner_column = "staff_id"
        obligations = [item for item in identity_maps.get("staff_payout_candidates", ()) if item["staff_id"] == owner_id]
    elif kind == "client_receipt":
        cursor.execute(
            "SELECT o.case_no,o.due_date,o.amount_due_ntd FROM client_obligations o "
            "JOIN orders ord ON ord.case_no=o.case_no WHERE ord.client_id=%s "
            "AND o.direction='receivable_from_client' AND o.status='open' AND o.amount_due_ntd>0",
            (owner_id,),
        )
        obligations = cursor.fetchall()
        exact = [item for item in obligations if int(item["amount_due_ntd"]) == int(row["credit"])]
        if len(exact) == 1:
            return bool(exact[0]["case_no"])
    else:
        obligation_types = {"subsidy_return"} if kind == "client_subsidy_return" else {"refund", "adjustment"}
        obligations = [item for item in identity_maps.get("taishin_client_refund_candidates", ())
                       if item["client_id"] == owner_id and item["obligation_type"] in obligation_types]

    cases = {item["case_no"] for item in obligations if item.get("case_no")}
    cursor.execute(
        f"SELECT DISTINCT case_no FROM orders WHERE {owner_column}=%s",
        (owner_id,),
    )
    cases.update(str(item['case_no']) for item in cursor.fetchall())
    if owner_column == 'staff_id':
        cursor.execute("SELECT DISTINCT case_no FROM case_staff_assignments WHERE staff_id=%s "
                       "AND status IN ('planned','active','completed')", (owner_id,))
        cases.update(str(item['case_no']) for item in cursor.fetchall())
    suffixes = sinopac_memo_case_suffixes(row.get('memo'))
    if suffixes:
        if len(suffixes) != 1:
            return False
        resolved = resolve_client_virtual_account_suffix(cursor, next(iter(suffixes)))
        return resolved['result'] == 'resolved' and resolved['case_no'] in cases
    return len(cases) == 1


def stage_finance_rows(
    cursor: Any,
    normalized_result: Mapping[str, Any],
    identity_maps: Mapping[str, Any],
    *,
    business_only: bool = False,
) -> dict[str, Any]:
    """Keep source positions for new batch facts; count earlier-batch repeats in the receipt."""
    assert callable(getattr(cursor, "execute", None)), "cursor must provide execute()"
    if not isinstance(normalized_result, Mapping):
        raise ValueError("normalized_result must be a mapping")
    rows = normalized_result.get("normalized_rows")
    if not isinstance(rows, list):
        raise ValueError("normalized_rows must be a list")
    format_id = normalized_result.get("format_id")
    sheet_name = normalized_result.get("sheet_name")
    header_row = normalized_result.get("header_row")
    source_row_count = normalized_result.get("source_row_count", len(rows))
    if format_id not in {"legacy", "taishin", "sinopac"}:
        raise ValueError("normalized_result has an unsupported format_id")
    if not isinstance(sheet_name, str) or not sheet_name:
        raise ValueError("normalized_result must include sheet_name")
    if not isinstance(header_row, int) or isinstance(header_row, bool) or header_row < 1:
        raise ValueError("normalized_result must include a positive header_row")
    if (
        isinstance(source_row_count, bool)
        or not isinstance(source_row_count, int)
        or source_row_count < len(rows)
    ):
        raise ValueError("normalized_result source_row_count is invalid")
    _identity_maps(identity_maps)

    source_files = {row.get("source_file") for row in rows if isinstance(row, Mapping)}
    source_file = normalized_result.get("source_file")
    if source_file is None and len(source_files) == 1:
        source_file = next(iter(source_files))
    cursor.execute(
        """INSERT INTO finance_import_batches
           (format_id, source_file, sheet_name, header_row, row_count, status)
           VALUES (%s,%s,%s,%s,%s,'staged')""",
        (format_id, source_file, sheet_name, header_row, source_row_count),
    )
    batch_id = cursor.lastrowid
    if not batch_id:
        raise RuntimeError("finance import batch id was not generated")

    staged_rows = []
    inserted_fingerprints = set()
    columns = "id" if business_only else (
        "id, classification_type, matched_identity_ids, "
        "resolved_counterparty_account, reconciliation_status"
    )
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("each normalized row must be a mapping")
        if row.get("format_id") != format_id or row.get("sheet_name") != sheet_name:
            raise ValueError("normalized row metadata does not match its batch")

        dedup_fingerprint = build_dedup_fingerprint(row)
        cursor.execute(
            f"SELECT {columns} FROM finance_import_rows WHERE dedup_fingerprint=%s FOR UPDATE",
            (dedup_fingerprint,),
        )
        existing = cursor.fetchone()
        if existing is not None:
            if not isinstance(existing, Mapping):
                raise TypeError("cursor must return mapping rows")
            if dedup_fingerprint in inserted_fingerprints:
                _append_occurrence(cursor, batch_id, existing["id"], row)
            skipped = {
                "row_id": existing["id"],
                "dedup_fingerprint": dedup_fingerprint,
                "result": "skipped_existing",
            }
            if not business_only:
                skipped.update(
                    classification_type=existing["classification_type"],
                    matched_identity_ids=_matched_identity_ids(existing["matched_identity_ids"]),
                    resolved_counterparty_account=existing["resolved_counterparty_account"],
                    reconciliation_status=existing["reconciliation_status"],
                )
            staged_rows.append(skipped)
            continue

        if business_only:
            classification = classify_row_with_identity_maps(row, identity_maps)
            if not _has_unique_import_case(cursor, row, classification, identity_maps):
                continue

        cursor.execute(
            """INSERT INTO finance_import_rows (
                   dedup_fingerprint, batch_id, format_id, source_file, source_bank_account,
                   sheet_name, source_row, source_reference,
                   transaction_date, transaction_time, posting_date, value_date,
                   debit, credit, direction, balance, currency,
                   summary, memo, counterparty_name, counterparty_account,
                   cancellation_code, bank_references, warnings, raw_payload,
                   reconciliation_status
                ) VALUES (
                   %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                   %s,%s,%s,%s,%s,%s,%s,%s,%s,'pending'
                )""",
            (
                dedup_fingerprint,
                batch_id,
                row.get("format_id"),
                row.get("source_file"),
                row.get("source_bank_account"),
                row.get("sheet_name"),
                row.get("source_row"),
                row.get("source_reference"),
                row.get("transaction_date"),
                row.get("transaction_time"),
                row.get("posting_date"),
                row.get("value_date"),
                row.get("debit"),
                row.get("credit"),
                row.get("direction"),
                row.get("balance"),
                row.get("currency"),
                row.get("summary"),
                row.get("memo"),
                row.get("counterparty_name"),
                row.get("counterparty_account"),
                row.get("cancellation_code"),
                _json(row.get("bank_references")),
                _json(row.get("warnings")),
                _json(row.get("raw_payload")),
            ),
        )
        staged_row_id = cursor.lastrowid
        if not staged_row_id:
            raise RuntimeError("finance import row id was not generated")

        _append_occurrence(cursor, batch_id, staged_row_id, row)
        inserted_fingerprints.add(dedup_fingerprint)

        if not business_only:
            classification = classify_row_with_identity_maps(row, identity_maps)
        classification_type = classification["classification_type"]
        matched_identity_ids = classification.get("matched_identity_ids", [])
        resolved_counterparty_account = classification.get("resolved_counterparty_account")
        reason = classification.get("reason")
        cursor.execute(
            """UPDATE finance_import_rows
               SET classification_type=%s,
                   matched_identity_ids=%s,
                   resolved_counterparty_account=%s,
                   classification_reason=%s,
                   classified_at=CURRENT_TIMESTAMP
               WHERE id=%s""",
            (
                classification_type,
                _json(matched_identity_ids),
                resolved_counterparty_account,
                reason,
                staged_row_id,
            ),
        )
        staged_rows.append(
            {
                "row_id": staged_row_id,
                "dedup_fingerprint": dedup_fingerprint,
                "classification_type": classification_type,
                "matched_identity_ids": matched_identity_ids,
                "resolved_counterparty_account": resolved_counterparty_account,
                "reconciliation_status": "pending",
                "result": "inserted",
            }
        )

    if len(staged_rows) != source_row_count:
        cursor.execute(
            "UPDATE finance_import_batches SET row_count = %s WHERE id = %s",
            (len(staged_rows), batch_id),
        )

    return {"batch_id": batch_id, "staged_rows": staged_rows}
