"""
File: application.py
Description: 組合 Case Import workflow、MySQL repository 與 outer UoW。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypeVar

from domains.case_import.case_import import resolve_hcm_identity
from subsystems.case_import.case_import_workflow import (
    ApplyCaseImport,
    CaseImportRepository,
    CaseImportWorkflow,
)


_T = TypeVar("_T")


@dataclass(frozen=True)
class CaseImportApplication:
    repository: CaseImportRepository
    workflow: CaseImportWorkflow
    unit_of_work_factory: Callable[[], object]

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

    def apply_in_current_uow(self, command: ApplyCaseImport):
        return self.workflow.apply_in_current_uow(command)

    def execute_in_uow(self, operation: Callable[[], _T]) -> _T:
        """Run a Case Import composition under one outer transaction.

        The callback may include review persistence and borrowed owning-domain
        commands.  Repositories and adapters only use the caller's connection;
        this method is the sole commit owner for the composition.
        """
        with self.unit_of_work_factory() as unit_of_work:
            result = operation()
            unit_of_work.commit()
            return result
