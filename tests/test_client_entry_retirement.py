"""Verify retired Client entries are typed, fail closed, and perform no DB work."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from api.routes import clients


def test_unbounded_client_list_is_a_typed_gone_boundary() -> None:
    with pytest.raises(HTTPException) as captured:
        clients.get_all_clients()

    assert captured.value.status_code == 410
    error = captured.value.detail["error"]
    assert error["code"] == "client_full_list_endpoint_retired"
    assert error["domain_blockers"] == [
        "replacement_identifier:/api/v1/admin/data-browser/sources/clients"
    ]
    assert error["retryable"] is False


def test_direct_identity_status_update_is_a_typed_gone_boundary() -> None:
    with pytest.raises(HTTPException) as captured:
        clients.update_client_identity_status(client_id=17)

    assert captured.value.status_code == 410
    error = captured.value.detail["error"]
    assert error["code"] == "client_identity_status_direct_update_retired"
    assert error["domain_blockers"] == [
        "replacement_identifier:/api/v1/case-import/hcm/resubmissions/preview",
        "replacement_identifier:/api/v1/case-import/hcm/resubmissions/apply",
    ]


def test_retired_client_router_has_no_database_or_raw_contract_path() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "api" / "routes" / "clients.py"
    ).read_text(encoding="utf-8")

    assert "mysql_adapter" not in source
    assert "get_table_data" not in source
    assert "UPDATE clients" not in source
    assert ".commit(" not in source
    assert ".rollback(" not in source
    assert "Dict[str, Any]" not in source
