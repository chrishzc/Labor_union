"""Formal successful statements and separately retained historical references."""
from dataclasses import dataclass
from typing import Protocol

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
    def legacy_reference_rows(self) -> tuple[StatementExportRow, ...]: ...
    def exclude_duplicate(self, candidate, kept, key, actor) -> StatementCommandReceipt: ...


class StatementArchiveApplication:
    def __init__(self, repository: StatementArchivePort):
        self.repository = repository

    def export_rows(self):
        return self.repository.export_rows()

    def legacy_reference_rows(self):
        return self.repository.legacy_reference_rows()

    def exclude_duplicate(self, candidate, kept, key, actor):
        if candidate == kept:
            raise ValueError("duplicate_requires_two_sources")
        return self.repository.exclude_duplicate(candidate, kept, key, actor)
