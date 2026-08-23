"""
File: test_jobs_public_observation_route.py
Description: 驗證背景工作 observation 只公開允許的執行狀態欄位。
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.routes.jobs import get_job_observation


def _job(command_type: str):
    return SimpleNamespace(
        job_id="job-observation-1",
        command_type=command_type,
        status="running",
        attempt_count=1,
        max_attempts=3,
        receipt_payload={"secret": "hidden"},
        error_payload={"internal": "hidden"},
    )


def test_observation_excludes_receipt_and_error_payload() -> None:
    class Repository:
        def get_job(self, _):
            return _job("assignment_plan_apply")

    response = get_job_observation("job-observation-1", None, Repository())
    assert response.data.model_dump() == {
        "job_id": "job-observation-1",
        "command_type": "assignment_plan_apply",
        "status": "running",
        "attempt_count": 1,
        "max_attempts": 3,
    }


def test_observation_fails_closed_for_untyped_command_type() -> None:
    class Repository:
        def get_job(self, _):
            return _job("legacy.untyped")

    with pytest.raises(HTTPException) as error:
        get_job_observation("job-observation-1", None, Repository())
    assert error.value.status_code == 503
    assert error.value.detail["error"]["code"] == "job_observation_unavailable"
