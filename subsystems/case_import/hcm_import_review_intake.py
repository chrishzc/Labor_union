"""
File: hcm_import_review_intake.py
Description: 原子建立或 replay HCM Case Import review，source conflict 固定 fail closed。
"""

from __future__ import annotations

from typing import Callable, Protocol

from domains.case_import.hcm_import_review import build_hcm_import_review_root


class HcmImportReviewRepository(Protocol):
    def find_fingerprint(self, source_event_identity: str, *, for_update: bool): ...
    def append_root_and_outbox(self, root, *, canonical_case_no: str | None) -> None: ...


def record_hcm_import_review(
    connection,
    *,
    source_content_digest: str,
    source_sheet: str,
    source_row: int,
    case_identity: object,
    issue_codes: tuple[str, ...],
    evidence_snapshot: dict[str, object],
    repository: HcmImportReviewRepository,
    unit_of_work_factory: Callable[[], object] | None = None,
) -> str:
    root = build_hcm_import_review_root(
        source_content_digest=source_content_digest,
        source_sheet=source_sheet,
        source_row=source_row,
        case_identity=case_identity,
        issue_codes=issue_codes,
        evidence_snapshot=evidence_snapshot,
    )
    def persist() -> str:
        existing = repository.find_fingerprint(root.source_event_identity, for_update=True)
        if existing is None:
            repository.append_root_and_outbox(
                root,
                canonical_case_no=_canonical_case_no(case_identity),
            )
            return root.review_identity
        if existing != root.source_fingerprint.value:
            raise RuntimeError("case_import_source_conflict")
        return root.review_identity
    if unit_of_work_factory is None:
        return persist()
    with unit_of_work_factory() as unit_of_work:
        result = persist()
        unit_of_work.commit()
        return result


def _canonical_case_no(value: object) -> str | None:
    """A raw case number may create an explicit FK; masked values never do."""
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


__all__ = ["record_hcm_import_review"]
