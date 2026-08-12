"""Atomically archive immutable contract document bytes outside the database."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path


MAXIMUM_CONTRACT_DOCUMENT_SIZE = 20 * 1024 * 1024
ALLOWED_CONTRACT_DOCUMENT_MIME_TYPES = frozenset({
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
})


@dataclass(frozen=True, slots=True)
class ArchivedContractDocument:
    storage_key: str
    file_size: int
    sha256: str


def archive_contract_document(
    content: bytes,
    *,
    storage_root: Path,
    storage_key: str,
) -> ArchivedContractDocument:
    if not content:
        raise ValueError("contract document content must not be empty")
    target = _safe_target(storage_root, storage_key)
    digest = _sha256(content)
    if target.exists():
        existing_content = target.read_bytes()
        if _sha256(existing_content) != digest:
            raise FileExistsError("contract document archive target content conflict")
        return ArchivedContractDocument(storage_key, len(existing_content), digest)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, target)
        digest = _sha256(target.read_bytes())
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return ArchivedContractDocument(storage_key, len(content), digest)


def read_archived_contract_document(
    *, storage_root: Path, storage_key: str, expected_sha256: str
) -> bytes:
    target = _safe_target(storage_root, storage_key)
    content = target.read_bytes()
    if _sha256(content) != expected_sha256:
        raise ValueError("contract document archive integrity check failed")
    return content


def discard_uncommitted_contract_document(
    *, storage_root: Path, storage_key: str
) -> None:
    """Remove an archive only after its owning database transaction rolled back."""
    _safe_target(storage_root, storage_key).unlink(missing_ok=True)


def validate_contract_document_content(content: bytes, mime_type: str) -> None:
    if not content:
        raise ValueError("contract_document_empty")
    if len(content) > MAXIMUM_CONTRACT_DOCUMENT_SIZE:
        raise ValueError("contract_document_too_large")
    if mime_type not in ALLOWED_CONTRACT_DOCUMENT_MIME_TYPES:
        raise ValueError("contract_document_type_not_allowed")


def _safe_target(storage_root: Path, storage_key: str) -> Path:
    if not storage_key or Path(storage_key).is_absolute():
        raise ValueError("contract document storage key is invalid")
    root = storage_root.resolve()
    target = (root / storage_key).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise ValueError("contract document storage key escapes archive root") from error
    return target


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
