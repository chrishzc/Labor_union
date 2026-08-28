"""
File: test_launcher_inventory.py
Description: 驗證操作用 launcher 集中於正式目錄，且已退役入口不會復活。
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_ROOT = ROOT / "scripts" / "launchers"


def test_operator_launchers_are_converged_under_one_directory() -> None:
    expected = {
        "configure_local_admin_no_auth.bat",
        "configure_local_admin_no_auth.ps1",
        "get_durable_job_worker_task_status.ps1",
        "reset_DB.bat",
        "start_fastapi_ngrok.py",
        "start_local_development.bat",
        "start_local_development.sh",
        "start_local_development_no_auth.bat",
        "start_local_development_no_auth.sh",
        "supervise_local_runtime.ps1",
        "uninstall_durable_job_worker_task.ps1",
        "update_local_database.bat",
    }

    assert expected <= {path.name for path in LAUNCHER_ROOT.iterdir()}


def test_retired_or_moved_legacy_launcher_paths_do_not_return() -> None:
    legacy_paths = (
        "bootstrap_admin_dev_env.bat",
        "dev_API.bat",
        "online.bat",
        "online.sh",
        "reset_DB.bat",
        "start.bat",
        "start_fastapi_ngrok.py",
        "update_DB.bat",
        "scripts/bootstrap_admin_dev_env.ps1",
        "scripts/install_durable_job_worker_task.ps1",
    )

    assert all(not (ROOT / relative_path).exists() for relative_path in legacy_paths)
