"""Successful bank statements: full read-only export and explicit manual commands."""
from dataclasses import dataclass
from typing import Protocol

from domains.finance_import.statement_archive import validate_manual_statement


class StatementCommandConflict(ValueError):
    pass


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
    def __init__(self, repository: StatementArchivePort):
        self.repository = repository

    def export_rows(self):
        return self.repository.export_rows()

    def create_manual(self, fields, key, actor, duplicate_of=None):
        values = validate_manual_statement(fields)
        return self.repository.create_manual(values, key, actor, duplicate_of)

    def exclude_duplicate(self, candidate, kept, key, actor):
        if candidate == kept:
            raise ValueError("duplicate_requires_two_sources")
        return self.repository.exclude_duplicate(candidate, kept, key, actor)
