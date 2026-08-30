"""Task 97 guards for repository and application transaction ownership."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


REPOSITORIES_WITH_CALLER_OWNED_TRANSACTIONS = (
    "infrastructure/mysql/admin_command_repository.py",
    "infrastructure/mysql/background_job_repository.py",
    "infrastructure/mysql/hcm_workbook_import_repository.py",
    "infrastructure/mysql/historical_order_workbook_import_repository.py",
    "infrastructure/mysql/matching_schedule_confirmation_repository.py",
    "infrastructure/mysql/service_date_confirmation_repository.py",
    "infrastructure/mysql/staff_historical_workbook_repository.py",
)


def test_task97_repositories_do_not_own_commit_or_rollback() -> None:
    for relative_path in REPOSITORIES_WITH_CALLER_OWNED_TRANSACTIONS:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert ".commit(" not in source, relative_path
        assert ".rollback(" not in source, relative_path


def test_task97_workflows_do_not_call_repository_transaction_methods() -> None:
    for relative_path in (
        "subsystems/case_import/hcm_workbook_import.py",
        "subsystems/case_import/staff_historical_workbook_adoption.py",
        "subsystems/orders/client_name_maintenance.py",
        "subsystems/orders/historical_order_workbook_import.py",
        "subsystems/orders/service_date_confirmation_workflow.py",
        "subsystems/scheduling/matching_schedule_confirmation.py",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "repository.commit(" not in source, relative_path
        assert "repository.rollback(" not in source, relative_path
        assert "_repository.commit(" not in source, relative_path
        assert "_repository.rollback(" not in source, relative_path


def test_task97_refactored_routes_do_not_own_transactions() -> None:
    for relative_path in (
        "api/routes/holidays.py",
        "api/routes/staff_leave_intake.py",
        "api/routes/staff_leave_management.py",
        "api/routes/staff_service_day_logs.py",
        "api/routes/staff_service_day_media.py",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert ".commit(" not in source, relative_path
        assert ".rollback(" not in source, relative_path
