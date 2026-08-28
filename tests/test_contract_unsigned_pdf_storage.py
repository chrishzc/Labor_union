"""
File: test_contract_unsigned_pdf_storage.py
Description: 驗證未簽契約 PDF storage adapter 只以 opaque identity 解析並完整性讀取。
"""

from __future__ import annotations

import hashlib

import pytest

from infrastructure.file.contract_unsigned_pdf_storage import (
    ContractUnsignedPdfStorage,
    ContractUnsignedPdfStorageError,
)
from subsystems.controlled_files.contracts import ControlledFileContent


_PDF = b"%PDF-1.7\nunsigned\n%%EOF\n"
_DIGEST = hashlib.sha256(_PDF).hexdigest()
_OPAQUE_ID = "cf_0123456789abcdef0123456789abcdef"


class _Storage:
    def __init__(self, content=_PDF, content_type="application/pdf", digest=_DIGEST):
        self.content = content
        self.content_type = content_type
        self.digest = digest
        self.calls = []

    def download(self, object_reference):
        self.calls.append(object_reference)
        return ControlledFileContent(
            object_reference=object_reference,
            filename="unsigned.pdf",
            content_type=self.content_type,
            content=self.content,
            content_sha256=self.digest,
        )


def test_delegates_opaque_identity_to_registered_controlled_file_download():
    controlled_storage = _Storage()
    adapter = ContractUnsignedPdfStorage(controlled_storage)

    content = adapter.read_verified(_OPAQUE_ID, expected_sha256=_DIGEST)

    assert content == _PDF
    assert controlled_storage.calls == [_OPAQUE_ID]


@pytest.mark.parametrize(
    ("storage", "expected_code"),
    [
        (_Storage(content_type="application/octet-stream"), "contract_pdf_storage_media_invalid"),
        (_Storage(content=b"not-pdf"), "contract_pdf_storage_integrity_invalid"),
        (_Storage(digest="b" * 64), "contract_pdf_storage_integrity_invalid"),
    ],
)
def test_invalid_storage_result_fails_closed_without_locator(storage, expected_code):
    adapter = ContractUnsignedPdfStorage(storage)

    with pytest.raises(ContractUnsignedPdfStorageError) as captured:
        adapter.read_verified(_OPAQUE_ID, expected_sha256=_DIGEST)

    assert captured.value.code == expected_code
    assert _OPAQUE_ID not in str(captured.value)


def test_controlled_download_failure_does_not_echo_opaque_identity():
    class _Missing:
        def download(self, _):
            raise RuntimeError("/private/nas/unsigned.pdf")

    adapter = ContractUnsignedPdfStorage(_Missing())

    with pytest.raises(ContractUnsignedPdfStorageError) as captured:
        adapter.read_verified(_OPAQUE_ID, expected_sha256=_DIGEST)

    assert captured.value.code == "contract_pdf_storage_read_failed"
    assert _OPAQUE_ID not in str(captured.value)
