"""Per-request Finance Import application construction."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Protocol
from fastapi import Depends

from infrastructure.mysql.finance_import_repository import (
    FinanceImportMySqlUnitOfWork,
    MySqlFinanceImportRepository,
)
from infrastructure.mysql.finance_import_owning_domain_composite import (
    MySqlFinanceImportOwningDomainComposite,
)
from infrastructure.mysql.historical_reprocess_repository import (
    MySqlHistoricalReprocessRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from scripts.imports.finance_statement_normalizer import normalize_workbook
from subsystems.finance_import.ingestion import ingest_finance_workbook
from subsystems.finance_import.query import FinanceImportQueryService
from subsystems.finance_import.correction_workflow import (
    FinanceImportCorrectionApplyRequest,
    FinanceImportCorrectionWorkflow,
)
from subsystems.finance_import.import_workflow import (
    FinanceImportApplyRequest,
    FinanceImportRepositoryUnavailable,
    FinanceImportWorkflow,
)
from subsystems.finance_import.historical_reprocess_workflow import (
    HistoricalReprocessApplyRequest,
    HistoricalReprocessWorkflow,
)
from subsystems.finance_import.refund_return_review_workflow import (
    RefundReturnReviewApplyRequest,
    RefundReturnReviewWorkflow,
)


class FinanceImportOwningDomainCompositePort(Protocol):
    def bind_request(self, request): ...

    def clear_request(self): ...

    def resolve(self, candidate): ...
    def resolve_pending_government(self, candidate): ...

    def post(self, candidate): ...

    def validate_client_refund(self, candidate, correlation_id): ...
    def preview_client_refund(self, selection, facts, correlation_id): ...


class UnavailableOwningDomainCompositePort:
    def preview_client_refund(self, selection, facts, correlation_id):
        del selection, facts, correlation_id
        raise FinanceImportRepositoryUnavailable("Owning Finance Domain composite writer is not configured.")

    def validate_client_refund(self, candidate, correlation_id):
        del candidate, correlation_id
        raise FinanceImportRepositoryUnavailable("Owning Finance Domain composite writer is not configured.")

    def bind_request(self, request):
        del request

    def clear_request(self):
        return None

    def resolve(self, candidate):
        return candidate

    def resolve_pending_government(self, candidate):
        return candidate

    def post(self, candidate):
        del candidate
        raise FinanceImportRepositoryUnavailable(
            "Owning Finance Domain composite writer is not configured."
        )


@dataclass(slots=True)
class FinanceImportApplication:
    workflow: FinanceImportWorkflow
    correction_workflow: FinanceImportCorrectionWorkflow
    posting_port: FinanceImportOwningDomainCompositePort

    def preview_batch(self, batch_identity, correlation_id, staff_subsidy_selections=()):
        return self.workflow.preview(batch_identity, correlation_id, staff_subsidy_selections)

    def apply_batch(self, request: FinanceImportApplyRequest):
        self.posting_port.bind_request(request)
        try:
            return self.workflow.apply(request)
        finally:
            self.posting_port.clear_request()

    def reconcile_pending(self, request):
        self.posting_port.bind_request(request)
        try:
            return self.workflow.reconcile_pending(request)
        finally:
            self.posting_port.clear_request()

    def preview_correction(self, selection, correlation_id):
        return self.correction_workflow.preview(selection, correlation_id)

    def correct_and_post(self, request: FinanceImportCorrectionApplyRequest):
        self.posting_port.bind_request(request)
        try:
            return self.correction_workflow.correct_and_post(request)
        finally:
            self.posting_port.clear_request()


@dataclass(slots=True)
class HistoricalReprocessApplication:
    workflow: HistoricalReprocessWorkflow
    posting_port: FinanceImportOwningDomainCompositePort

    def preview(self, batch_identity, correlation_id, owner_selections=()):
        return self.workflow.preview(batch_identity, correlation_id, owner_selections)

    def apply(self, request: HistoricalReprocessApplyRequest):
        self.posting_port.bind_request(request)
        try:
            return self.workflow.apply(request)
        finally:
            self.posting_port.clear_request()


@dataclass(slots=True)
class RefundReturnReviewApplication:
    workflow: RefundReturnReviewWorkflow

    def preview(self, selection, correlation_id):
        return self.workflow.preview(selection, correlation_id)

    def apply(self, request: RefundReturnReviewApplyRequest):
        return self.workflow.apply(request)


def build_finance_import_application(
    connection,
    posting_port: FinanceImportOwningDomainCompositePort,
) -> FinanceImportApplication:
    repository = MySqlFinanceImportRepository(connection)
    unit_of_work_factory = lambda: FinanceImportMySqlUnitOfWork(connection)
    return FinanceImportApplication(
        FinanceImportWorkflow(
            repository,
            posting_port,
            unit_of_work_factory,
        ),
        FinanceImportCorrectionWorkflow(
            repository,
            posting_port,
            unit_of_work_factory,
        ),
        posting_port,
    )


def get_finance_import_application():
    connection = get_connection()
    application = build_finance_import_application(
        connection,
        MySqlFinanceImportOwningDomainComposite(connection),
    )
    try:
        yield application
    finally:
        connection.close()


def get_historical_reprocess_application():
    connection = get_connection()
    posting_port = MySqlFinanceImportOwningDomainComposite(connection)
    application = HistoricalReprocessApplication(
        HistoricalReprocessWorkflow(
            MySqlHistoricalReprocessRepository(connection),
            posting_port,
            lambda: FinanceImportMySqlUnitOfWork(connection),
        ),
        posting_port,
    )
    try:
        yield application
    finally:
        connection.close()


def get_refund_return_review_application():
    connection = get_connection()
    try:
        yield RefundReturnReviewApplication(
            RefundReturnReviewWorkflow(
                MySqlFinanceImportRepository(connection),
                lambda: FinanceImportMySqlUnitOfWork(connection),
            )
        )
    finally:
        connection.close()


def get_finance_import_ingestion_service():
    return partial(
        ingest_finance_workbook,
        connection_factory=get_connection,
        normalizer=normalize_workbook,
    )


def get_finance_import_query_service():
    from functools import partial
    from infrastructure.mysql.subsidy_confirmation_repository import match_client_subsidy_month

    connection = get_connection()
    try:
        yield FinanceImportQueryService(connection, match_client_month=partial(match_client_subsidy_month, connection))
    finally:
        connection.close()


def get_statement_archive_application():
    from infrastructure.mysql.finance_statement_archive_repository import MySqlStatementArchiveRepository
    from subsystems.finance_import.statement_archive import StatementArchiveApplication
    connection = get_connection()
    try:
        yield StatementArchiveApplication(MySqlStatementArchiveRepository(connection))
    finally:
        connection.close()


def get_accounting_workspace():
    from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace
    connection = get_connection()
    try:
        yield build_accounting_workspace(connection)
    finally:
        connection.close()


def get_monthly_accounting_query(application=Depends(get_accounting_workspace)):
    from infrastructure.mysql.monthly_accounting_repository import MySqlMonthlyAccountingSource
    from subsystems.finance_import.monthly_accounting import MonthlyAccountingQuery
    return MonthlyAccountingQuery(MySqlMonthlyAccountingSource(application.state.connection), partial(application.query, include_sources=False))


__all__ = [
    "FinanceImportApplication",
    "FinanceImportOwningDomainCompositePort",
    "HistoricalReprocessApplication",
    "RefundReturnReviewApplication",
    "UnavailableOwningDomainCompositePort",
    "build_finance_import_application",
    "get_finance_import_application",
    "get_finance_import_ingestion_service",
    "get_finance_import_query_service",
    "get_historical_reprocess_application",
    "get_refund_return_review_application",
]
