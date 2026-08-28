"""
File: contract_unsigned_pdf_storage.py
Description: 以未簽契約 opaque file identity 委派 controlled-file registered staging 完整性讀取。
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Protocol

from subsystems.controlled_files.contracts import ControlledFileContent


_PDF_MEDIA_TYPE = "application/pdf"
_MAXIMUM_PDF_BYTES = 20 * 1024 * 1024


class ContractUnsignedPdfStorageError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(message)


class ContractUnsignedPdfDownloadPort(Protocol):
    def download(self, file_id: str) -> ControlledFileContent: ...


class ContractUnsignedPdfStorage:
    def __init__(
        self,
        controlled_files: ContractUnsignedPdfDownloadPort,
    ) -> None:
        self._controlled_files = controlled_files

    def read_verified(
        self, object_reference: str, *, expected_sha256: str
    ) -> bytes:
        try:
            result = self._controlled_files.download(object_reference)
        except Exception:
            raise _error("contract_pdf_storage_read_failed", retryable=True) from None
        if (
            result.object_reference != object_reference
            or result.content_type != _PDF_MEDIA_TYPE
        ):
            raise _error("contract_pdf_storage_media_invalid", retryable=False)
        content = result.content
        valid = isinstance(content, bytes) and 0 < len(content) <= _MAXIMUM_PDF_BYTES
        if valid:
            digest = hashlib.sha256(content).hexdigest()
            valid = (
                hmac.compare_digest(digest, expected_sha256)
                and hmac.compare_digest(result.content_sha256, expected_sha256)
                and content.startswith(b"%PDF-")
                and content.rstrip().endswith(b"%%EOF")
            )
        if not valid:
            raise _error("contract_pdf_storage_integrity_invalid", retryable=False)
        return content


def _error(code: str, *, retryable: bool) -> ContractUnsignedPdfStorageError:
    return ContractUnsignedPdfStorageError(
        code,
        "未簽契約 PDF 儲存目前無法安全讀取。",
        retryable=retryable,
    )


__all__ = [
    "ContractUnsignedPdfDownloadPort",
    "ContractUnsignedPdfStorage",
    "ContractUnsignedPdfStorageError",
]
