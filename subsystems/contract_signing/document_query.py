"""Typed, bounded Contract Signing document queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from shared_kernel.validation import (
    require_canonical_text,
    require_positive_integer,
    require_sha256_hex,
)


@dataclass(frozen=True, slots=True)
class ContractSigningDocumentDownload:
    """The smallest owner-scoped projection required to download a document."""

    case_no: str
    document_version_id: int
    storage_key: str
    sha256: str
    mime_type: str
    original_filename: str

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        require_positive_integer(self.document_version_id, "document version ID")
        require_canonical_text(self.storage_key, "contract document storage key", 500)
        require_sha256_hex(self.sha256, "contract document SHA-256")
        require_canonical_text(self.mime_type, "contract document MIME type", 100)
        require_canonical_text(self.original_filename, "contract document filename", 255)


@dataclass(frozen=True, slots=True)
class ContractSigningStaffSegment:
    segment_id: int
    staff_id: int
    sent: bool
    signed_received: bool


@dataclass(frozen=True, slots=True)
class ContractSigningDocument:
    document_version_id: int
    scope: Literal["staff_segment", "client_contract"]
    role: Literal["template_generated", "signed_return"]
    target_key: str
    version_number: int
    template_key: str | None
    template_sha256: str | None
    mapping_sha256: str | None
    archive_sha256: str
    mime_type: str
    file_size: int


@dataclass(frozen=True, slots=True)
class ContractSigningStatus:
    case_no: str
    staff_segments: tuple[ContractSigningStaffSegment, ...]
    commitment_id: int | None
    client_document_sent: bool
    client_signed_received: bool
    contract_identity: str | None
    documents: tuple[ContractSigningDocument, ...]


class ContractSigningDocumentQueryRepository(Protocol):
    def find_status(self, case_no: str) -> ContractSigningStatus | None: ...

    def find_document_for_download(
        self, case_no: str, document_version_id: int
    ) -> ContractSigningDocumentDownload | None: ...


class ContractSigningDocumentQueryApplication:
    """Read-only Contract Signing application over a typed repository port."""

    def __init__(self, repository: ContractSigningDocumentQueryRepository) -> None:
        self._repository = repository

    def query_status(self, case_no: str) -> ContractSigningStatus | None:
        require_canonical_text(case_no, "case number", 50)
        return self._repository.find_status(case_no)

    def find_document_for_download(
        self, case_no: str, document_version_id: int
    ) -> ContractSigningDocumentDownload | None:
        require_canonical_text(case_no, "case number", 50)
        require_positive_integer(document_version_id, "document version ID")
        return self._repository.find_document_for_download(case_no, document_version_id)


__all__ = [
    "ContractSigningDocumentDownload",
    "ContractSigningDocument",
    "ContractSigningDocumentQueryApplication",
    "ContractSigningDocumentQueryRepository",
    "ContractSigningStaffSegment",
    "ContractSigningStatus",
]
