"""
File: test_jobs_public_outcome_route.py
Description: 驗證 Durable Job public GET 只輸出 closed masked terminal outcome，拒絕 raw payload。
"""

from types import SimpleNamespace

import pytest

from api.routes.jobs import get_job_status


def _repository(job):
    return SimpleNamespace(get_job=lambda _job_id: job)


def _job(status, receipt=None, error=None):
    return SimpleNamespace(
        job_id="job-1",
        status=status,
        receipt_payload=receipt,
        error_payload=error,
        command_type="finance_import_batch_apply",
        attempt_count=1,
        max_attempts=3,
        result_reference=None,
    )


def test_public_success_exposes_only_safe_result_reference() -> None:
    job = _job(
        "succeeded",
        {"kind": "success", "schema_version": 1, "result_reference": "finance_import:batch-1"},
    )

    response = get_job_status("job-1", None, _repository(job))

    assert response.data.outcome.kind == "success"
    assert response.data.outcome.result_reference == "finance_import:batch-1"
    assert "receipt_payload" not in response.data.model_dump()


def test_public_failure_exposes_closed_typed_error() -> None:
    job = _job(
        "failed",
        error={
            "kind": "failure",
            "schema_version": 1,
            "error": {
                "category": "domain_blocked",
                "code": "finance_review_required",
                "message": "Review is required.",
                "retryable": False,
                "domain_blockers": ["finance.review"],
            },
        },
    )

    response = get_job_status("job-1", None, _repository(job))

    assert response.data.outcome.kind == "failure"
    assert response.data.outcome.error.code == "finance_review_required"


def test_public_outcome_rejects_raw_or_extra_terminal_payload() -> None:
    job = _job(
        "succeeded",
        {
            "kind": "success",
            "schema_version": 1,
            "result_reference": "safe:1",
            "raw_receipt": {"bank_account": "unsafe"},
        },
    )

    with pytest.raises(Exception) as raised:
        get_job_status("job-1", None, _repository(job))

    assert raised.value.status_code == 503
    assert raised.value.detail["error"]["code"] == "job_outcome_contract_unavailable"
