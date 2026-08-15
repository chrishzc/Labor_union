"""
File: hcm_import_review_intake.py
Description: 原子建立或 replay HCM Case Import review，source conflict 固定 fail closed。
"""

from __future__ import annotations

from domains.case_import.hcm_import_review import build_hcm_import_review_root
from infrastructure.mysql.hcm_import_review_repository import (
    HcmImportReviewMySqlUnitOfWork,
    MySqlHcmImportReviewRepository,
)


def record_hcm_import_review(
    connection,
    *,
    source_content_digest: str,
    source_sheet: str,
    source_row: int,
    case_identity: object,
    issue_codes: tuple[str, ...],
    evidence_snapshot: dict[str, object],
) -> str:
    root = build_hcm_import_review_root(
        source_content_digest=source_content_digest,
        source_sheet=source_sheet,
        source_row=source_row,
        case_identity=case_identity,
        issue_codes=issue_codes,
        evidence_snapshot=evidence_snapshot,
    )
    repository = MySqlHcmImportReviewRepository(connection)
    with HcmImportReviewMySqlUnitOfWork(connection) as unit_of_work:
        existing = repository.find_fingerprint(root.source_event_identity, for_update=True)
        if existing is None:
            repository.append_root_and_outbox(
                root,
                canonical_case_no=_canonical_case_no(case_identity),
            )
            unit_of_work.commit()
            return root.review_identity
        if existing != root.source_fingerprint.value:
            raise RuntimeError("case_import_source_conflict")
        unit_of_work.commit()
    return root.review_identity


def _canonical_case_no(value: object) -> str | None:
    """A raw case number may create an explicit FK; masked values never do."""
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


__all__ = ["record_hcm_import_review"]
