"""
File: beclass_review_intake.py
Description: 保存 BeClass invalid-row review，並相容同來源的 canonical evidence升級 replay。
"""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import math
from pathlib import Path
from typing import Mapping, Protocol

from domains.case_import.beclass_import_review import (
    BeClassImportSourceKind,
    InvalidBeClassImportRow,
    build_review_identity,
    fingerprint_source_row,
)


class BeClassImportReviewRepository(Protocol):
    def load(self, review_identity: str, *, for_update: bool): ...
    def append_invalid_row(self, root) -> None: ...


def record_invalid_beclass_row(
    connection,
    *,
    source_kind: BeClassImportSourceKind,
    source_content_digest: str,
    source_sheet: str,
    source_row: int,
    identifier: str,
    source_payload: Mapping[str, object],
    issue_codes,
    repository: BeClassImportReviewRepository,
) -> str:
    canonical_payload = {
        str(field): _canonical_value(value) for field, value in source_payload.items()
    }
    canonical_issues = tuple(sorted({str(item).strip() for item in issue_codes}))
    source_event_identity = _source_event_identity(source_content_digest, source_row)
    review_identity = build_review_identity(source_kind, source_event_identity)
    root = InvalidBeClassImportRow(
        review_identity,
        source_kind,
        source_event_identity,
        source_sheet.strip(),
        source_row,
        identifier.strip(),
        canonical_payload,
        canonical_issues,
        fingerprint_source_row(
            source_kind,
            source_event_identity,
            source_sheet.strip(),
            source_row,
            identifier.strip(),
            canonical_payload,
            canonical_issues,
        ),
    )
    existing = repository.load(review_identity, for_update=False)
    if existing is None:
        repository.append_invalid_row(root)
        return review_identity
    if (
        existing.root.source_fingerprint != root.source_fingerprint
        and not _same_source_issue(existing.root, root)
    ):
        raise RuntimeError("beclass_import_review_source_conflict")
    return review_identity


def _same_source_issue(existing, candidate) -> bool:
    return (
        existing.source_kind is candidate.source_kind
        and existing.source_event_identity == candidate.source_event_identity
        and existing.source_sheet == candidate.source_sheet
        and existing.source_row == candidate.source_row
        and existing.identifier == candidate.identifier
        and existing.issue_codes == candidate.issue_codes
    )


def canonical_review_identifier(source_kind, stable_identity, fallback) -> str:
    raw = str(stable_identity or fallback or "").strip()
    return raw if raw else f"{source_kind.value}-unknown"

def fingerprint_workbook(workbook_path: str) -> str:
    return hashlib.sha256(Path(workbook_path).read_bytes()).hexdigest()


def _source_event_identity(source_content_digest: str, source_row: int) -> str:
    if (
        not isinstance(source_content_digest, str)
        or len(source_content_digest) != 64
        or any(character not in "0123456789abcdef" for character in source_content_digest)
    ):
        raise ValueError("source_content_digest must be lowercase SHA-256 hex")
    return f"beclass-workbook:{source_content_digest}:row:{source_row}"


def _canonical_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if value.is_integer():
            return int(value)
    return str(value).strip()


__all__ = ["fingerprint_workbook", "canonical_review_identifier", "record_invalid_beclass_row"]
