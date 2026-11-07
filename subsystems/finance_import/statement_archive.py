"""Successful bank statements: full read-only export and explicit manual commands."""
from dataclasses import dataclass
from typing import Protocol

from domains.finance_import.statement_archive import validate_manual_statement
from shared_kernel.ports import UnitOfWork
from collections.abc import Callable


class StatementCommandConflict(ValueError):
    pass


class ManualStatementReplacementRequired(ValueError):
    """Fresh manual accounting belongs to the existing case-scoped command."""
    code = "case_manual_supplement_required"

    def __init__(self):
        super().__init__(self.code)


@dataclass(frozen=True)
class StatementExportRow:
    identity: str
    bank: str
    source: str
    cases: tuple[str, ...]
    fields: tuple[tuple[str, object], ...]


@dataclass(frozen=True)
class StatementCommandReceipt:
    identity: str | None
    saved_count: int
    excluded_count: int


class StatementArchivePort(Protocol):
    def export_rows(self) -> tuple[StatementExportRow, ...]: ...
    def create_manual(self, fields, key, actor, duplicate_of) -> StatementCommandReceipt: ...
    def exclude_duplicate(self, candidate, kept, key, actor) -> StatementCommandReceipt: ...


class StatementArchiveApplication:
    def __init__(self, repository: StatementArchivePort, unit_of_work_factory: Callable[[], UnitOfWork]):
        self.repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def export_rows(self):
        return self.repository.export_rows()

    def create_manual(self, fields, key, actor, duplicate_of=None):
        values = validate_manual_statement(fields)
        with self._unit_of_work_factory() as unit_of_work:
            result = self.repository.create_manual(values, key, actor, duplicate_of)
            unit_of_work.commit()
        return result

    def exclude_duplicate(self, candidate, kept, key, actor):
        if candidate == kept:
            raise ValueError("duplicate_requires_two_sources")
        with self._unit_of_work_factory() as unit_of_work:
            result = self.repository.exclude_duplicate(candidate, kept, key, actor)
            unit_of_work.commit()
        return result
