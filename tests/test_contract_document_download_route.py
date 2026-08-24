"""
File: test_contract_document_download_route.py
Description: 驗證遺失或損毀的契約 archive 以 typed not-found 回應，不洩漏 500。
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.routes import contract_signing as route


class _Cursor:
    def execute(self, *_args, **_kwargs):
        return None

    def fetchone(self):
        return {
            "storage_key": "CASE-1/client/missing.pdf",
            "sha256": "a" * 64,
            "mime_type": "application/pdf",
            "original_filename": "服務人員契約.xlsx",
        }

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Connection:
    def cursor(self):
        return _Cursor()

    def close(self):
        return None


def test_missing_contract_archive_returns_typed_not_found_instead_of_internal_error(monkeypatch):
    monkeypatch.setattr(route, "get_connection", _Connection)
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
        )

    assert captured.value.status_code == 404
    assert captured.value.detail["error"]["category"] == "not_found"
    assert captured.value.detail["error"]["code"] == "contract_document_not_found"


def test_download_uses_rfc5987_filename_for_non_ascii_archive_name(monkeypatch):
    monkeypatch.setattr(route, "get_connection", _Connection)
    monkeypatch.setattr(route, "read_archived_contract_document", lambda **_kwargs: b"pdf")
    monkeypatch.setattr(route, "record_admin_audit", lambda **_kwargs: None)

    response = route.download_contract_document(
        request=SimpleNamespace(url=SimpleNamespace(path="/api/v1/orders/CASE-1/contract-signing/documents/7/download")),
        case_no="CASE-1",
        document_version_id=7,
        principal=SimpleNamespace(),
    )

    assert response.headers["content-disposition"] == (
        'attachment; filename="contract_document_7.xlsx"; '
        "filename*=UTF-8''%E6%9C%8D%E5%8B%99%E4%BA%BA%E5%93%A1%E5%A5%91%E7%B4%84.xlsx"
    )
