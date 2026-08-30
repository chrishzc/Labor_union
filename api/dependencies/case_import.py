"""Composition root for Case Import applications."""

from infrastructure.mysql.case_import_repository import (
    CaseImportMySqlUnitOfWork,
    MySqlCaseImportRepository,
)
from subsystems.case_import.application import CaseImportApplication
from subsystems.case_import.case_import_workflow import CaseImportWorkflow


def build_case_import_application(connection) -> CaseImportApplication:
    repository = MySqlCaseImportRepository(connection)
    return CaseImportApplication(
        repository,
        CaseImportWorkflow(repository, lambda: CaseImportMySqlUnitOfWork(connection)),
        lambda: CaseImportMySqlUnitOfWork(connection),
    )


__all__ = ["build_case_import_application"]
