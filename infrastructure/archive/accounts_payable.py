"""Atomic permanent archive for generated accounts-payable workbooks."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile

from subsystems.staff_payables.accounts_payable_export import (
    ArchivedWorkbook,
    ArchivedWorkbookRecord,
)


class LocalAccountsPayableArchive:
    def __init__(self, repository_root: Path) -> None:
        self._archive_root = (
            repository_root
            / "downloads"
            / "accounts_payable_archive"
        ).resolve()

    def save(
        self,
        year: int,
        filename: str,
        workbook_bytes: bytes,
        expected_sha256: str,
    ) -> ArchivedWorkbook:
        target = self._target_path(year, filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError("accounts payable archive never overwrites")
        temporary_path = self._write_temporary(target.parent, workbook_bytes)
        try:
            os.link(temporary_path, target)
        finally:
            temporary_path.unlink(missing_ok=True)
        actual_sha256 = _verify_archive(target, expected_sha256)
        return ArchivedWorkbook(str(target), actual_sha256)

    def list(self, year: int) -> tuple[ArchivedWorkbookRecord, ...]:
        directory = self._target_directory(year)
        if not directory.exists():
            return ()
        paths = sorted(
            directory.glob("accounts-payable-*.xlsx"),
            key=lambda path: path.name,
            reverse=True,
        )
        return tuple(_archive_record(path) for path in paths[:200])

    def _target_directory(self, year: int) -> Path:
        if year < 2000 or year > 9999:
            raise ValueError("archive year is invalid")
        return (self._archive_root / str(year)).resolve()

    def _target_path(self, year: int, filename: str) -> Path:
        if Path(filename).name != filename or not filename.endswith(".xlsx"):
            raise ValueError("archive filename is invalid")
        target = (self._target_directory(year) / filename).resolve()
        if self._archive_root not in target.parents:
            raise ValueError("archive target escaped the archive root")
        return target

    def _write_temporary(self, parent: Path, content: bytes) -> Path:
        descriptor, name = tempfile.mkstemp(
            prefix=".accounts-payable-",
            suffix=".tmp",
            dir=parent,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            Path(name).unlink(missing_ok=True)
            raise
        return Path(name)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65_536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_archive(target: Path, expected_sha256: str) -> str:
    actual_sha256 = _file_sha256(target)
    if actual_sha256 == expected_sha256:
        return actual_sha256
    target.unlink()
    raise RuntimeError("accounts_payable_archive_failed")


def _archive_record(path: Path) -> ArchivedWorkbookRecord:
    return ArchivedWorkbookRecord(
        filename=path.name,
        absolute_path=str(path.resolve()),
        sha256=_file_sha256(path),
        size_bytes=path.stat().st_size,
    )
