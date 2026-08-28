"""
File: test_unsigned_contract_pdf.py
Description: 驗證未簽 PDF prepare／authenticated download 的 current、integrity、audit 與去敏契約。
"""

from __future__ import annotations

import hashlib

import pytest

from shared_kernel.identities import ActorContext, CorrelationId
from subsystems.contract_signing.contract_renderer import (
    ContractRendererError,
    RenderedContract,
)
from subsystems.contract_signing.template_catalog import load_approved_template
from subsystems.contract_signing.unsigned_contract_pdf import (
    DownloadUnsignedContractPdf,
    PrepareUnsignedContractPdf,
    StoredUnsignedContractPdf,
    UnsignedContractPdfApplication,
    UnsignedContractPdfError,
    UnsignedContractRenderSource,
)


PDF = b"%PDF-1.7\nunsigned contract\n%%EOF\n"


class _Repository:
    def __init__(self, *, source=None, stored=None, audit_error=None):
        self.source = source
        self.stored = stored
        self.audit_error = audit_error
        self.render_queries = []
        self.download_queries = []
        self.audits = []

    def load_render_source(self, case_no, document_version_id):
        self.render_queries.append((case_no, document_version_id))
        return self.source

    def load_current_pdf(self, case_no, document_version_id):
        self.download_queries.append((case_no, document_version_id))
        return self.stored

    def append_durable_download_audit(self, audit):
        if self.audit_error is not None:
            raise self.audit_error
        self.audits.append(audit)


class _Storage:
    def __init__(self, content=PDF, error=None):
        self.content = content
        self.error = error
        self.calls = []

    def read_verified(self, object_reference, *, expected_sha256):
        self.calls.append((object_reference, expected_sha256))
        if self.error is not None:
            raise self.error
        return self.content


