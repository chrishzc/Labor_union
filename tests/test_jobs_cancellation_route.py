"""
File: test_jobs_cancellation_route.py
Description: 驗證 Durable Job canonical cancellation 的typed route與outer UoW契約。
"""

from types import SimpleNamespace

import pytest

from api.routes.jobs import cancel_queued_job
from subsystems.jobs.command_application import DurableJobCancellationApplication
from shared_kernel.durable_job_queue import DurableJobStateConflict


def _job(status="queued"):
    return SimpleNamespace(
        job_id="job-1", status=status, receipt_payload=None, error_payload=None,
        command_type="assignment_plan_apply", attempt_count=0, max_attempts=3, result_reference=None,
    )


def test_cancels_only_a_queued_job():
    class Repository:
        def __init__(self):
            self.job = _job()

        def get_job(self, _):
            return self.job

    class Cancellation:
        def cancel_queued(self, job_id):
            assert job_id == "job-1"

    response = cancel_queued_job("job-1", None, Repository(), Cancellation())

    assert response.data.status == "cancelled"


def test_rejects_cancellation_after_a_worker_claims_the_job():
    class Repository:
        def get_job(self, _):
            return _job("running")

    class Cancellation:
        def cancel_queued(self, _):
            raise DurableJobStateConflict("claimed")

    with pytest.raises(Exception) as error:
        cancel_queued_job("job-1", None, Repository(), Cancellation())

    assert "job_state_conflict" in str(error.value.detail)
"""
File: test_jobs_cancellation_route.py
Description: 驗證 Durable Job 只取消 queued 狀態，並透過 outer-UoW cancellation application。
"""
