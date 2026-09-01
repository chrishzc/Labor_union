"""
File: contract_external_signing.py
Description: 組合外部簽約 FastAPI 所需的單一連線 workflow、交易與安全 read model。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any, Iterator

from infrastructure.db.contract_external_signing_repository import (
    MySqlContractExternalSigningRepository,
)
from infrastructure.mysql.contract_full_preview_repository import (
    MySqlFullContractProjectionRepository,
)
from infrastructure.db.contract_unsigned_pdf_repository import (
    MySqlContractUnsignedPdfRepository,
)
from infrastructure.db.controlled_file_repository import (
    MySqlControlledFileWorkflowRepository,
)
from infrastructure.db.external_staff_completion_port import (
    MySqlExternalStaffCompletionPort,
)
from infrastructure.file.contract_unsigned_pdf_storage import ContractUnsignedPdfStorage
from infrastructure.file.controlled_file_storage import FileSystemControlledFileStorage
from infrastructure.file.libreoffice_contract_renderer import LibreOfficeContractRenderer
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.order_contract_completion_repository import (
    MySqlOrderContractCompletionRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.clock import SystemBusinessClock
from shared_kernel.identities import ActorContext, CorrelationId
from subsystems.contract_signing.external_signing_workflow import ExternalSigningWorkflow
from subsystems.contract_signing.full_contract_preview import FullContractPreviewApplication
from subsystems.contract_signing.final_document_preview_token import (
    HmacFinalDocumentPreviewTokenCodec,
)
from subsystems.contract_signing.final_document_workflow import FinalSignedContractWorkflow
from subsystems.contract_signing.unsigned_contract_pdf import (
    DownloadUnsignedContractPdf,
    UnsignedContractPdfApplication,
)
from subsystems.controlled_files.workflow import ControlledFileWorkflow
from subsystems.orders.contract_completion_workflow import ContractCompletionWorkflow


_LOCAL_PREVIEW_SECRET = "local-only-contract-final-preview-token-secret-v1"


@dataclass(slots=True)
class ContractExternalSigningApplication:
    connection: Any
    repository: MySqlContractExternalSigningRepository
    unsigned_repository: MySqlContractUnsignedPdfRepository
    reports: ExternalSigningWorkflow
    controlled_files: ControlledFileWorkflow
    final_documents: FinalSignedContractWorkflow
    unsigned_documents: UnsignedContractPdfApplication
    full_preview: FullContractPreviewApplication

    def load_facts(self, case_no: str):
        facts = self.repository.load_active_session_by_case(case_no, for_update=False)
        return facts or self.repository.derive_current_session(case_no, for_update=False)

    def query_case(self, case_no: str) -> dict[str, object]:
        facts = self.load_facts(case_no)
        if facts is None:
            self.reports.query_case(case_no)  # raises the canonical typed error
            raise AssertionError("query_case must return or raise")
        reported = frozenset(facts.reported_staff_segment_ids)
        document = self._representative_unsigned_document(facts)
        return {
            "case_no": facts.case_no,
            "session_id": facts.session_id,
            "state": facts.state.value,
            "status_version": facts.status_version,
            "matching_plan_id": facts.matching_plan_id,
            "commitment_id": facts.commitment_id,
            "unsigned_document": document,
            "staff_targets": [
                {
                    "matching_segment_id": target.matching_segment_id,
                    "staff_subject_reference": target.staff_subject_reference,
                    "document_version_id": target.document_version_id,
                    "reported": target.matching_segment_id in reported,
                }
                for target in facts.staff_targets
            ],
            "client_target": {
                "client_subject_reference": facts.client_subject_reference,
                "document_version_id": facts.client_document_version_id,
                "reported": facts.client_reported,
            },
        }

    def download_unsigned(
        self,
        case_no: str,
        document_version_id: int,
        actor: ActorContext,
        correlation_id: CorrelationId,
    ):
        with MySqlUnitOfWork(self.connection) as unit_of_work:
            result = self.unsigned_documents.download(
                DownloadUnsignedContractPdf(
                    case_no, document_version_id, actor, correlation_id
                )
            )
            unit_of_work.commit()
            return result

    def read_receipt(self, case_no: str, receipt_id: str) -> dict[str, object] | None:
        with self.connection.cursor() as cursor:
            cursor.execute(_RECEIPT_VIEW_SQL, (case_no, receipt_id))
            row = cursor.fetchone()
        if row is None:
            return None
        snapshot = json.loads(row["result_snapshot"])
        document = snapshot.get("document") if isinstance(snapshot, dict) else None
        return {
            "receipt_id": str(row["receipt_id"]),
            "command_type": str(row["command_type"]),
            "schema_version": str(row["schema_version"]),
            "session_id": str(row["external_signing_session_id"]),
            "outcome_state": str(row["outcome_state"]),
            "resulting_status_version": int(row["result_status_version"]),
            "resulting_state": str(snapshot["resulting_state"]),
            "matching_segment_id": snapshot.get("matching_segment_id"),
            "final_document_id": (
                document.get("final_document_id") if isinstance(document, dict) else None
            ),
            "replayed": False,
            "applied_at": _aware_utc(row["applied_at_utc"]),
        }

    def _representative_unsigned_document(self, facts) -> dict[str, object] | None:
        identities = (facts.client_document_version_id,) + tuple(
            target.document_version_id for target in facts.staff_targets
        )
        for identity in identities:
            stored = self.unsigned_repository.load_current_pdf(facts.case_no, identity)
            if stored is not None:
                return {
                    "document_version_id": stored.document_version_id,
                    "filename": stored.filename,
                    "mime_type": stored.mime_type,
                    "size_bytes": stored.size_bytes,
                }
        return None


def get_contract_external_signing_application() -> Iterator[ContractExternalSigningApplication]:
    connection = get_connection()
    try:
        clock = SystemBusinessClock()
        unit_of_work_factory = lambda: MySqlUnitOfWork(connection)
        repository = MySqlContractExternalSigningRepository(connection)
        controlled = ControlledFileWorkflow(
            MySqlControlledFileWorkflowRepository(connection),
            FileSystemControlledFileStorage(
                os.getenv("CONTROLLED_FILE_STORAGE_ROOT", "").strip() or None
            ),
            unit_of_work_factory,
            clock,
        )
        reports = ExternalSigningWorkflow(
            repository,
            MySqlExternalStaffCompletionPort(connection),
            unit_of_work_factory,
        )
        orders_completion = ContractCompletionWorkflow(
            MySqlOrderContractCompletionRepository(connection),
            unit_of_work_factory,
            clock,
        )
        unsigned_repository = MySqlContractUnsignedPdfRepository(connection)
        yield ContractExternalSigningApplication(
            connection=connection,
            repository=repository,
            unsigned_repository=unsigned_repository,
            reports=reports,
            controlled_files=controlled,
            final_documents=FinalSignedContractWorkflow(
                repository,
                controlled,
                orders_completion,
                unit_of_work_factory,
                clock,
                HmacFinalDocumentPreviewTokenCodec(_preview_token_secret()),
            ),
            unsigned_documents=UnsignedContractPdfApplication(
                unsigned_repository,
                ContractUnsignedPdfStorage(controlled),
                LibreOfficeContractRenderer(),
            ),
            full_preview=FullContractPreviewApplication(
                MySqlFullContractProjectionRepository(connection),
                clock,
            ),
        )
    finally:
        connection.close()


def _preview_token_secret() -> str:
    configured = os.getenv("CONTRACT_FINAL_PREVIEW_TOKEN_SECRET", "").strip()
    if configured:
        if len(configured.encode("utf-8")) < 32:
            raise RuntimeError("contract final preview token secret is too short")
        return configured
    environment = os.getenv("APP_ENV", "development").strip().lower()
    if environment in {"production", "prod"}:
        raise RuntimeError("contract final preview token secret is required")
    return _LOCAL_PREVIEW_SECRET


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


_RECEIPT_VIEW_SQL = (
    "SELECT receipt.receipt_id,receipt.command_type,receipt.schema_version,"
    "receipt.result_status_version,receipt.outcome_state,receipt.result_snapshot,"
    "receipt.applied_at_utc,session.external_signing_session_id "
    "FROM contract_external_signing_receipts receipt "
    "JOIN contract_external_signing_sessions session "
    "ON session.id=receipt.external_signing_session_id "
    "WHERE session.case_no=%s AND receipt.receipt_id=%s LIMIT 1"
)


__all__ = [
    "ContractExternalSigningApplication",
    "get_contract_external_signing_application",
]
