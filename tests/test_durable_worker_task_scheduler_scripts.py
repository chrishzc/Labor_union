"""Guard the Windows Task Scheduler deployment contract for durable jobs."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_ROOT = ROOT / "scripts" / "launchers"


def _script(name: str) -> str:
    return (LAUNCHER_ROOT / name).read_text(encoding="utf-8")


def test_deferred_supervision_has_no_install_entrypoint() -> None:
    assert not (LAUNCHER_ROOT / "install_durable_job_worker_task.ps1").exists()
    assert not (ROOT / "scripts" / "install_durable_job_worker_task.ps1").exists()


def test_uninstall_and_status_scripts_are_safe_and_read_only() -> None:
    uninstall = _script("uninstall_durable_job_worker_task.ps1")
    status = _script("get_durable_job_worker_task_status.ps1")

    assert "SupportsShouldProcess" in uninstall
    assert "Unregister-ScheduledTask" in uninstall
    assert "Get-ScheduledTaskInfo" in status
    assert "Start-ScheduledTask" not in status
