"""
File: source_warning_review.py
Description: 建立 Finance 無法正規化來源列的去敏 immutable review root。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


_FORMATS = frozenset({"legacy", "taishin", "sinopac"})
_FIELDS = frozenset(
    {
        "transaction_date",
        "posting_date",
        "value_date",
        "transaction_amount",
        "source_bank_account",
    }
)
_PREFIXES = (
    "finance_source_field_missing:",
    "finance_source_field_invalid:",
)


@dataclass(frozen=True, slots=True)
class FinanceSourceReview:
    review_identity: str
    source_content_digest: str
    format_id: str
    sheet_name: str
    source_row: int
    source_identity: str
    issue_codes: tuple[str, ...]


def build_finance_source_review(
    *,
    source_content_digest: str,
    format_id: str,
    sheet_name: str,
    source_row: int,
    issue_codes: tuple[str, ...],
) -> FinanceSourceReview:
    _require_digest(source_content_digest)
    if format_id not in _FORMATS:
        raise ValueError("finance_source_review_format_unknown")
    if not isinstance(sheet_name, str) or not sheet_name.strip():
        raise ValueError("finance_source_review_sheet_required")
    if isinstance(source_row, bool) or not isinstance(source_row, int) or source_row < 1:
        raise ValueError("finance_source_review_row_invalid")
    normalized_issues = tuple(sorted(set(issue_codes)))
    if not normalized_issues or any(not _known_issue(issue) for issue in normalized_issues):
        raise ValueError("finance_source_review_issue_unknown")
    identity_payload = {
        "source_content_digest": source_content_digest,
        "format_id": format_id,
        "sheet_name": sheet_name,
        "source_row": source_row,
    }
    review_identity = "finance-source-review:" + hashlib.sha256(
        json.dumps(
            identity_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return FinanceSourceReview(
        review_identity,
        source_content_digest,
        format_id,
        sheet_name.strip(),
        source_row,
        f"finance-{format_id}-row-{source_row}",
        normalized_issues,
    )


def finance_source_issue_field(issue_code: str) -> str:
    for prefix in _PREFIXES:
        if issue_code.startswith(prefix):
            field = issue_code.removeprefix(prefix)
            if field in _FIELDS:
                return field
    raise ValueError("finance_source_review_issue_unknown")


def _known_issue(issue_code: object) -> bool:
    if not isinstance(issue_code, str):
        return False
    try:
        finance_source_issue_field(issue_code)
    except ValueError:
        return False
    return True


def _require_digest(value: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("source_content_digest_must_be_sha256")


__all__ = [
    "FinanceSourceReview",
    "build_finance_source_review",
    "finance_source_issue_field",
]
