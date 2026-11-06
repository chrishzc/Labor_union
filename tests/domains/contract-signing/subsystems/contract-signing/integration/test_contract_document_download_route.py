"""
File: test_contract_document_download_route.py
Description: 驗證遺失或損毀的契約 archive 以 typed not-found 回應，不洩漏 500。
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.routes import contract_signing as route
from subsystems.contract_signing.document_query import ContractSigningDocumentDownload


class _DocumentQueryApplication:
    def find_document_for_download(self, case_no, document_version_id):
        return ContractSigningDocumentDownload(
            case_no=case_no,
            document_version_id=document_version_id,
            storage_key="CASE-1/client/missing.pdf",
            sha256="a" * 64,
            mime_type="application/pdf",
            original_filename="服務人員契約.xlsx",
        )


def test_missing_contract_archive_returns_typed_not_found_instead_of_internal_error(monkeypatch):
    monkeypatch.setattr(
        route,
        "read_archived_contract_document",
        lambda **_kwargs: (_ for _ in ()).throw(FileNotFoundError("archive file missing")),
    )

    with pytest.raises(HTTPException) as captured:
        route.download_contract_document(
            request=SimpleNamespace(url=SimpleNamespace(path="/api/v1/orders/CASE-1/contract-signing/documents/7/download")),
            case_no="CASE-1",
            document_version_id=7,
            principal=SimpleNamespace(),
            application=_DocumentQueryApplication(),
        )

    assert captured.value.status_code == 404
    assert captured.value.detail["error"]["category"] == "not_found"
    assert captured.value.detail["error"]["code"] == "contract_document_not_found"


def test_download_uses_rfc5987_filename_for_non_ascii_archive_name(monkeypatch):
    monkeypatch.setattr(route, "read_archived_contract_document", lambda **_kwargs: b"pdf")
    monkeypatch.setattr(route, "record_admin_audit", lambda **_kwargs: None)

    response = route.download_contract_document(
        request=SimpleNamespace(url=SimpleNamespace(path="/api/v1/orders/CASE-1/contract-signing/documents/7/download")),
        case_no="CASE-1",
        document_version_id=7,
        principal=SimpleNamespace(),
        application=_DocumentQueryApplication(),
    )

    assert response.headers["content-disposition"] == (
        'attachment; filename="contract_document_7.xlsx"; '
        "filename*=UTF-8''%E6%9C%8D%E5%8B%99%E4%BA%BA%E5%93%A1%E5%A5%91%E7%B4%84.xlsx"
    )


def test_reconstructed_source_uses_original_download_endpoint_without_archive_locator(monkeypatch):
    import hashlib
    content = b"reconstructed canonical xlsx"
    class SnapshotQuery:
        def find_document_for_download(self, case_no, document_version_id):
            return ContractSigningDocumentDownload(case_no, document_version_id, None,
                hashlib.sha256(content).hexdigest(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "source.xlsx", content)
    def forbidden(**_): pytest.fail("snapshot source must not use an invented archive locator")
    audits = []
    monkeypatch.setattr(route, "read_archived_contract_document", forbidden)
    monkeypatch.setattr(route, "record_admin_audit", lambda **kwargs: audits.append(kwargs))
    response = route.download_contract_document(
        request=SimpleNamespace(url=SimpleNamespace(path="/api/v1/orders/CASE-1/contract-signing/documents/101/download")),
        case_no="CASE-1", document_version_id=101, principal=SimpleNamespace(), application=SnapshotQuery(),
    )
    assert response.body == content and len(audits) == 1
    assert audits[0]["details"]["sha256"] == hashlib.sha256(content).hexdigest()


def test_reconstructed_source_owner_failure_is_typed_without_raw_internal_error():
    from subsystems.contract_signing.unsigned_contract_pdf import UnsignedContractPdfError
    class SnapshotQuery:
        def find_document_for_download(self, *_):
            raise UnsignedContractPdfError(category="conflict", code="contract_render_snapshot_invalid", message="invalid snapshot")
    with pytest.raises(HTTPException) as captured:
        route.download_contract_document(
            request=SimpleNamespace(url=SimpleNamespace(path="/download")), case_no="CASE-1", document_version_id=101,
            principal=SimpleNamespace(), application=SnapshotQuery(),
        )
    assert captured.value.status_code == 409
    assert captured.value.detail["error"]["code"] == "contract_render_snapshot_invalid"


@pytest.mark.parametrize("category,retryable,status", [("conflict", False, 409), ("unavailable", True, 503)])
def test_original_sender_maps_snapshot_owner_failure_to_the_closed_response(category, retryable, status):
    from subsystems.contract_signing.unsigned_contract_pdf import UnsignedContractPdfError
    def operation():
        raise UnsignedContractPdfError(category=category, code="contract_render_snapshot_template_unavailable",
            message="核准模板目前無法讀取。", retryable=retryable)
    with pytest.raises(HTTPException) as captured:
        route._response(operation, "send", "snapshot:sender:error")
    assert captured.value.status_code == status
    assert captured.value.detail["error"]["code"] == "contract_render_snapshot_template_unavailable"
    assert captured.value.detail["error"]["retryable"] is retryable
