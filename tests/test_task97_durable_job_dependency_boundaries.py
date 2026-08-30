"""
File: test_task97_durable_job_dependency_boundaries.py
Description: 驗證 generic Durable Job worker 與 concrete composition 的依賴方向。
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_generic_durable_worker_has_no_api_or_infrastructure_composition() -> None:
    source = (PROJECT_ROOT / "subsystems/jobs/durable_job_worker.py").read_text(
        encoding="utf-8"
    )

    assert "from api." not in source
    assert "from infrastructure." not in source
    assert "default_job_handlers" not in source


def test_concrete_handlers_live_in_outer_api_composition() -> None:
    source = (PROJECT_ROOT / "api/dependencies/durable_job_handlers.py").read_text(
        encoding="utf-8"
    )

    assert "def default_job_handlers" in source
    assert "from subsystems.jobs.durable_job_worker import JobHandler" in source
