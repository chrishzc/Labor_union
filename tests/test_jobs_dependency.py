"""
File: test_jobs_dependency.py
Description: 驗證 Durable Job dependencies 組合 canonical Bridge 並於成功或例外後關閉 connection。
"""

from __future__ import annotations

import pytest

from api.dependencies import jobs
from infrastructure.mysql.background_job_repository import BackgroundJobRepository
from subsystems.jobs.command_application import DurableJobCommandApplication
from subsystems.jobs.command_application import DurableJobCancellationApplication


class _Connection:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


@pytest.mark.parametrize(
    ("dependency", "expected_type"),
    [
        (jobs.get_job_repository, BackgroundJobRepository),
        (jobs.get_durable_job_application, DurableJobCommandApplication),
        (jobs.get_durable_job_cancellation, DurableJobCancellationApplication),
    ],
)
def test_jobs_dependency_closes_connection(dependency, expected_type, monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(jobs, "get_connection", lambda: connection)
    provider = dependency()

    assert isinstance(next(provider), expected_type)
    provider.close()

    assert connection.closed == 1


def test_jobs_dependency_closes_connection_when_consumer_raises(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(jobs, "get_connection", lambda: connection)
    provider = jobs.get_durable_job_application()
    next(provider)

    with pytest.raises(RuntimeError, match="consumer failed"):
        provider.throw(RuntimeError("consumer failed"))

    assert connection.closed == 1
