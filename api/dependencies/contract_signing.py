"""Composition root for contract-signing applications."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path

from infrastructure.mysql.contract_signing_document_query_repository import (
    MySqlContractSigningDocumentQueryRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.archive.contract_documents import archive_contract_document, discard_uncommitted_contract_document
from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from infrastructure.mysql.order_contract_completion_repository import MySqlOrderContractCompletionRepository
from infrastructure.mysql.order_terms_read_model import load_contract_client_finance_facts, select_order
from infrastructure.mysql.client_finance_terms_writer import persist_client_finance_terms_impact
from shared_kernel.clock import SystemBusinessClock
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion
from domains.orders.contract_completion import ContractCompletionIntent
from subsystems.orders.contract_completion_workflow import ContractCompletionApplyRequest, ContractCompletionWorkflow
from subsystems.contract_signing.client_contract_application import (
    ClientContractSigningApplication,
)
from subsystems.contract_signing.staff_contract_application import (
    StaffContractSigningApplication,
)
from subsystems.contract_signing.document_query import (
    ContractSigningDocumentQueryApplication,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_staff_contract_signing_application() -> StaffContractSigningApplication:
    return StaffContractSigningApplication(
        get_connection,
        archive_root=_archive_root(),
        now=lambda: datetime.now(timezone.utc),
        archive_document=archive_contract_document,
        discard_document=discard_uncommitted_contract_document,
        line_delivery_repository_factory=MySqlLineDeliveryTaskRepository,
        order_selector=select_order,
        finance_facts_loader=load_contract_client_finance_facts,
        finance_terms_writer=persist_client_finance_terms_impact,
    )


def get_client_contract_signing_application() -> ClientContractSigningApplication:
    return ClientContractSigningApplication(
        get_connection,
        archive_root=_archive_root(),
        now=lambda: datetime.now(timezone.utc),
        archive_document=archive_contract_document,
        discard_document=discard_uncommitted_contract_document,
        line_delivery_repository_factory=MySqlLineDeliveryTaskRepository,
        completion=_complete_contract_in_transaction,
    )


def get_contract_signing_document_query_application():
    connection = get_connection()
    try:
        yield ContractSigningDocumentQueryApplication(
            MySqlContractSigningDocumentQueryRepository(connection)
        )
    finally:
        connection.close()


def _archive_root() -> Path:
    configured = os.getenv("CONTRACT_DOCUMENT_ARCHIVE_ROOT", "").strip()
    return Path(configured) if configured else PROJECT_ROOT / "runtime_data" / "contracts"


class _JoinedTransaction:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self) -> None:
        return None


def _complete_contract_in_transaction(connection, command, identity: str) -> None:
    repository = MySqlOrderContractCompletionRepository(connection)
    repository.record_contract_identity(command.case_no, identity)
    workflow = ContractCompletionWorkflow(repository, _JoinedTransaction, SystemBusinessClock())
    facts = repository.load_for_apply(command.case_no)
    preview = workflow.preview(command.case_no, ContractCompletionIntent.CONFIRM_COMPLETED)
    workflow.apply(ContractCompletionApplyRequest(
        command.case_no,
        ContractCompletionIntent.CONFIRM_COMPLETED,
        ExpectedVersion(facts.order.aggregate_version),
        ExpectedVersion(facts.client_finance.account_version),
        preview.fingerprint,
        command.idempotency_key,
        ActorContext(command.actor_id),
        "client signed returned contract was accepted",
        command.correlation_id,
    ))
