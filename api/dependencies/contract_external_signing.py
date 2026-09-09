"""
File: contract_external_signing.py
Description: 組合外部簽約 FastAPI 所需的單一連線 workflow、交易與安全 read model。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
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
from infrastructure.archive.contract_documents import (
    archive_contract_document,
    discard_uncommitted_contract_document,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.line_delivery_task_repository import (
    MySqlLineDeliveryTaskRepository,
)
from infrastructure.mysql.order_contract_completion_repository import (
    MySqlOrderContractCompletionRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.clock import SystemBusinessClock
from shared_kernel.identities import ActorContext, CorrelationId
from subsystems.contract_signing.external_signing_contracts import ExternalSigningTypedError
from subsystems.contract_signing.external_signing_workflow import ExternalSigningWorkflow
from subsystems.contract_signing.full_contract_preview import FullContractPreviewApplication
from subsystems.contract_signing.full_contract_preview import FullContractPreviewError
from subsystems.contract_signing.final_document_preview_token import (
    HmacFinalDocumentPreviewTokenCodec,
)
from subsystems.contract_signing.final_document_workflow import FinalSignedContractWorkflow
from subsystems.contract_signing.unsigned_contract_pdf import (
    DownloadUnsignedContractPdf,
    UnsignedContractPdfApplication,
)
from subsystems.contract_signing.unsigned_contract_pdf_persistence import (
    PrepareAndPersistUnsignedContractPdf,
    UnsignedContractPdfPersistenceWorkflow,
)
from subsystems.contract_signing.staff_contract_application import (
    PrepareExternalStaffContractCommand,
    StaffContractSigningApplication,
)
from subsystems.contract_signing.line_delivery import (
    ContractLineBinding,
    build_external_platform_reminder_request,
    external_platform_staff_reminder_text,
    require_contract_line_recipient,
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
    staff_documents: StaffContractSigningApplication
    unsigned_persistence: UnsignedContractPdfPersistenceWorkflow

    def load_facts(self, case_no: str):
        facts = self.repository.load_active_session_by_case(case_no, for_update=False)
        return facts or self.repository.derive_current_session(case_no, for_update=False)

    def query_case(self, case_no: str) -> dict[str, object]:
        active = self.repository.load_active_session_by_case(case_no, for_update=False)
        facts = active or self.repository.derive_current_session(case_no, for_update=False)
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
            "handoff_recorded": active is not None,
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

    def prepare_staff_unsigned(
        self,
        case_no: str,
        matching_segment_id: int,
        actor: ActorContext,
        idempotency_key,
        correlation_id: CorrelationId,
    ) -> dict[str, object]:
        try:
            source = self.staff_documents.prepare_external_document(
                PrepareExternalStaffContractCommand(
                    case_no=case_no,
                    matching_segment_id=matching_segment_id,
                    actor_id=actor.actor_id,
                    idempotency_key=idempotency_key,
                    correlation_id=correlation_id,
                )
            )
        except ValueError as error:
            if str(error) == "contract_external_signing_accepted_plan_required":
                raise ExternalSigningTypedError(
                    category="conflict",
                    code="external_signing_accepted_plan_required",
                    message="目前案件尚未具備已接受且有效的配對方案。",
                ) from error
            raise
        existing = self.unsigned_repository.load_current_pdf_for_source(
            case_no, source.source_document_version_id
        )
        if existing is not None:
            return {
                "document_version_id": existing.document_version_id,
                "filename": existing.filename,
                "mime_type": existing.mime_type,
                "size_bytes": existing.size_bytes,
                "replayed": True,
            }
        persisted = self.unsigned_persistence.prepare_and_persist(
            PrepareAndPersistUnsignedContractPdf(
                case_no=case_no,
                source_document_version_id=source.source_document_version_id,
                actor=actor,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        )
        return {
            "document_version_id": persisted.document_version_id,
            "filename": persisted.filename,
            "mime_type": persisted.mime_type,
            "size_bytes": persisted.size_bytes,
            "replayed": source.replayed or persisted.replayed,
        }

    def staff_reminder_readiness(
        self, case_no: str, matching_segment_id: int
    ) -> dict[str, object]:
        facts = self.load_facts(case_no)
        if facts is None:
            raise ExternalSigningTypedError(
                category="conflict",
                code="external_signing_session_facts_unavailable",
                message="目前案件尚未具備可啟動的簽約 facts。",
            )
        target = facts.staff_target(matching_segment_id)
        if target is None:
            raise ExternalSigningTypedError(
                category="not_found",
                code="external_staff_report_target_not_found",
                message="找不到指定的月嫂簽約對象。",
            )
        stored = self.unsigned_repository.load_current_pdf(
            case_no, target.document_version_id
        )
        binding = self._staff_binding(target.staff_subject_reference, for_update=False)
        blockers = []
        if stored is None:
            blockers.append("contract_unsigned_pdf_missing")
        try:
            require_contract_line_recipient(
                binding,
                subject_type="staff",
                subject_reference=target.staff_subject_reference,
            )
        except ValueError as error:
            blockers.append(str(error))
        return {
            "matching_segment_id": matching_segment_id,
            "document_version_id": target.document_version_id,
            "message": external_platform_staff_reminder_text(case_no),
            "blockers": blockers,
            "ready": not blockers,
        }

    def enqueue_staff_reminder(
        self,
        case_no: str,
        matching_segment_id: int,
        expected_document_version_id: int,
        actor: ActorContext,
        idempotency_key,
        correlation_id: CorrelationId,
    ) -> dict[str, object]:
        with MySqlUnitOfWork(self.connection) as unit_of_work:
            facts = self.repository.load_active_session_by_case(
                case_no, for_update=True
            ) or self.repository.derive_current_session(case_no, for_update=True)
            if facts is None:
                raise ExternalSigningTypedError(
                    category="conflict",
                    code="external_signing_session_facts_unavailable",
                    message="目前案件尚未具備可建立提醒的簽約 facts。",
                )
            target = facts.staff_target(matching_segment_id)
            if target is None:
                raise ExternalSigningTypedError(
                    category="not_found",
                    code="external_staff_report_target_not_found",
                    message="找不到指定的月嫂簽約對象。",
                )
            if target.document_version_id != expected_document_version_id:
                raise ExternalSigningTypedError(
                    category="conflict",
                    code="external_staff_report_document_stale",
                    message="月嫂契約文件版本已變更。",
                )
            if self.unsigned_repository.load_current_pdf(
                case_no, target.document_version_id
            ) is None:
                raise ExternalSigningTypedError(
                    category="conflict",
                    code="contract_unsigned_pdf_missing",
                    message="月嫂未簽契約 PDF 尚未備妥。",
                )
            binding = self._staff_binding(
                target.staff_subject_reference, for_update=True
            )
            try:
                recipient = require_contract_line_recipient(
                    binding,
                    subject_type="staff",
                    subject_reference=target.staff_subject_reference,
                )
            except ValueError as error:
                raise ExternalSigningTypedError(
                    category="domain_blocked",
                    code=str(error),
                    message="月嫂 LINE 身分尚未完成正確綁定。",
                ) from error
            result = MySqlLineDeliveryTaskRepository(self.connection).enqueue(
                build_external_platform_reminder_request(
                    recipient,
                    case_no=case_no,
                    session_id=facts.session_id,
                    matching_segment_id=matching_segment_id,
                    document_version_id=target.document_version_id,
                    scheduled_at=datetime.now(timezone.utc),
                    idempotency_key=idempotency_key,
                    correlation_id=correlation_id,
                )
            )
            unit_of_work.commit()
        return {
            "task_id": result.task_id.value,
            "status": result.status.value,
            "replayed": result.outcome.value != "created",
        }

    def _staff_binding(
        self, subject_reference: str, *, for_update: bool
    ) -> ContractLineBinding:
        suffix = " FOR UPDATE" if for_update else ""
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT line_user_id,binding_status,subject_type,subject_reference "
                "FROM line_identity_bindings WHERE subject_type='staff' "
                "AND subject_reference=%s" + suffix,
                (subject_reference,),
            )
            row = cursor.fetchone()
        if row is None:
            return ContractLineBinding(None, None, None, None)
        return ContractLineBinding(
            str(row["line_user_id"]),
            str(row["binding_status"]),
            str(row["subject_type"]),
            str(row["subject_reference"]),
        )

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
        identities = tuple(
            target.document_version_id for target in facts.staff_targets
        )
        if facts.client_document_version_id is not None:
            identities = (facts.client_document_version_id,) + identities
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
        unsigned_repository = MySqlContractUnsignedPdfRepository(
            connection,
            archive_root=_contract_archive_root(),
        )
        unsigned_documents = UnsignedContractPdfApplication(
            unsigned_repository,
            ContractUnsignedPdfStorage(controlled),
            LibreOfficeContractRenderer(),
        )
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
                MySqlExternalStaffCompletionPort(connection),
                unit_of_work_factory,
                clock,
                HmacFinalDocumentPreviewTokenCodec(_preview_token_secret()),
            ),
            unsigned_documents=unsigned_documents,
            full_preview=FullContractPreviewApplication(
                MySqlFullContractProjectionRepository(connection),
                clock,
            ),
            staff_documents=StaffContractSigningApplication(
                get_connection,
                archive_root=_contract_archive_root(),
                now=lambda: datetime.now(timezone.utc),
                archive_document=archive_contract_document,
                discard_document=discard_uncommitted_contract_document,
                external_template_facts_loader=_load_external_staff_template_facts,
            ),
            unsigned_persistence=UnsignedContractPdfPersistenceWorkflow(
                unsigned_documents,
                controlled,
                unsigned_repository,
                unit_of_work_factory,
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


def _contract_archive_root():
    configured = os.getenv("CONTRACT_DOCUMENT_ARCHIVE_ROOT", "").strip()
    return (
        Path(configured)
        if configured
        else Path(__file__).resolve().parents[2]
        / "runtime_data"
        / "contracts"
    )


def _load_external_staff_template_facts(
    connection, case_no: str, matching_segment_id: int, now: datetime
) -> tuple[dict[str, object], str]:
    repository = MySqlFullContractProjectionRepository(connection)
    projection = repository.load_staff_projection_for_segment(
        case_no, matching_segment_id
    )
    if projection is None:
        raise FullContractPreviewError(
            "contract_preview_target_not_found",
            "找不到指定契約預覽對象。",
            not_found=True,
        )
    preview = FullContractPreviewApplication(repository).preview_staff_segment(
        case_no, matching_segment_id
    )
    if preview.blockers:
        raise FullContractPreviewError(
            preview.blockers[0],
            "契約必要欄位尚未齊全，不能產生未簽 PDF。",
        )
    facts = dict(projection.facts)
    facts["contract_signed_date"] = now.date()
    facts["__today__"] = now.date()
    return facts, preview.preview_fingerprint.value


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
