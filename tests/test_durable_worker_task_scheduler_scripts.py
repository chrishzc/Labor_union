"""Guard the Windows Task Scheduler deployment contract for durable jobs."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _script(name: str) -> str:
    return (ROOT / "scripts" / name).read_text(encoding="utf-8")


def test_install_script_registers_a_supervised_system_worker() -> None:
    source = _script("install_durable_job_worker_task.ps1")

    assert "run_durable_job_worker.py" in source
    assert "New-ScheduledTaskTrigger -AtStartup" in source
    assert '-UserId "SYSTEM"' in source
    assert "-RestartCount 3" in source
    assert "-RestartInterval (New-TimeSpan -Minutes 1)" in source
    assert "[switch]$StartNow" in source


def test_uninstall_and_status_scripts_are_safe_and_read_only() -> None:
    uninstall = _script("uninstall_durable_job_worker_task.ps1")
    status = _script("get_durable_job_worker_task_status.ps1")

    assert "SupportsShouldProcess" in uninstall
    assert "Unregister-ScheduledTask" in uninstall
    assert "Get-ScheduledTaskInfo" in status
    assert "Start-ScheduledTask" not in status
