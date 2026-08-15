"""
File: application.py
Description: 組合 Case Import workflow、MySQL repository 與 outer UoW。
"""

from __future__ import annotations

from dataclasses import dataclass

from domains.case_import.case_import import resolve_hcm_identity
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

    def resolve_hcm_identity(self, case_no, ip_address, client_name):
        facts = self.repository.load_hcm_identity_facts(
            case_no, ip_address, client_name
        )
        return resolve_hcm_identity(facts)

    def find_receipt(self, key):
        return self.repository.find_receipt(key)

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
