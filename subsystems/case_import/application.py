"""Compose the Case Import workflow with its MySQL repository and unit of work."""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.case_import_repository import (
    CaseImportMySqlUnitOfWork,
    MySqlCaseImportRepository,
)
from subsystems.case_import.case_import_workflow import (
    ApplyCaseImport,
    CaseImportWorkflow,
)


@dataclass(frozen=True)
class CaseImportApplication:
    repository: MySqlCaseImportRepository
    workflow: CaseImportWorkflow

    def case_exists(self, case_no):
        return self.repository.case_exists(case_no)

    def preview(self, intent, correlation_id):
        return self.workflow.preview(intent, correlation_id)

    def apply(self, command: ApplyCaseImport):
        return self.workflow.apply(command)


def build_case_import_application(connection) -> CaseImportApplication:
    repository = MySqlCaseImportRepository(connection)
    return CaseImportApplication(
        repository,
        CaseImportWorkflow(repository, lambda: CaseImportMySqlUnitOfWork(connection)),
    )

