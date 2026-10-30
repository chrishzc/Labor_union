"""Shared NAS root keeps SQL maintenance artifacts outside business attachments."""
from pathlib import Path

import pytest

from infrastructure.file.controlled_file_storage import DATABASE_BACKUP_DIRECTORY, FileSystemControlledFileStorage
from subsystems.controlled_files.contracts import ControlledFileStorageError


@pytest.mark.parametrize("directory", [DATABASE_BACKUP_DIRECTORY, DATABASE_BACKUP_DIRECTORY.upper(), DATABASE_BACKUP_DIRECTORY + ". "])
@pytest.mark.parametrize("relative_path", ["2026-10/union_db_fixture.sql.gz", "_receipts/2026-10/fixture.json", "_maintenance/fixture/backup.sql"])
def test_database_backup_area_is_neither_discovered_nor_read_as_business_files(tmp_path: Path, directory: str, relative_path: str) -> None:
    contract = tmp_path / "contracts" / "signed.pdf"
    contract.parent.mkdir()
    contract.write_bytes(b"contract")
    artifact = tmp_path / DATABASE_BACKUP_DIRECTORY / relative_path
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"synthetic maintenance artifact")
    storage = FileSystemControlledFileStorage(tmp_path, settle_seconds=0)

    assert [item.object_reference for item in storage.discover(limit=10).items] == ["contracts/signed.pdf"]
    with pytest.raises(ControlledFileStorageError) as captured:
        storage.read_verified(directory + "/" + relative_path)
    assert captured.value.code == "controlled_file_reference_invalid"
    assert not captured.value.retryable
