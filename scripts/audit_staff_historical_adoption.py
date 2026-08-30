"""
File: audit_staff_historical_adoption.py
Description: 唯讀列出 Staff 歷史來源逐列、receipt與目前 Staff root的去敏一致性證據。
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import re

import pymysql

from scripts.imports.import_staff_beclass import (
    DB_CONFIG,
    _load_staff_beclass_frame,
    clean_data,
)
from domains.case_import.staff_import_validation import validate_staff_row
from subsystems.case_import.beclass_review_intake import fingerprint_workbook


_SUCCESS_OUTCOMES = frozenset({"created", "adopted_existing"})
_DATABASE_PATTERN = re.compile(r"lu_test_[a-z0-9_]+")


def _require_validation_database() -> str:
    """Refuse the historical audit unless it targets an isolated test DB."""

    database = str(DB_CONFIG.get("database") or "").strip()
    if not _DATABASE_PATTERN.fullmatch(database):
        raise ValueError("staff historical audit requires a lu_test_* database")
    if os.getenv("APP_ENV", "development").strip().lower() in {"prod", "production"}:
        raise ValueError("staff historical audit requires a development validation profile")
    return database


def audit_staff_historical_adoption(workbook_path: str) -> dict[str, object]:
    database = _require_validation_database()
    selected = _load_staff_beclass_frame(workbook_path)
    if selected is None:
        raise RuntimeError("staff_historical_audit_sheet_contract_not_unique")
    _, frame = selected
    content_digest = fingerprint_workbook(workbook_path)
    source_evidence_by_row = _source_evidence_by_row(frame)
    connection = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    try:
        results = tuple(
            _audit_row(
                connection,
                content_digest,
                source_row,
                source_evidence_by_row[source_row],
            )
            for source_row, (_, row) in enumerate(frame.iterrows(), start=2)
        )
        staff_total = _staff_total(connection)
    finally:
        connection.close()
    reasons = Counter(item["reason"] for item in results)
    root_mappings = _summarize_root_mappings(results, source_evidence_by_row)
    return {
        "database": database,
        "source_rows": len(results),
        "staff_total": staff_total,
        "reason_counts": dict(sorted(reasons.items())),
        "root_mappings": root_mappings,
        "rows": results,
    }


def _audit_row(connection, content_digest, source_row, source_evidence) -> dict[str, object]:
    identity_card = source_evidence["identity_card"]["normalized_value"]
    name = source_evidence["name"]["normalized_value"]
    source_identity = f"staff-workbook:{content_digest}:row:{source_row}"
    receipt = _load_receipt(connection, source_identity)
    reason = _replay_reason(receipt, identity_card, name)
    return {
        "source_row": source_row,
        "reason": reason,
        "receipt_outcome": None if receipt is None else str(receipt["outcome"]),
        "staff_id": None if receipt is None or receipt["staff_id"] is None else int(receipt["staff_id"]),
        "source_evidence": _public_source_evidence(source_evidence),
        "root_evidence": _root_evidence(receipt, identity_card, name),
    }


def _load_receipt(connection, source_identity):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT receipt.source_fingerprint,receipt.staff_id,receipt.outcome,"
            "staff.id AS live_staff_id,staff.identity_card AS live_identity_card,"
            "staff.name AS live_name "
            "FROM staff_historical_adoption_receipts AS receipt "
            "LEFT JOIN staff ON staff.id=receipt.staff_id "
            "WHERE receipt.source_event_identity=%s",
            (source_identity,),
        )
        return cursor.fetchone()


def _replay_reason(receipt, identity_card: str | None, name: str | None) -> str:
    if receipt is None:
        return "receipt_missing"
    outcome = str(receipt["outcome"])
    if outcome not in _SUCCESS_OUTCOMES:
        return f"receipt_outcome:{outcome}"
    if receipt["staff_id"] is None or receipt["live_staff_id"] is None:
        return "staff_root_missing"
    if str(receipt["live_identity_card"] or "").strip() != str(
        identity_card or ""
    ).strip():
        return "staff_identity_mismatch"
    if str(receipt["live_name"] or "").strip() != str(name or "").strip():
        return "staff_name_mismatch"
    return "exact_replay_verified"


def _source_evidence_by_row(frame) -> dict[int, dict[str, object]]:
    raw_rows = tuple(frame.iterrows())
    identity_values = tuple(clean_data(row.get("身分證字號"), "identity_card") for _, row in raw_rows)
    name_values = tuple(clean_data(row.get("姓名"), "name") for _, row in raw_rows)
    identity_labels = _private_group_labels(identity_values, "identity")
    name_labels = _private_group_labels(name_values, "name")
    return {
        source_row: _source_row_evidence(row, identity_labels, name_labels)
        for source_row, (_, row) in enumerate(raw_rows, start=2)
    }


def _source_row_evidence(row, identity_labels, name_labels) -> dict[str, object]:
    raw_identity = row.get("身分證字號")
    raw_name = row.get("姓名")
    identity_card = clean_data(raw_identity, "identity_card")
    name = clean_data(raw_name, "name")
    return {
        "identity_card": _value_evidence(raw_identity, identity_card, identity_labels),
        "name": _value_evidence(raw_name, name, name_labels),
        "validation_issue_fields": tuple(sorted(validate_staff_row(row.to_dict()))),
    }


def _private_group_labels(values, prefix: str) -> dict[str | None, str]:
    labels: dict[str | None, str] = {}
    for value in values:
        canonical = value or None
        if canonical not in labels:
            labels[canonical] = "blank" if canonical is None else f"{prefix}-{len(labels) + 1:02d}"
    return labels


def _value_evidence(raw_value, normalized_value, labels) -> dict[str, object]:
    canonical = normalized_value or None
    return {
        "normalized_value": normalized_value,
        "group": labels[canonical],
        "raw_type": type(raw_value).__name__,
        "blank": canonical is None,
        "trimmed": isinstance(raw_value, str) and raw_value != normalized_value,
    }


def _public_source_evidence(source_evidence) -> dict[str, object]:
    return {
        "identity_card": _public_value_evidence(source_evidence["identity_card"]),
        "name": _public_value_evidence(source_evidence["name"]),
        "validation_issue_fields": list(source_evidence["validation_issue_fields"]),
    }


def _public_value_evidence(value_evidence) -> dict[str, object]:
    return {
        field: value_evidence[field]
        for field in ("group", "raw_type", "blank", "trimmed")
    }


def _root_evidence(receipt, identity_card, name) -> dict[str, bool | None]:
    if receipt is None or receipt["live_staff_id"] is None:
        return {"staff_root_present": False, "identity_card_matches_source": None, "name_matches_source": None}
    return {
        "staff_root_present": True,
        "identity_card_matches_source": str(receipt["live_identity_card"] or "").strip() == str(identity_card or "").strip(),
        "name_matches_source": str(receipt["live_name"] or "").strip() == str(name or "").strip(),
    }


def _summarize_root_mappings(
    rows: tuple[dict[str, object], ...],
    source_evidence_by_row: dict[int, dict[str, object]],
) -> dict[str, object]:
    source_rows_by_staff_id: dict[int, list[int]] = {}
    for row in rows:
        if row["reason"] != "exact_replay_verified" or row["staff_id"] is None:
            continue
        source_rows_by_staff_id.setdefault(int(row["staff_id"]), []).append(int(row["source_row"]))
    reused_roots = tuple(
        {"staff_id": staff_id, "source_rows": source_rows}
        for staff_id, source_rows in sorted(source_rows_by_staff_id.items())
        if len(source_rows) > 1
    )
    return {
        "verified_replay_rows": sum(len(source_rows) for source_rows in source_rows_by_staff_id.values()),
        "distinct_verified_staff_roots": len(source_rows_by_staff_id),
        "shared_staff_roots": tuple(
            _shared_root_evidence(item, source_evidence_by_row) for item in reused_roots
        ),
    }


def _shared_root_evidence(
    root_mapping: dict[str, object], source_evidence_by_row: dict[int, dict[str, object]]
) -> dict[str, object]:
    source_rows = [int(value) for value in root_mapping["source_rows"]]
    identity_groups = [source_evidence_by_row[source_row]["identity_card"]["group"] for source_row in source_rows]
    name_groups = [source_evidence_by_row[source_row]["name"]["group"] for source_row in source_rows]
    return {
        **root_mapping,
        "identity_card_groups": identity_groups,
        "name_groups": name_groups,
        "same_normalized_identity_card": len(set(identity_groups)) == 1,
        "same_normalized_name": len(set(name_groups)) == 1,
    }


def _staff_total(connection) -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS count FROM staff")
        return int(cursor.fetchone()["count"])


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Staff historical adoption replay audit."
    )
    parser.add_argument("workbook")
    options = parser.parse_args(arguments)
    try:
        result = audit_staff_historical_adoption(options.workbook)
    except Exception as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["audit_staff_historical_adoption"]
