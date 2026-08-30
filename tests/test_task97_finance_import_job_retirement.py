"""Verify the duplicate Finance Import job-status entry is a typed 410 boundary."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from api.routes.finance_import import query_finance_import_job


def test_duplicate_finance_import_job_status_is_typed_gone() -> None:
    with pytest.raises(HTTPException) as captured:
        query_finance_import_job("job-17", None)

    assert captured.value.status_code == 410
    error = captured.value.detail["error"]
    assert error["code"] == "finance_import_job_status_endpoint_retired"
    assert error["domain_blockers"] == [
        "replacement_identifier:/api/v1/jobs/{job_id}/observation"
    ]
    assert error["retryable"] is False
    assert error["correlation_id"] == "finance-import-job-retired:job-17"


def test_retired_finance_import_job_status_has_no_repository_query() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "api" / "routes" / "finance_import.py"
    ).read_text(encoding="utf-8")
    function = source.split("def query_finance_import_job(", 1)[1].split(
        "@router.get(\n    \"/jobs/{job_id}/batch-outcome\"", 1
    )[0]

    assert "get_job_repository" not in function
    assert ".get_job(" not in function
    assert "HTTP_410_GONE" in function
