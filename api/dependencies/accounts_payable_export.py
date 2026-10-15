"""Per-request construction for accounts-payable query and export."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from infrastructure.archive.accounts_payable import LocalAccountsPayableArchive
from infrastructure.mysql.accounts_payable_export_sources import MySqlClientRefundExportSource, MySqlReadOnlySnapshot, MySqlStaffPayableExportSource
from shared_kernel.business_time import current_business_instant
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.staff_payables.accounts_payable_export import (
    AccountsPayableExportWorkflow,
)
from infrastructure.mysql.cash_requirements_repository import MySqlCashRequirementsRepository
from subsystems.staff_payables.cash_requirements_query import query_cash_requirements

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class _ReadOnlySnapshotComposition:
    """Own finalization for the request-wide export snapshot."""

    def __init__(self, connection) -> None:
        self._connection = connection
        self._snapshot = MySqlReadOnlySnapshot(connection)

    def __enter__(self):
        return self._snapshot.__enter__()

    def __exit__(self, exception_type, exception, traceback) -> None:
        try:
            return self._snapshot.__exit__(exception_type, exception, traceback)
        finally:
            self._connection.rollback()


@dataclass(slots=True)
class AccountsPayableExportApplication:
    workflow: AccountsPayableExportWorkflow

    def query(self, target_payment_date: date):
        return self.workflow.query(target_payment_date)

    def query_case(self, case_no: str, target_payment_date: date):
        return self.workflow.query_case(case_no, target_payment_date)

    def export(self, target_payment_date: date):
        return self.workflow.export(target_payment_date)

    def query_archive(self, year: int):
        return self.workflow.query_archive(year)


def get_accounts_payable_export_application():
    connection = get_connection()
    workflow = AccountsPayableExportWorkflow(
        MySqlStaffPayableExportSource(connection),
        MySqlClientRefundExportSource(connection),
        LocalAccountsPayableArchive(_REPOSITORY_ROOT),
        lambda: _ReadOnlySnapshotComposition(connection),
        current_business_instant,
    )
    try:
        yield AccountsPayableExportApplication(workflow)
    finally:
        connection.close()


@dataclass(slots=True)
class CashRequirementsApplication:
    connection: object

    def query(self, *, page_size=100, after_case_no=None):
        with _ReadOnlySnapshotComposition(self.connection):
            return query_cash_requirements(MySqlCashRequirementsRepository(self.connection),
                page_size=page_size, after_case_no=after_case_no)


def get_cash_requirements_application():
    connection = get_connection()
    try:
        yield CashRequirementsApplication(connection)
    finally:
        connection.close()


__all__ = ['AccountsPayableExportApplication', 'get_accounts_payable_export_application']
