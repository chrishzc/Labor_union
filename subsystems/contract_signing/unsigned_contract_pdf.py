"""
File: unsigned_contract_pdf.py
Description: 編排核准未簽 PDF prepare 與 current authenticated download、完整性驗證及 durable audit。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from pathlib import Path
import re
from typing import Mapping, Protocol

from shared_kernel.identities import ActorContext, CorrelationId
from shared_kernel.validation import (
    require_canonical_text,
    require_positive_integer,
    require_sha256_hex,
)
from subsystems.contract_signing.contract_renderer import (
    ContractRenderer,
    ContractRendererError,
    PDF_MEDIA_TYPE,
    RenderedContract,
)
from subsystems.contract_signing.template_catalog import (
    TEMPLATE_DIRECTORY,
    approved_template_mapping_path,
    load_approved_template,
)


_AUTHORIZED_LOCAL_OR_PERSISTED_ACTOR = re.compile(
    r"^(?:admin:[1-9][0-9]*|system:local_bypass)$"
)
_OPAQUE_OBJECT_REFERENCE = re.compile(r"^[a-z][a-z0-9_-]{15,63}$")
_UNSIGNED_DOCUMENT_ROLE = "template_generated"
_MAXIMUM_PDF_BYTES = 20 * 1024 * 1024


class UnsignedContractPdfError(RuntimeError):
    def __init__(
        self,
        *,
        category: str,
        code: str,
        message: str,
        retryable: bool = False,
    ) -> None:
        self.category = category
        self.code = code
        self.retryable = retryable
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class PrepareUnsignedContractPdf:
    case_no: str
    document_version_id: int
    actor: ActorContext

    def __post_init__(self) -> None:
        _validate_request_identity(self.case_no, self.document_version_id, self.actor)


@dataclass(frozen=True, slots=True)
class DownloadUnsignedContractPdf:
    case_no: str
    document_version_id: int
    actor: ActorContext
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        _validate_request_identity(self.case_no, self.document_version_id, self.actor)
        if not isinstance(self.correlation_id, CorrelationId):
            raise TypeError("unsigned contract PDF correlation ID is invalid")


@dataclass(frozen=True, slots=True)
class UnsignedContractRenderSource:
    case_no: str
    document_version_id: int
    document_role: str
    is_current: bool
    template_key: str
    template_sha256: str
    mapping_sha256: str
    facts: Mapping[str, object]

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        require_positive_integer(self.document_version_id, "document version ID")
        require_canonical_text(self.document_role, "document role", 50)
        if not isinstance(self.is_current, bool):
            raise TypeError("current document flag must be boolean")
        require_canonical_text(self.template_key, "template key", 100)
        require_sha256_hex(self.template_sha256, "template SHA-256")
        require_sha256_hex(self.mapping_sha256, "mapping SHA-256")
        if not isinstance(self.facts, Mapping):
            raise TypeError("contract render facts must be a mapping")


@dataclass(frozen=True, slots=True)
class StoredUnsignedContractPdf:
    case_no: str
    document_version_id: int
    document_role: str
    is_current: bool
    object_reference: str
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        require_positive_integer(self.document_version_id, "document version ID")
        require_canonical_text(self.document_role, "document role", 50)
        if not isinstance(self.is_current, bool):
            raise TypeError("current document flag must be boolean")
        require_canonical_text(self.object_reference, "object reference", 64)
        if _OPAQUE_OBJECT_REFERENCE.fullmatch(self.object_reference) is None:
            raise ValueError("object reference must be opaque")
        _validate_pdf_filename(self.filename)
        require_canonical_text(self.mime_type, "document MIME type", 100)
        require_positive_integer(self.size_bytes, "document size")
        if self.size_bytes > _MAXIMUM_PDF_BYTES:
            raise ValueError("document size exceeds maximum")
        require_sha256_hex(self.sha256, "document SHA-256")


@dataclass(frozen=True, slots=True)
class PreparedUnsignedContractPdf:
    case_no: str
    source_document_version_id: int
    content: bytes
    mime_type: str
    filename: str
    renderer_identity: str


@dataclass(frozen=True, slots=True)
class UnsignedContractPdfDownload:
    case_no: str
    document_version_id: int
    content: bytes
    mime_type: str
    filename: str
    cache_control: str = "no-store"


@dataclass(frozen=True, slots=True)
class UnsignedContractPdfDownloadAudit:
    case_no: str
    document_version_id: int
    actor_id: str
    correlation_id: str
    filename: str
    mime_type: str
    size_bytes: int


class UnsignedContractPdfRepository(Protocol):
    def load_render_source(
        self, case_no: str, document_version_id: int
    ) -> UnsignedContractRenderSource | None: ...

    def load_current_pdf(
        self, case_no: str, document_version_id: int
    ) -> StoredUnsignedContractPdf | None: ...

    def append_durable_download_audit(
        self, audit: UnsignedContractPdfDownloadAudit
    ) -> None: ...


class UnsignedContractPdfStoragePort(Protocol):
    def read_verified(
        self, object_reference: str, *, expected_sha256: str
    ) -> bytes: ...


class UnsignedContractPdfApplication:
    def __init__(
        self,
        repository: UnsignedContractPdfRepository,
        storage: UnsignedContractPdfStoragePort,
        renderer: ContractRenderer,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._renderer = renderer

    def prepare(
        self, command: PrepareUnsignedContractPdf
    ) -> PreparedUnsignedContractPdf:
        _require_persisted_actor(command.actor)
        source = self._repository.load_render_source(
            command.case_no,
            command.document_version_id,
        )
        if source is None:
            raise _error(
                "not_found",
                "contract_pdf_source_not_found",
                "找不到未簽契約來源。",
            )
        _require_source_identity(command, source)
        template = _load_current_approved_template(source)
        try:
            rendered = self._renderer.render(
                template_path=TEMPLATE_DIRECTORY / template.template_filename,
                mapping_path=approved_template_mapping_path(template.template_key),
                facts=dict(source.facts),
            )
        except ContractRendererError as error:
            raise _error(
                "unavailable" if error.retryable else "domain_blocked",
                error.code,
                "未簽契約 PDF 目前無法產生。",
                retryable=error.retryable,
            ) from None
        except Exception:
            raise _error(
                "unavailable",
                "contract_pdf_renderer_unavailable",
                "未簽契約 PDF 目前無法產生。",
                retryable=True,
            ) from None
        if not isinstance(rendered, RenderedContract):
            raise _error(
                "internal",
                "contract_pdf_renderer_result_invalid",
                "未簽契約 PDF renderer 回應無效。",
            )
        return PreparedUnsignedContractPdf(
            case_no=source.case_no,
            source_document_version_id=source.document_version_id,
            content=rendered.content,
            mime_type=rendered.mime_type,
            filename=rendered.filename,
            renderer_identity=rendered.renderer_identity,
        )

    def download(
        self, query: DownloadUnsignedContractPdf
    ) -> UnsignedContractPdfDownload:
        _require_persisted_actor(query.actor)
        stored = self._repository.load_current_pdf(
            query.case_no,
            query.document_version_id,
        )
        if stored is None:
            raise _error(
                "not_found",
                "contract_pdf_document_not_found",
                "找不到未簽契約 PDF。",
            )
        _require_download_identity(query, stored)
        try:
            content = self._storage.read_verified(
                stored.object_reference,
                expected_sha256=stored.sha256,
            )
        except Exception:
            raise _error(
                "unavailable",
                "contract_pdf_storage_unavailable",
                "未簽契約 PDF 儲存目前無法讀取。",
                retryable=True,
            ) from None
        _require_pdf_integrity(stored, content)
        audit = UnsignedContractPdfDownloadAudit(
            case_no=stored.case_no,
            document_version_id=stored.document_version_id,
            actor_id=query.actor.actor_id,
            correlation_id=query.correlation_id.value,
            filename=stored.filename,
            mime_type=stored.mime_type,
            size_bytes=stored.size_bytes,
        )
        try:
            self._repository.append_durable_download_audit(audit)
        except Exception:
            raise _error(
                "unavailable",
                "contract_pdf_download_audit_failed",
                "未簽契約 PDF 下載稽核無法保存。",
                retryable=True,
            ) from None
        return UnsignedContractPdfDownload(
            case_no=stored.case_no,
            document_version_id=stored.document_version_id,
            content=content,
            mime_type=stored.mime_type,
            filename=stored.filename,
        )


def _validate_request_identity(
    case_no: str,
    document_version_id: int,
    actor: ActorContext,
) -> None:
    require_canonical_text(case_no, "case number", 50)
    require_positive_integer(document_version_id, "document version ID")
    if not isinstance(actor, ActorContext):
        raise TypeError("unsigned contract PDF actor is invalid")


def _require_persisted_actor(actor: ActorContext) -> None:
    if _AUTHORIZED_LOCAL_OR_PERSISTED_ACTOR.fullmatch(actor.actor_id) is None:
        raise _error(
            "forbidden",
            "contract_pdf_requires_persisted_actor",
            "未簽契約 PDF 操作需要已登入且啟用的內部使用者。",
        )


def _require_source_identity(
    command: PrepareUnsignedContractPdf,
    source: UnsignedContractRenderSource,
) -> None:
    if (
        source.case_no != command.case_no
        or source.document_version_id != command.document_version_id
    ):
        raise _error(
            "conflict",
            "contract_pdf_source_identity_mismatch",
            "未簽契約來源身分不一致。",
        )
    if not source.is_current:
        raise _error(
            "conflict",
            "contract_pdf_document_stale",
            "未簽契約文件版本已過期。",
        )
    if source.document_role != _UNSIGNED_DOCUMENT_ROLE:
        raise _error(
            "domain_blocked",
            "contract_pdf_not_unsigned",
            "指定文件不是未簽契約來源。",
        )


def _load_current_approved_template(source: UnsignedContractRenderSource):
    try:
        template = load_approved_template(source.template_key)
    except Exception:
        raise _error(
            "domain_blocked",
            "contract_pdf_template_unavailable",
            "核准契約模板目前無法使用。",
        ) from None
    if not (
        hmac.compare_digest(template.template_sha256, source.template_sha256)
        and hmac.compare_digest(template.mapping_sha256, source.mapping_sha256)
    ):
        raise _error(
            "conflict",
            "contract_pdf_template_stale",
            "核准契約模板版本已變更。",
        )
    return template


def _require_download_identity(
    query: DownloadUnsignedContractPdf,
    stored: StoredUnsignedContractPdf,
) -> None:
    if (
        stored.case_no != query.case_no
        or stored.document_version_id != query.document_version_id
    ):
        raise _error(
            "conflict",
            "contract_pdf_document_identity_mismatch",
            "未簽契約 PDF 身分不一致。",
        )
    if not stored.is_current:
        raise _error(
            "conflict",
            "contract_pdf_document_stale",
            "未簽契約 PDF 版本已過期。",
        )
    if stored.document_role != _UNSIGNED_DOCUMENT_ROLE:
        raise _error(
            "domain_blocked",
            "contract_pdf_not_unsigned",
            "指定文件不是未簽契約 PDF。",
        )
    if stored.mime_type != PDF_MEDIA_TYPE:
        raise _error(
            "domain_blocked",
            "contract_pdf_media_type_invalid",
            "未簽契約文件類型不是 PDF。",
        )


def _require_pdf_integrity(stored: StoredUnsignedContractPdf, content: object) -> None:
    valid_content = isinstance(content, bytes) and bool(content)
    if valid_content:
        digest = hashlib.sha256(content).hexdigest()
        valid_content = (
            len(content) == stored.size_bytes
            and hmac.compare_digest(digest, stored.sha256)
            and content.startswith(b"%PDF-")
            and content.rstrip().endswith(b"%%EOF")
        )
    if not valid_content:
        raise _error(
            "domain_blocked",
            "contract_pdf_integrity_mismatch",
            "未簽契約 PDF 完整性驗證失敗。",
        )


def _validate_pdf_filename(filename: str) -> None:
    require_canonical_text(filename, "PDF filename", 255)
    if (
        Path(filename).name != filename
        or not filename.lower().endswith(".pdf")
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in filename
        )
    ):
        raise ValueError("PDF filename is invalid")


def _error(
    category: str,
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> UnsignedContractPdfError:
    return UnsignedContractPdfError(
        category=category,
        code=code,
        message=message,
        retryable=retryable,
    )


__all__ = [
    "DownloadUnsignedContractPdf",
    "PrepareUnsignedContractPdf",
    "PreparedUnsignedContractPdf",
    "StoredUnsignedContractPdf",
    "UnsignedContractPdfApplication",
    "UnsignedContractPdfDownload",
    "UnsignedContractPdfDownloadAudit",
    "UnsignedContractPdfError",
    "UnsignedContractPdfRepository",
    "UnsignedContractPdfStoragePort",
    "UnsignedContractRenderSource",
]
