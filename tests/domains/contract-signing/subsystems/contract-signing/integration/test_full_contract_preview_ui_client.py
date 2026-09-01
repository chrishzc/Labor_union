"""Focused typed client contract for the Form Management full-contract UI flow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ui.api_clients.full_contract_preview_api_client import (
    FullContractPreviewApiClient,
    FullContractPreviewApiError,
)
from ui.pages.form_management.shared import render_excel_contract_mirror


class _Response:
    def __init__(self, *, payload=None, content=b"", status_code=200, headers=None):
        self._payload = payload
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}
        self.ok = status_code < 400

    def json(self):
        return self._payload


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def _preview(scope="client", assignment_id=None):
    return {
        "success": True,
        "message": "ok",
        "error": None,
        "data": {
            "case_no": "CASE-1",
            "scope": scope,
            "assignment_id": assignment_id,
            "template_key": "contract_client_copy",
            "template_version": "a" * 64,
            "owner_fingerprints": {},
            "field_values": {"F1": "CASE-1"},
            "blockers": [],
            "preview_fingerprint": "b" * 64,
            "ready_to_print": True,
        },
    }


def test_full_preview_client_and_staff_targets_use_typed_exact_routes():
    session = _Session(
        [
            _Response(payload=_preview()),
            _Response(payload=_preview("staff", 7)),
        ]
    )
    client = FullContractPreviewApiClient(
        base_url="http://api.test/",
        headers={"Authorization": "Bearer test"},
        session=session,
    )

    assert client.preview_client(" CASE-1 ").case_no == "CASE-1"
    assert client.preview_staff("CASE-1", 7).assignment_id == 7
    assert session.calls[0][0] == "http://api.test/api/v1/orders/CASE-1/contract-signing/client/preview"
    assert session.calls[1][0] == "http://api.test/api/v1/orders/CASE-1/contract-signing/staff-segments/7/preview"


def test_full_preview_rejects_mismatched_case_without_using_stale_result():
    payload = _preview()
    payload["data"]["case_no"] = "CASE-OTHER"
    session = _Session([_Response(payload=payload)])
    client = FullContractPreviewApiClient(
        base_url="http://api.test",
        headers={},
        session=session,
    )

    with pytest.raises(FullContractPreviewApiError, match="案件識別不一致"):
        client.preview_client("CASE-1")


def test_browser_print_mirror_uses_only_typed_cell_values() -> None:
    mapping_path = (
        Path(__file__).resolve().parents[6]
        / "db/templates/contracts/contract_client_copy.json"
    )
    config = json.loads(mapping_path.read_text(encoding="utf-8"))

    html = render_excel_contract_mirror(
        config,
        {"case_no": "RAW-FALLBACK"},
        {},
        mapped_values={"F1": "TYPED<&"},
    )

    assert "TYPED&lt;&amp;" in html
    assert "RAW-FALLBACK" not in html
    assert "window.print()" in html
