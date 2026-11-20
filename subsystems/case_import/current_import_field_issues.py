"""Read-only current Case Import field warnings for registry and workbench."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domains.case_import.import_field_issues import ImportFieldIssue


@dataclass(frozen=True, slots=True)
class CaseImportFieldIssues:
    case_no: str
    issues: tuple[ImportFieldIssue, ...]

    def as_dict(self):
        return {"case_no": self.case_no, "issues": [issue.as_dict() for issue in self.issues]}


@dataclass(frozen=True, slots=True)
class ImportFieldIssuePage:
    items: tuple[CaseImportFieldIssues, ...]
    next_page: int | None
    total: int | None = None

    def as_dict(self):
        return {"items": [item.as_dict() for item in self.items], "next_page": self.next_page, "total": self.total}


class ImportFieldIssuesRepository(Protocol):
    def candidate_case_nos(self, *, offset: int, limit: int, case_no: str | None) -> tuple[str, ...]: ...
    def query_case(self, case_no: str) -> tuple[ImportFieldIssue, ...]: ...


class CurrentImportFieldIssuesQuery:
    def __init__(self, repository: ImportFieldIssuesRepository):
        self._repository = repository

    def query_case(self, case_no: str) -> tuple[ImportFieldIssue, ...]:
        return self._repository.query_case(_case_no(case_no))

    def query_page(self, page: int, page_size: int, case_no: str | None = None) -> ImportFieldIssuePage:
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("import_field_issues_page_invalid")
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 100:
            raise ValueError("import_field_issues_page_size_invalid")
        identity = None if case_no is None else _case_no(case_no)
        candidates = self._repository.candidate_case_nos(offset=(page - 1) * page_size,
                                                        limit=page_size + 1, case_no=identity)
        items = tuple(CaseImportFieldIssues(number, issues) for number in candidates[:page_size]
                      if (issues := self.query_case(number)))
        # An entirely resolved candidate page can be empty and still have a
        # successor. Keep candidate pagination after current-state filtering.
        return ImportFieldIssuePage(items, page + 1 if len(candidates) > page_size else None)


def _case_no(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 50:
        raise ValueError("import_field_issues_case_no_invalid")
    return value.strip()
