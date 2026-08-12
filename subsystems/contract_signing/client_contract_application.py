"""Send and record client contract signatures after staff commitment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Callable

from infrastructure.archive.contract_documents import (
    archive_contract_document,
    discard_uncommitted_contract_document,
)
from infrastructure.mysql.line_delivery_task_repository import (
    MySqlLineDeliveryTaskRepository,
)
from infrastructure.mysql.order_contract_completion_repository import (
    MySqlOrderContractCompletionRepository,
)
from shared_kernel.clock import SystemBusinessClock
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.orders.contract_completion_workflow import (
    ContractCompletionApplyRequest,
    ContractCompletionWorkflow,
)
from domains.orders.contract_completion import ContractCompletionIntent
from subsystems.contract_signing.document_access import (
    create_document_access_credential,
)
from subsystems.contract_signing.line_delivery import (
    ContractLineBinding,
    build_contract_delivery_request,
    require_contract_line_recipient,
)
from subsystems.contract_signing.template_catalog import (
    TEMPLATE_DIRECTORY,
    approved_template_mapping_path,
    load_approved_template,
)
from subsystems.contract_signing.contract_renderer import render_contract_template
from subsystems.contract_signing.command_receipts import append_command_receipt, append_outbox_intent


@dataclass(frozen=True, slots=True)
class SendClientContractCommand:
    case_no: str
    actor_id: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId
    download_url: str


@dataclass(frozen=True, slots=True)
class RecordClientSignedReturnCommand:
    case_no: str
    signed_content: bytes
    original_filename: str
    mime_type: str
    actor_id: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId
    expected_document_version_id: int


@dataclass(frozen=True, slots=True)
class ClientContractWorkflowReceipt:
    document_version_id: int
    signing_event_id: int
    line_delivery_task_id: int | None
    contract_identity: str | None
    contract_completed: bool = False


class ClientContractSigningApplication:
    """Owns the client-signature fact but does not complete an Order lifecycle."""

    def __init__(
        self,
        connection_factory: Callable[[], object],
        *,
        archive_root: Path,
        now: Callable[[], datetime],
    ) -> None:
        self._connection_factory = connection_factory
        self._archive_root = archive_root
        self._now = now

    def send(self, command: SendClientContractCommand) -> ClientContractWorkflowReceipt:
        existing = self._existing_receipt(command.idempotency_key)
        if existing is not None:
            return existing
        template = load_approved_template("contract_client_copy")
        return self._persist_sent_contract(command, template)

    def record_signed_return(
        self,
        command: RecordClientSignedReturnCommand,
    ) -> ClientContractWorkflowReceipt:
        existing = self._existing_signed_return_receipt(command)
        if existing is not None:
            return existing
        archive = archive_contract_document(
            command.signed_content,
            storage_root=self._archive_root,
            storage_key=_client_signed_storage_key(command),
        )
        return self._persist_signed_return(command, archive)

    def _existing_signed_return_receipt(
        self, command: RecordClientSignedReturnCommand
    ) -> ClientContractWorkflowReceipt | None:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT event.document_version_id,event.id,event.line_delivery_task_id,order_row.contract_identity,"
                    "asset.sha256,EXISTS(SELECT 1 FROM order_contract_flow_events completion "
                    "WHERE completion.case_no=event.case_no AND completion.event_type='contract_completed') "
                    "AS contract_completed FROM contract_signing_events event "
                    "JOIN contract_document_versions document ON document.id=event.document_version_id "
                    "JOIN media_assets asset ON asset.id=document.media_asset_id "
                    "JOIN orders order_row ON order_row.case_no=event.case_no "
                    "WHERE event.event_key=%s",
                    (command.idempotency_key.value,),
                )
                row = cursor.fetchone()
            if row is None:
                return None
            if str(row["sha256"]) != _sha256(command.signed_content):
                raise ValueError("contract_signature_idempotency_conflict")
            return ClientContractWorkflowReceipt(
                int(row["document_version_id"]), int(row["id"]),
                _optional_integer(row["line_delivery_task_id"]),
                _optional_text(row["contract_identity"]), bool(row["contract_completed"]),
            )
        finally:
            connection.close()

    def _existing_receipt(self, key: IdempotencyKey) -> ClientContractWorkflowReceipt | None:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT event.document_version_id,event.id,event.line_delivery_task_id,order_row.contract_identity,"
                    "EXISTS(SELECT 1 FROM order_contract_flow_events completion "
                    "WHERE completion.case_no=event.case_no AND completion.event_type='contract_completed') "
                    "AS contract_completed "
                    "FROM contract_signing_events event JOIN orders order_row ON order_row.case_no=event.case_no "
                    "WHERE event.event_key=%s",
                    (key.value,),
                )
                row = cursor.fetchone()
            if row is None:
                return None
            return ClientContractWorkflowReceipt(
                int(row["document_version_id"]),
                int(row["id"]),
                _optional_integer(row["line_delivery_task_id"]),
                _optional_text(row["contract_identity"]),
                bool(row["contract_completed"]),
            )
        finally:
            connection.close()

    def _persist_sent_contract(self, command, template):
        connection = self._connection_factory()
        archive = None
        try:
            try:
                connection.begin()
                facts = _client_contract_facts(connection, command.case_no)
                content = render_contract_template(
                    template_path=TEMPLATE_DIRECTORY / template.template_filename,
                    mapping_path=approved_template_mapping_path(template.template_key),
                    facts=_client_template_facts(connection, command.case_no, facts),
                )
                archive = archive_contract_document(
                    content, storage_root=self._archive_root,
                    storage_key=_client_template_storage_key(command),
                )
                binding = _line_binding(connection, "customer", str(facts["client_id"]))
                recipient = require_contract_line_recipient(binding, subject_type="customer", subject_reference=str(facts["client_id"]))
                document_id = _insert_generated_document(connection, command, facts, template, archive)
                grant_id, raw_token = _insert_access_grant(connection, command, document_id, binding, self._now())
                request = build_contract_delivery_request(
                    recipient,
                    case_no=command.case_no,
                    document_version_id=document_id,
                    download_url=_tokenized_download_url(command.download_url, raw_token),
                    audience_label="客戶契約",
                    scheduled_at=self._now(),
                    idempotency_key=command.idempotency_key,
                    correlation_id=command.correlation_id,
                )
                delivery = MySqlLineDeliveryTaskRepository(connection).enqueue(request)
                event_id = _insert_sent_event(connection, command, facts, document_id, int(delivery.task_id.value), grant_id)
                _append_command_outcome(connection, command, "send_client_contract", document_id, event_id, {"line_delivery_task_id": int(delivery.task_id.value)})
            except Exception:
                connection.rollback()
                if archive is not None:
                    discard_uncommitted_contract_document(
                        storage_root=self._archive_root, storage_key=archive.storage_key
                    )
                raise
            connection.commit()
            return ClientContractWorkflowReceipt(document_id, event_id, int(delivery.task_id.value), None)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _persist_signed_return(self, command, archive):
        connection = self._connection_factory()
        try:
            try:
                connection.begin()
                facts = _client_contract_facts(connection, command.case_no)
                source_document_id = _sent_client_document(connection, command.case_no)
                _require_expected_document_version(command.expected_document_version_id, source_document_id)
                document_id = _insert_signed_document(connection, command, facts, source_document_id, archive)
                identity = f"client-contract:{archive.sha256}"
                event_id = _insert_signed_event(connection, command, facts, document_id)
                _complete_contract_in_transaction(connection, command, identity)
                _append_command_outcome(connection, command, "record_client_signed_return", document_id, event_id, {"contract_identity": identity, "contract_completed": True})
            except Exception:
                connection.rollback()
                discard_uncommitted_contract_document(
                    storage_root=self._archive_root, storage_key=archive.storage_key
                )
                raise
            connection.commit()
            return ClientContractWorkflowReceipt(document_id, event_id, None, identity, True)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def _client_template_storage_key(command: SendClientContractCommand) -> str:
    return f"{command.case_no}/client/{command.idempotency_key.value}.xlsx"


def _append_command_outcome(connection, command, command_kind, document_id, event_id, result):
    snapshot = {"document_version_id": document_id, "signing_event_id": event_id, **result}
    append_command_receipt(connection, idempotency_key=command.idempotency_key.value, command_kind=command_kind, case_no=command.case_no, document_version_id=document_id, signing_event_id=event_id, correlation_id=command.correlation_id.value, result_snapshot=snapshot)
    append_outbox_intent(connection, case_no=command.case_no, signing_event_id=event_id, intent_key=command.idempotency_key.value, intent_type=command_kind, payload_snapshot=snapshot)


def _client_signed_storage_key(command: RecordClientSignedReturnCommand) -> str:
    return f"{command.case_no}/client/{command.idempotency_key.value}-signed.xlsx"


def _client_contract_facts(connection, case_no: str) -> dict[str, object]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT order_row.client_id,commitment.matching_plan_id,commitment.id AS commitment_id "
            "FROM orders order_row JOIN precontract_service_commitments commitment "
            "ON commitment.case_no=order_row.case_no WHERE order_row.case_no=%s FOR UPDATE",
            (case_no,),
        )
        row = cursor.fetchone()
    if row is None:
        raise ValueError("staff_commitment_required_before_client_contract")
    return row


def _client_template_facts(connection, case_no: str, facts: dict[str, object]) -> dict[str, object]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT order_row.case_no,order_row.service_days,order_row.service_hours_per_day,"
            "order_row.floor_fee,client.name AS client_name,client.phone,client.address,"
            "client.service_time,client.service_type,client.baby_info,client.notes,"
            "MIN(day_row.service_date) AS committed_service_start_date,"
            "MAX(day_row.service_date) AS committed_service_end_date "
            "FROM orders order_row JOIN clients client ON client.case_no=order_row.case_no "
            "JOIN precontract_service_commitment_days day_row ON day_row.commitment_id=%s "
            "WHERE order_row.case_no=%s FOR UPDATE",
            (facts["commitment_id"], case_no),
        )
        snapshot = cursor.fetchone()
    if snapshot is None:
        raise ValueError("contract_signing_case_facts_not_found")
    return dict(snapshot)


def _line_binding(connection, subject_type: str, subject_reference: str) -> ContractLineBinding:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT line_user_id,binding_status,subject_type,subject_reference "
            "FROM line_identity_bindings WHERE subject_type=%s AND subject_reference=%s",
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


def _insert_generated_document(connection, command, facts, template, archive):
    snapshot = _facts_snapshot(connection, command.case_no, int(facts["commitment_id"]))
    asset_id = _insert_media_asset(connection, command.case_no, archive.storage_key, template.template_filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", archive.file_size, archive.sha256)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,version_number FROM contract_document_versions "
            "WHERE case_no=%s AND document_scope='client_contract' "
            "AND document_target_key='client-contract' ORDER BY version_number DESC LIMIT 1 FOR UPDATE",
            (command.case_no,),
        )
        previous = cursor.fetchone()
        version_number = 1 if previous is None else int(previous["version_number"]) + 1
        replaces_document_version_id = None if previous is None else int(previous["id"])
        cursor.execute(
            "INSERT INTO contract_document_versions (case_no,document_scope,document_role,matching_plan_id,document_target_key,template_key,template_sha256,mapping_sha256,facts_snapshot_sha256,media_asset_id,version_number,replaces_document_version_id,created_by) "
            "VALUES (%s,'client_contract','template_generated',%s,'client-contract',%s,%s,%s,%s,%s,%s,%s,%s)",
            (command.case_no, facts["matching_plan_id"], template.template_key, template.template_sha256, template.mapping_sha256, snapshot, asset_id, version_number, replaces_document_version_id, command.actor_id),
        )
        return int(cursor.lastrowid)


def _facts_snapshot(connection, case_no: str, commitment_id: int) -> str:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT MIN(service_date) AS start_date,MAX(service_date) AS end_date,COUNT(*) AS day_count "
            "FROM precontract_service_commitment_days WHERE commitment_id=%s",
            (commitment_id,),
        )
        dates = cursor.fetchone()
    return _sha256(_canonical_json({"case_no": case_no, **dates}).encode())


def _insert_access_grant(connection, command, document_id, binding, now):
    credential = create_document_access_credential(now=now, ttl=timedelta(days=7))
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO contract_document_access_grants (document_version_id,case_no,recipient_line_user_id,recipient_subject_type,recipient_subject_reference,token_sha256,expires_at,created_by) "
            "VALUES (%s,%s,%s,'customer',%s,%s,%s,%s)",
            (document_id, command.case_no, binding.line_user_id, binding.subject_reference, credential.token_sha256, credential.expires_at.replace(tzinfo=None), command.actor_id),
        )
        return int(cursor.lastrowid), credential.raw_token


def _insert_sent_event(connection, command, facts, document_id, task_id, grant_id):
    payload = _canonical_json({"command": "send_client_contract", "correlation_id": command.correlation_id.value})
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO contract_signing_events (case_no,document_version_id,matching_plan_id,event_type,delivery_channel,line_delivery_task_id,document_access_grant_id,event_key,actor,payload) "
            "VALUES (%s,%s,%s,'sent','line',%s,%s,%s,%s,%s)",
            (command.case_no, document_id, facts["matching_plan_id"], task_id, grant_id, command.idempotency_key.value, command.actor_id, payload),
        )
        return int(cursor.lastrowid)


def _sent_client_document(connection, case_no: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT event.document_version_id FROM contract_signing_events event "
            "JOIN contract_document_versions document ON document.id=event.document_version_id "
            "WHERE event.case_no=%s AND event.event_type='sent' AND document.document_scope='client_contract' "
            "ORDER BY event.id DESC LIMIT 1 FOR UPDATE",
            (case_no,),
        )
        row = cursor.fetchone()
    if row is None:
        raise ValueError("client_contract_not_sent")
    return int(row["document_version_id"])


def _require_expected_document_version(expected_document_version_id: int, current_document_version_id: int) -> None:
    if expected_document_version_id != current_document_version_id:
        raise ValueError("contract_document_version_stale")


def _insert_signed_document(connection, command, facts, source_document_id, archive):
    asset_id = _insert_media_asset(connection, command.case_no, archive.storage_key, command.original_filename, command.mime_type, archive.file_size, archive.sha256)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COALESCE(MAX(version_number),0)+1 AS next_version FROM contract_document_versions "
            "WHERE case_no=%s AND document_scope='client_contract' AND document_target_key='client-contract' FOR UPDATE",
            (command.case_no,),
        )
        version_number = int(cursor.fetchone()["next_version"])
        cursor.execute(
            "INSERT INTO contract_document_versions (case_no,document_scope,document_role,matching_plan_id,document_target_key,source_document_version_id,media_asset_id,version_number,created_by) "
            "VALUES (%s,'client_contract','signed_return',%s,'client-contract',%s,%s,%s,%s)",
            (command.case_no, facts["matching_plan_id"], source_document_id, asset_id, version_number, command.actor_id),
        )
        return int(cursor.lastrowid)


def _insert_signed_event(connection, command, facts, document_id):
    payload = _canonical_json({"command": "record_client_signed_return", "correlation_id": command.correlation_id.value})
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO contract_signing_events (case_no,document_version_id,matching_plan_id,event_type,event_key,actor,payload) "
            "VALUES (%s,%s,%s,'signed_received',%s,%s,%s)",
            (command.case_no, document_id, facts["matching_plan_id"], command.idempotency_key.value, command.actor_id, payload),
        )
        return int(cursor.lastrowid)


class _JoinedTransaction:
    """Lets Orders participate in the signing application's outer transaction."""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self) -> None:
        return None


