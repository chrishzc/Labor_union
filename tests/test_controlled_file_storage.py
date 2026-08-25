"""
File: test_controlled_file_storage.py
Description: 驗證受控 NAS 唯讀探索、路徑隔離、穩定檔案判定及 digest 讀取契約。
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from infrastructure.file.controlled_file_storage import FileSystemControlledFileStorage
from subsystems.controlled_files.contracts import (
    ControlledFileStorageError,
    ControlledFileStorageStatus,
)


def _write_stable(path: Path, content: bytes, *, modified_at: float = 100.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.utime(path, (modified_at, modified_at))


def test_unconfigured_or_missing_root_is_explicit_and_never_created(tmp_path: Path) -> None:
    missing_root = tmp_path / "not-mounted"

    unconfigured = FileSystemControlledFileStorage(None)
    missing = FileSystemControlledFileStorage(missing_root)

    assert unconfigured.readiness().status is ControlledFileStorageStatus.UNCONFIGURED
    assert missing.readiness().status is ControlledFileStorageStatus.MOUNT_UNAVAILABLE
    assert not missing_root.exists()

    with pytest.raises(ControlledFileStorageError) as captured:
        missing.discover(limit=10)

    assert captured.value.code == "controlled_file_storage_mount_unavailable"
    assert str(missing_root) not in str(captured.value)


def test_discovery_projects_only_stable_folder_and_file_names_with_bounded_paging(
    tmp_path: Path,
) -> None:
    _write_stable(tmp_path / "contracts" / "signed.pdf", b"pdf")
    _write_stable(tmp_path / "staff" / "resume.docx", b"resume")
    _write_stable(tmp_path / ".private" / "hidden.txt", b"hidden")
    _write_stable(tmp_path / "contracts" / "upload.tmp", b"partial")
    fresh = tmp_path / "contracts" / "still-writing.pdf"
    fresh.write_bytes(b"fresh")
    os.utime(fresh, (199.0, 199.0))
    storage = FileSystemControlledFileStorage(tmp_path, clock=lambda: 200.0)

    first_page = storage.discover(limit=1)
    second_page = storage.discover(limit=1, after=first_page.next_after)

    assert first_page.items[0].logical_folder == "contracts"
    assert first_page.items[0].filename == "signed.pdf"
    assert first_page.items[0].object_reference == "contracts/signed.pdf"
    assert first_page.next_after == "contracts/signed.pdf"
    assert second_page.items[0].logical_folder == "staff"
    assert second_page.items[0].filename == "resume.docx"
    assert second_page.next_after is None


@pytest.mark.parametrize("reference", ["../outside.pdf", "/absolute.pdf", "C:/drive.pdf", "a\\b.pdf"])
def test_invalid_object_reference_fails_closed(tmp_path: Path, reference: str) -> None:
    storage = FileSystemControlledFileStorage(tmp_path, settle_seconds=0)

    with pytest.raises(ControlledFileStorageError) as captured:
        storage.read_verified(reference)

    assert captured.value.code == "controlled_file_reference_invalid"
    assert not captured.value.retryable


def test_verified_read_returns_content_and_rejects_digest_mismatch(tmp_path: Path) -> None:
    content = b"signed-contract"
    target = tmp_path / "contracts" / "final.pdf"
    _write_stable(target, content)
    expected = hashlib.sha256(content).hexdigest()
    storage = FileSystemControlledFileStorage(tmp_path, clock=lambda: 200.0)

    result = storage.read_verified("contracts/final.pdf", expected_sha256=expected)

    assert result.filename == "final.pdf"
    assert result.content_type == "application/pdf"
    assert result.content == content
    assert result.content_sha256 == expected

    with pytest.raises(ControlledFileStorageError) as captured:
        storage.read_verified("contracts/final.pdf", expected_sha256="0" * 64)

    assert captured.value.code == "controlled_file_digest_mismatch"
    assert not captured.value.retryable


def test_fresh_file_is_retryable_and_not_discovered(tmp_path: Path) -> None:
    target = tmp_path / "baby-log" / "meal.jpg"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"photo")
    os.utime(target, (198.0, 198.0))
    storage = FileSystemControlledFileStorage(tmp_path, settle_seconds=5, clock=lambda: 200.0)

    assert storage.discover(limit=10).items == ()
    with pytest.raises(ControlledFileStorageError) as captured:
        storage.read_verified("baby-log/meal.jpg")

    assert captured.value.code == "controlled_file_still_writing"
    assert captured.value.retryable


def test_discovery_reports_file_permission_failure_instead_of_hiding_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "contracts" / "denied.pdf"
    _write_stable(target, b"denied")
    original_stat = Path.stat

    def deny_selected_file(path: Path, *args, **kwargs):
        if path == target:
            raise PermissionError("test deny")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", deny_selected_file)
    storage = FileSystemControlledFileStorage(tmp_path, clock=lambda: 200.0)

    with pytest.raises(ControlledFileStorageError) as captured:
        storage.discover(limit=10)

    assert captured.value.code == "controlled_file_storage_read_denied"
    assert captured.value.retryable
    assert str(target) not in str(captured.value)


def test_symlink_is_never_used_as_a_controlled_object_reference(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_bytes(b"outside")
    link = tmp_path / "linked.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("current platform does not allow test symlinks")
    storage = FileSystemControlledFileStorage(tmp_path, settle_seconds=0)

    assert storage.discover(limit=10).items == ()
    with pytest.raises(ControlledFileStorageError) as captured:
        storage.read_verified("linked.txt")

    assert captured.value.code == "controlled_file_reference_invalid"
    assert str(outside) not in str(captured.value)
