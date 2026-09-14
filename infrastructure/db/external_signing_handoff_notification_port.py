"""Create all LINE notification tasks inside the handoff transaction."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any

from domains.contract_signing.external_signing import ExternalSigningSessionFacts
from infrastructure.mysql.line_delivery_task_repository import (
    MySqlLineDeliveryTaskRepository,
)
from shared_kernel.identities import IdempotencyKey
from subsystems.contract_signing.external_signing_contracts import (
    ExternalSigningTypedError,
)
from subsystems.contract_signing.external_signing_workflow import (
    RecordExternalSigningHandoff,
)
from subsystems.contract_signing.line_delivery import (
    ContractLineBinding,
    build_external_platform_client_reminder_request,
    build_external_platform_reminder_request,
    require_contract_line_recipient,
)


class MySqlExternalSigningHandoffNotificationPort:
    """Borrowed adapter; the external-signing workflow remains commit owner."""

    def __init__(self, connection: Any, unsigned_repository: Any) -> None:
        self._connection = connection
        self._unsigned_repository = unsigned_repository
        self._delivery_tasks = MySqlLineDeliveryTaskRepository(connection)

    def enqueue_notifications(
        self,
        command: RecordExternalSigningHandoff,
        facts: ExternalSigningSessionFacts,
    ) -> None:
        client_document_id = facts.client_document_version_id
        if client_document_id is None:
            raise self._blocked(
                "contract_unsigned_pdf_missing",
                "客戶未簽契約 PDF 尚未備妥。",
            )

        targets: list[tuple[str, str, int, int | None]] = [
            (
                "customer",
                facts.client_subject_reference,
                client_document_id,
                None,
            )
        ]
        targets.extend(
            (
                "staff",
                target.staff_subject_reference,
                target.document_version_id,
                target.matching_segment_id,
            )
            for target in facts.staff_targets
        )

        prepared = []
        for subject_type, subject_reference, document_id, segment_id in targets:
            if self._unsigned_repository.load_current_pdf(facts.case_no, document_id) is None:
                label = "客戶" if subject_type == "customer" else f"月嫂 {subject_reference}"
                raise self._blocked(
                    "contract_unsigned_pdf_missing",
                    f"{label}未簽契約 PDF 尚未備妥。",
                )
            try:
                recipient = require_contract_line_recipient(
                    self._binding(subject_type, subject_reference),
                    subject_type=subject_type,
                    subject_reference=subject_reference,
                )
            except ValueError as error:
                label = "客戶" if subject_type == "customer" else f"月嫂 {subject_reference}"
                raise self._blocked(str(error), f"{label} LINE 身分尚未完成正確綁定。") from error
            prepared.append((recipient, subject_type, document_id, segment_id))

        scheduled_at = datetime.now(timezone.utc)
        for recipient, subject_type, document_id, segment_id in prepared:
            key = _derived_key(command.idempotency_key, subject_type, segment_id)
            if subject_type == "customer":
                request = build_external_platform_client_reminder_request(
                    recipient,
                    case_no=facts.case_no,
                    session_id=facts.session_id,
                    document_version_id=document_id,
                    scheduled_at=scheduled_at,
                    idempotency_key=key,
                    correlation_id=command.correlation_id,
                )
            else:
                if segment_id is None:
                    raise RuntimeError("external_signing_staff_segment_missing")
                request = build_external_platform_reminder_request(
                    recipient,
                    case_no=facts.case_no,
                    session_id=facts.session_id,
                    matching_segment_id=segment_id,
                    document_version_id=document_id,
                    scheduled_at=scheduled_at,
                    idempotency_key=key,
                    correlation_id=command.correlation_id,
                )
            self._delivery_tasks.enqueue(request)

    def _binding(self, subject_type: str, subject_reference: str) -> ContractLineBinding:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT line_user_id,binding_status,subject_type,subject_reference "
                "FROM line_identity_role_bindings WHERE subject_type=%s "
                "AND subject_reference=%s FOR UPDATE",
                (subject_type, subject_reference),
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

    @staticmethod
    def _blocked(code: str, message: str) -> ExternalSigningTypedError:
        return ExternalSigningTypedError(category="domain_blocked", code=code, message=message)


def _derived_key(parent: IdempotencyKey, subject_type: str, segment_id: int | None) -> IdempotencyKey:
    lane = subject_type if segment_id is None else f"{subject_type}:{segment_id}"
    digest = hashlib.sha256(f"{parent.value}:{lane}".encode("utf-8")).hexdigest()
    return IdempotencyKey(f"external-signing-handoff-notification:{digest}")


__all__ = ["MySqlExternalSigningHandoffNotificationPort"]
