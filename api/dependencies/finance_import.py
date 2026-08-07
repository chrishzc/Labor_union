"""Per-request Finance Import application construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

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

    def post(self, candidate): ...


class UnavailableOwningDomainCompositePort:
    def bind_request(self, request):
        del request

    def clear_request(self):
        return None

    def resolve(self, candidate):
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

    def preview_batch(self, batch_identity, correlation_id):
        return self.workflow.preview(batch_identity, correlation_id)

    def apply_batch(self, request: FinanceImportApplyRequest):
        self.posting_port.bind_request(request)
        try:
            return self.workflow.apply(request)
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

    def preview(self, batch_identity, correlation_id):
        return self.workflow.preview(batch_identity, correlation_id)

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
    return ingest_finance_workbook


def get_finance_import_query_service():
    connection = get_connection()
    try:
        yield FinanceImportQueryService(connection)
    finally:
        connection.close()


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