def _complete_contract_in_transaction(connection, command, identity: str) -> None:
    repository = MySqlOrderContractCompletionRepository(connection)
    repository.record_contract_identity(command.case_no, identity)
    workflow = ContractCompletionWorkflow(
        repository,
        _JoinedTransaction,
        SystemBusinessClock(),
    )
    facts = repository.load_for_apply(command.case_no)
    preview = workflow.preview(command.case_no, ContractCompletionIntent.CONFIRM_COMPLETED)
    workflow.apply(
        ContractCompletionApplyRequest(
            command.case_no,
            ContractCompletionIntent.CONFIRM_COMPLETED,
            ExpectedVersion(facts.order.aggregate_version),
            ExpectedVersion(facts.client_finance.account_version),
            preview.fingerprint,
            command.idempotency_key,
            ActorContext(command.actor_id),
            "client signed returned contract was accepted",
            command.correlation_id,
        )
    )


def _insert_media_asset(connection, case_no, storage_key, filename, mime_type, file_size, digest):
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO media_assets (category,owner_type,owner_id,storage_provider,storage_key,original_filename,mime_type,file_size,sha256) "
            "VALUES ('contract','contract_signing',%s,'local',%s,%s,%s,%s,%s)",
            (case_no, storage_key, filename, mime_type, file_size, digest),
        )
        return int(cursor.lastrowid)


def _tokenized_download_url(base_url: str, raw_token: str) -> str:
    if not base_url.startswith("https://"):
        raise ValueError("contract document download URL must use HTTPS")
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}token={raw_token}"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))


def _optional_integer(value: object) -> int | None:
    return None if value is None else int(value)


def _optional_text(value: object) -> str | None:
    value = str(value).strip() if value is not None else ""
    return value or None