class _Renderer:
    def __init__(self, *, error=None):
        self.error = error
        self.calls = []

    def render(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return RenderedContract.from_pdf_bytes(
            content=PDF,
            filename="approved-template.pdf",
            renderer_identity="test-renderer",
        )


def _actor(identity="admin:7"):
    return ActorContext(identity)


def _source(**changes):
    template = load_approved_template("contract_staff_service")
    values = {
        "case_no": "CASE-1",
        "document_version_id": 11,
        "document_role": "template_generated",
        "is_current": True,
        "template_key": template.template_key,
        "template_sha256": template.template_sha256,
        "mapping_sha256": template.mapping_sha256,
        "facts": {"case_no": "CASE-1", "staff_name": "安全文字"},
    }
    values.update(changes)
    return UnsignedContractRenderSource(**values)


def _stored(**changes):
    values = {
        "case_no": "CASE-1",
        "document_version_id": 12,
        "document_role": "template_generated",
        "is_current": True,
        "object_reference": "contractobj_0123456789abcdef0123456789abcdef",
        "filename": "CASE-1-unsigned.pdf",
        "mime_type": "application/pdf",
        "size_bytes": len(PDF),
        "sha256": hashlib.sha256(PDF).hexdigest(),
    }
    values.update(changes)
    return StoredUnsignedContractPdf(**values)


def _application(*, source=None, stored=None, storage=None, renderer=None, audit_error=None):
    repository = _Repository(source=source, stored=stored, audit_error=audit_error)
    storage = storage or _Storage()
    renderer = renderer or _Renderer()
    return UnsignedContractPdfApplication(repository, storage, renderer), repository, storage, renderer


def test_prepare_uses_only_current_approved_template_contract():
    application, repository, _storage, renderer = _application(source=_source())

    result = application.prepare(
        PrepareUnsignedContractPdf("CASE-1", 11, _actor())
    )

    assert repository.render_queries == [("CASE-1", 11)]
    assert renderer.calls[0]["facts"] == {"case_no": "CASE-1", "staff_name": "安全文字"}
    assert renderer.calls[0]["template_path"].name == "服務人員契約.xlsx"
    assert renderer.calls[0]["mapping_path"].name == "contract_staff_service.json"
    assert result.case_no == "CASE-1"
    assert result.source_document_version_id == 11
    assert result.content == PDF
    assert result.mime_type == "application/pdf"
    assert not hasattr(result, "sha256")
    assert not hasattr(result, "object_reference")


@pytest.mark.parametrize(
    ("source", "code"),
    [
        (None, "contract_pdf_source_not_found"),
        (_source(is_current=False), "contract_pdf_document_stale"),
        (_source(document_role="signed_return"), "contract_pdf_not_unsigned"),
        (_source(case_no="CASE-OTHER"), "contract_pdf_source_identity_mismatch"),
        (_source(template_sha256="a" * 64), "contract_pdf_template_stale"),
        (_source(mapping_sha256="b" * 64), "contract_pdf_template_stale"),
    ],
)
def test_prepare_rejects_missing_stale_or_nonapproved_source(source, code):
    application, _repository, _storage, renderer = _application(source=source)

    with pytest.raises(UnsignedContractPdfError) as captured:
        application.prepare(PrepareUnsignedContractPdf("CASE-1", 11, _actor()))

    assert captured.value.code == code
    assert renderer.calls == []


def test_prepare_maps_renderer_failure_to_closed_error():
    renderer = _Renderer(
        error=ContractRendererError(
            "contract_pdf_renderer_conversion_failed",
            "secret source /private/path",
        )
    )
    application, _repository, _storage, _renderer = _application(
        source=_source(), renderer=renderer
    )

    with pytest.raises(UnsignedContractPdfError) as captured:
        application.prepare(PrepareUnsignedContractPdf("CASE-1", 11, _actor()))

    assert captured.value.code == "contract_pdf_renderer_conversion_failed"
    assert "/private/path" not in str(captured.value)


def test_prepare_rejects_nonpersisted_actor_before_repository_access():
    application, repository, _storage, renderer = _application(source=_source())

    with pytest.raises(UnsignedContractPdfError) as captured:
        application.prepare(
            PrepareUnsignedContractPdf(
                "CASE-1",
                11,
                _actor("system:local_bypass"),
            )
        )

    assert captured.value.code == "contract_pdf_requires_persisted_actor"
    assert repository.render_queries == []
    assert renderer.calls == []


def test_download_returns_pdf_only_after_integrity_and_durable_audit():
    application, repository, storage, _renderer = _application(stored=_stored())

    result = application.download(
        DownloadUnsignedContractPdf(
            "CASE-1", 12, _actor(), CorrelationId("contract-download-1")
        )
    )

    assert storage.calls == [
        (
            "contractobj_0123456789abcdef0123456789abcdef",
            hashlib.sha256(PDF).hexdigest(),
        )
    ]
    assert len(repository.audits) == 1
    assert repository.audits[0].case_no == "CASE-1"
    assert repository.audits[0].document_version_id == 12
    assert result.content == PDF
    assert result.mime_type == "application/pdf"
    assert result.filename == "CASE-1-unsigned.pdf"
    assert result.cache_control == "no-store"
    assert not hasattr(result, "sha256")
    assert not hasattr(result, "object_reference")


def test_download_rejects_nonpersisted_actor_before_repository_access():
    application, repository, storage, _renderer = _application(stored=_stored())

    with pytest.raises(UnsignedContractPdfError) as captured:
        application.download(
            DownloadUnsignedContractPdf(
                "CASE-1",
                12,
                _actor("system:local_bypass"),
                CorrelationId("contract-download-local-bypass"),
            )
        )

    assert captured.value.code == "contract_pdf_requires_persisted_actor"
    assert repository.download_queries == []
    assert storage.calls == []


@pytest.mark.parametrize(
    ("stored", "code"),
    [
        (None, "contract_pdf_document_not_found"),
        (_stored(is_current=False), "contract_pdf_document_stale"),
        (_stored(document_role="signed_return"), "contract_pdf_not_unsigned"),
        (_stored(case_no="CASE-OTHER"), "contract_pdf_document_identity_mismatch"),
        (
            _stored(
                mime_type=(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            ),
            "contract_pdf_media_type_invalid",
        ),
    ],
)
def test_download_rejects_missing_stale_signed_xlsx_or_cross_case(stored, code):
    application, repository, storage, _renderer = _application(stored=stored)

    with pytest.raises(UnsignedContractPdfError) as captured:
        application.download(
            DownloadUnsignedContractPdf(
                "CASE-1", 12, _actor(), CorrelationId("contract-download-reject")
            )
        )

    assert captured.value.code == code
    assert repository.audits == []
    assert storage.calls == []


@pytest.mark.parametrize(
    ("stored", "content"),
    [
        (_stored(sha256="a" * 64), PDF),
        (_stored(size_bytes=len(PDF) + 1), PDF),
        (_stored(), b"%PDF-1.7\nchanged\n%%EOF\n"),
        (_stored(), b"not-a-pdf"),
    ],
)
def test_download_rejects_digest_size_or_pdf_content_drift(stored, content):
    application, repository, _storage, _renderer = _application(
        stored=stored, storage=_Storage(content=content)
    )

    with pytest.raises(UnsignedContractPdfError) as captured:
        application.download(
            DownloadUnsignedContractPdf(
                "CASE-1", 12, _actor(), CorrelationId("contract-download-drift")
            )
        )

    assert captured.value.code == "contract_pdf_integrity_mismatch"
    assert repository.audits == []


def test_download_maps_storage_and_audit_failures_without_leaking_details():
    application, repository, _storage, _renderer = _application(
        stored=_stored(), storage=_Storage(error=OSError("/private/nas/path"))
    )
    with pytest.raises(UnsignedContractPdfError) as captured:
        application.download(
            DownloadUnsignedContractPdf(
                "CASE-1", 12, _actor(), CorrelationId("contract-download-storage")
            )
        )
    assert captured.value.code == "contract_pdf_storage_unavailable"
    assert "/private/nas/path" not in str(captured.value)
    assert repository.audits == []

    application, repository, _storage, _renderer = _application(
        stored=_stored(), audit_error=RuntimeError("audit SQL /private/db")
    )
    with pytest.raises(UnsignedContractPdfError) as captured:
        application.download(
            DownloadUnsignedContractPdf(
                "CASE-1", 12, _actor(), CorrelationId("contract-download-audit")
            )
        )
    assert captured.value.code == "contract_pdf_download_audit_failed"
    assert "/private/db" not in str(captured.value)
    assert repository.audits == []


def test_internal_stored_reference_rejects_path_like_locator():
    with pytest.raises(ValueError, match="object reference"):
        _stored(object_reference="cases/CASE-1/unsigned.pdf")
