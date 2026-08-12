from __future__ import annotations

import hashlib

import pytest

from infrastructure.archive.contract_documents import (
    archive_contract_document,
    read_archived_contract_document,
    validate_contract_document_content,
)


def test_contract_document_archive_is_atomic_immutable_and_digest_checked(tmp_path):
    content = b"signed contract"
    archived = archive_contract_document(
        content,
        storage_root=tmp_path,
        storage_key="contracts/CASE-1/staff/one.pdf",
    )

    assert archived.sha256 == hashlib.sha256(content).hexdigest()
    assert read_archived_contract_document(
        storage_root=tmp_path,
        storage_key=archived.storage_key,
        expected_sha256=archived.sha256,
    ) == content
    assert archive_contract_document(
        content,
        storage_root=tmp_path,
        storage_key=archived.storage_key,
    ) == archived
    with pytest.raises(FileExistsError, match="content conflict"):
        archive_contract_document(
            b"different content",
            storage_root=tmp_path,
            storage_key=archived.storage_key,
        )


def test_contract_document_archive_rejects_path_escape_and_digest_mismatch(tmp_path):
    with pytest.raises(ValueError, match="escapes"):
        archive_contract_document(
            b"content", storage_root=tmp_path, storage_key="../outside.pdf"
        )

    archived = archive_contract_document(
        b"content", storage_root=tmp_path, storage_key="contracts/CASE-1/client.pdf"
    )
    with pytest.raises(ValueError, match="integrity"):
        read_archived_contract_document(
            storage_root=tmp_path,
            storage_key=archived.storage_key,
            expected_sha256="0" * 64,
        )


@pytest.mark.parametrize(
    ("content", "mime_type", "error_code"),
    [
        (b"", "application/pdf", "contract_document_empty"),
        (b"content", "text/plain", "contract_document_type_not_allowed"),
    ],
)
def test_contract_document_policy_rejects_invalid_uploads(content, mime_type, error_code):
    with pytest.raises(ValueError, match=error_code):
        validate_contract_document_content(content, mime_type)


def test_contract_document_policy_allows_approved_pdf_and_xlsx():
    validate_contract_document_content(b"pdf", "application/pdf")
    validate_contract_document_content(
        b"xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
