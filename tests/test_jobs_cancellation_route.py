from types import SimpleNamespace

import pytest

from api.routes.jobs import cancel_queued_job
from shared_kernel.durable_job_queue import DurableJobStateConflict


def _job(status="queued"):
    return SimpleNamespace(
        job_id="job-1", status=status, receipt_payload=None, error_payload=None,
        command_type="test.command", attempt_count=0, max_attempts=3, result_reference=None,
    )


def test_cancels_only_a_queued_job():
    class Repository:
        def __init__(self):
            self.job = _job()

        def get_job(self, _):
            return self.job

        def cancel_queued_job(self, _):
            self.job.status = "cancelled"

    response = cancel_queued_job("job-1", None, Repository())

    assert response.data.status == "cancelled"


def test_rejects_cancellation_after_a_worker_claims_the_job():
    class Repository:
        def get_job(self, _):
            return _job("running")

        def cancel_queued_job(self, _):
            raise DurableJobStateConflict("claimed")

    with pytest.raises(Exception) as error:
        cancel_queued_job("job-1", None, Repository())

    assert "job_state_conflict" in str(error.value.detail)
