"""
File: staff_contract_application.py
Description: 建立月嫂契約簽署與簽約前承諾；承諾服務日必須精確符合訂單天數。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Callable

from domains.line.identities import LineDeliveryTaskId
from domains.client_finance.obligation_planning import (
    build_precontract_deposit_candidate,
    precontract_deposit_terms_impact,
)
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.orders.contract_completion_workflow import (
    ContractCompletionClientFinanceCommand,
)
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


def _missing_adapter(*_args, **_kwargs):
    raise RuntimeError("contract_signing_adapter_not_configured")


archive_contract_document = _missing_adapter
discard_uncommitted_contract_document = lambda **_kwargs: None
persist_client_finance_terms_impact = _missing_adapter
load_contract_client_finance_facts = _missing_adapter
select_order = _missing_adapter


@dataclass(frozen=True, slots=True)
class SendStaffContractCommand:
    case_no: str
    matching_segment_id: int
    actor_id: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId
    download_url: str


@dataclass(frozen=True, slots=True)
class RecordStaffSignedReturnCommand:
    case_no: str
    matching_segment_id: int
    signed_content: bytes
    original_filename: str
    mime_type: str
    actor_id: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId
    expected_document_version_id: int


@dataclass(frozen=True, slots=True)
class ManualStaffContractAttestationCommand:
    case_no: str
    matching_segment_id: int
    signed_content: bytes
    original_filename: str
    mime_type: str
    confirmation_method: str
    reason: str
    preview_fingerprint: str
    actor_id: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class StaffContractWorkflowReceipt:
    document_version_id: int
    signing_event_id: int
    line_delivery_task_id: int | None
    commitment_id: int | None


class StaffContractSigningApplication:
    """Owns staff-side contract facts; it never creates execution assignments."""

    def __init__(
        self,
        connection_factory: Callable[[], object],
        *,
        archive_root: Path,
        now: Callable[[], datetime],
        archive_document: Callable[..., object] | None = None,
        discard_document: Callable[..., None] | None = None,
        line_delivery_repository_factory: Callable[[object], object] | None = None,
        order_selector: Callable[..., object] | None = None,
        finance_facts_loader: Callable[..., object] | None = None,
        finance_terms_writer: Callable[..., None] | None = None,
    ) -> None:
        self._connection_factory = connection_factory
        self._archive_root = archive_root
        self._now = now
        self._archive_document = archive_document
        self._discard_document = discard_document
        self._line_delivery_repository_factory = line_delivery_repository_factory
        self._order_selector = order_selector
        self._finance_facts_loader = finance_facts_loader
        self._finance_terms_writer = finance_terms_writer

    def _archive(self, content: bytes, storage_key: str):
        fn = self._archive_document or archive_contract_document
        return fn(content, storage_root=self._archive_root, storage_key=storage_key)

    def _discard(self, storage_key: str) -> None:
        fn = self._discard_document or discard_uncommitted_contract_document
        fn(storage_root=self._archive_root, storage_key=storage_key)

    def _line_delivery_repository(self, connection):
        factory = self._line_delivery_repository_factory or _missing_line_delivery_repository
        return factory(connection)

    def _establish_deposit(self, connection, command, commitment_id: int) -> None:
        _establish_precontract_deposit(
            connection,
            command,
            commitment_id,
            order_selector=self._order_selector,
            facts_loader=self._finance_facts_loader,
            terms_writer=self._finance_terms_writer,
        )

    def _run_in_application_unit_of_work(self, operation: Callable[[object], object]):
        connection = self._connection_factory()
        unit_of_work = connection
        try:
            unit_of_work.begin()
            result = operation(connection)
            unit_of_work.commit()
            return result
        except Exception:
            try:
                unit_of_work.rollback()
            except BaseException:
                pass
            raise
        finally:
            try:
                connection.close()
            except BaseException:
                pass

    def send(self, command: SendStaffContractCommand) -> StaffContractWorkflowReceipt:
        existing = self._existing_receipt(command.idempotency_key)
        if existing is not None:
            return existing
        template = load_approved_template("contract_staff_service")
        return self._persist_sent_contract(command, template)

    def record_signed_return(
        self,
        command: RecordStaffSignedReturnCommand,
    ) -> StaffContractWorkflowReceipt:
        existing = self._existing_signed_return_receipt(command)
        if existing is not None:
            return existing
        archive = self._archive(command.signed_content, _staff_signed_storage_key(command))
        return self._persist_signed_return(command, archive)

    def preview_manual_attestation(
        self,
        *,
        case_no: str,
        matching_segment_id: int,
        confirmation_method: str,
        reason: str,
    ) -> dict[str, object]:
        _require_manual_confirmation(confirmation_method, reason)
        connection = self._connection_factory()
        try:
            snapshot = _manual_staff_snapshot(connection, case_no, matching_segment_id, lock=False)
            _require_manual_staff_snapshot_applicable(snapshot)
            return {
                "case_no": case_no,
                "scope": "staff_segment",
                "matching_segment_id": matching_segment_id,
                "confirmation_method": confirmation_method,
                "preview_fingerprint": _manual_preview_fingerprint(snapshot, confirmation_method, reason),
                "can_apply": True,
                "line_delivery_task_id": None,
            }
        finally:
            connection.close()

    def record_manual_attestation(
        self,
        command: ManualStaffContractAttestationCommand,
    ) -> StaffContractWorkflowReceipt:
        _require_manual_confirmation(command.confirmation_method, command.reason)
        existing = self._existing_signed_return_receipt(command)
        if existing is not None:
            return existing
        signed_archive = self._archive(command.signed_content, _manual_staff_signed_storage_key(command))
        template_archive = None
        try:
            def persist(connection):
                snapshot = _manual_staff_snapshot(
                    connection, command.case_no, command.matching_segment_id, lock=True,
                )
                _require_manual_staff_snapshot_applicable(snapshot)
                expected = _manual_preview_fingerprint(snapshot, command.confirmation_method, command.reason)
                if command.preview_fingerprint != expected:
                    raise ValueError("manual_contract_preview_stale")
                segment = _staff_segment(connection, command.case_no, command.matching_segment_id)
                template = load_approved_template("contract_staff_service")
                content = render_contract_template(
                    template_path=TEMPLATE_DIRECTORY / template.template_filename,
                    mapping_path=approved_template_mapping_path(template.template_key),
                    facts=_staff_template_facts(connection, command.case_no, segment),
                )
                template_archive = self._archive(content, _manual_staff_template_storage_key(command))
                source_document_id = _insert_generated_document(
                    connection, command, segment, template, content, template_archive,
                )
                document_id = _insert_signed_document(
                    connection, command, segment, source_document_id, signed_archive,
                )
                event_id = _insert_signed_event(connection, command, segment, document_id)
                commitment_id = _create_commitment_if_ready(
                    connection, command.case_no, segment["plan_id"], command.actor_id,
                )
                if commitment_id is not None:
                    self._establish_deposit(connection, command, commitment_id)
                _append_command_outcome(
                    connection,
                    command,
                    "record_manual_staff_contract_attestation",
                    document_id,
                    event_id,
                    {"commitment_id": commitment_id, "confirmation_method": command.confirmation_method},
                )
                return StaffContractWorkflowReceipt(document_id, event_id, None, commitment_id)
            return self._run_in_application_unit_of_work(persist)
        except Exception:
            if template_archive is not None:
                self._discard(template_archive.storage_key)
            self._discard(signed_archive.storage_key)
            raise

    def _existing_signed_return_receipt(
        self, command: RecordStaffSignedReturnCommand
    ) -> StaffContractWorkflowReceipt | None:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT event.document_version_id,event.id,event.line_delivery_task_id,asset.sha256 "
                    "FROM contract_signing_events event "
                    "JOIN contract_document_versions document ON document.id=event.document_version_id "
                    "JOIN media_assets asset ON asset.id=document.media_asset_id "
                    "WHERE event.event_key=%s",
                    (command.idempotency_key.value,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                if str(row["sha256"]) != _sha256(command.signed_content):
                    raise ValueError("contract_signature_idempotency_conflict")
                return StaffContractWorkflowReceipt(
                    int(row["document_version_id"]), int(row["id"]),
                    _optional_integer(row["line_delivery_task_id"]),
                    _commitment_id(cursor, int(row["document_version_id"])),
                )
        finally:
            connection.close()

    def _existing_receipt(self, key: IdempotencyKey) -> StaffContractWorkflowReceipt | None:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT document_version_id,id,line_delivery_task_id FROM contract_signing_events "
                    "WHERE event_key=%s",
                    (key.value,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                return StaffContractWorkflowReceipt(
                    int(row["document_version_id"]),
                    int(row["id"]),
                    _optional_integer(row["line_delivery_task_id"]),
                    _commitment_id(cursor, int(row["document_version_id"])),
                )
        finally:
            connection.close()

    def _persist_sent_contract(self, command, template):
        archive = None
        try:
            def persist(connection):
                nonlocal archive
                segment = _staff_segment(connection, command.case_no, command.matching_segment_id)
                content = render_contract_template(
                    template_path=TEMPLATE_DIRECTORY / template.template_filename,
                    mapping_path=approved_template_mapping_path(template.template_key),
                    facts=_staff_template_facts(connection, command.case_no, segment),
                )
                archive = self._archive(content, _staff_template_storage_key(command))
                binding = _line_binding(connection, "staff", str(segment["staff_id"]))
                recipient = require_contract_line_recipient(binding, subject_type="staff", subject_reference=str(segment["staff_id"]))
                document_id = _insert_generated_document(connection, command, segment, template, content, archive)
                grant_id, raw_token = _insert_access_grant(
                    connection,
                    command,
                    document_id,
                    binding,
                    now=self._now(),
                )
                request = build_contract_delivery_request(
                    recipient,
                    case_no=command.case_no,
                    document_version_id=document_id,
                    download_url=_tokenized_download_url(command.download_url, raw_token),
                    audience_label="服務人員契約",
                    scheduled_at=self._now(),
                    idempotency_key=command.idempotency_key,
                    correlation_id=command.correlation_id,
                )
                delivery = self._line_delivery_repository(connection).enqueue(request)
                event_id = _insert_sent_event(connection, command, segment, document_id, int(delivery.task_id.value), grant_id)
                _append_command_outcome(connection, command, "send_staff_contract", document_id, event_id, {"line_delivery_task_id": int(delivery.task_id.value)})
                return StaffContractWorkflowReceipt(document_id, event_id, int(delivery.task_id.value), None)
            return self._run_in_application_unit_of_work(persist)
        except Exception:
            if archive is not None:
                self._discard(archive.storage_key)
            raise

    def _persist_signed_return(self, command, archive):
        try:
            def persist(connection):
                segment = _staff_segment(connection, command.case_no, command.matching_segment_id)
                source_document_id = _sent_staff_document(connection, command.case_no, command.matching_segment_id)
                _require_expected_document_version(command.expected_document_version_id, source_document_id)
                document_id = _insert_signed_document(connection, command, segment, source_document_id, archive)
                event_id = _insert_signed_event(connection, command, segment, document_id)
                commitment_id = _create_commitment_if_ready(connection, command.case_no, segment["plan_id"], command.actor_id)
                if commitment_id is not None:
                    self._establish_deposit(
                        connection,
                        command,
                        commitment_id,
                    )
                _append_command_outcome(connection, command, "record_staff_signed_return", document_id, event_id, {"commitment_id": commitment_id})
                return StaffContractWorkflowReceipt(document_id, event_id, None, commitment_id)
            return self._run_in_application_unit_of_work(persist)
        except Exception:
            self._discard(archive.storage_key)
            raise


def _staff_template_storage_key(command: SendStaffContractCommand) -> str:
    return f"{command.case_no}/staff/{command.matching_segment_id}/{command.idempotency_key.value}.xlsx"


def _append_command_outcome(connection, command, command_kind, document_id, event_id, result):
    snapshot = {"document_version_id": document_id, "signing_event_id": event_id, **result}
    append_command_receipt(connection, idempotency_key=command.idempotency_key.value, command_kind=command_kind, case_no=command.case_no, document_version_id=document_id, signing_event_id=event_id, correlation_id=command.correlation_id.value, result_snapshot=snapshot)
    append_outbox_intent(connection, case_no=command.case_no, signing_event_id=event_id, intent_key=command.idempotency_key.value, intent_type=command_kind, payload_snapshot=snapshot)


def _staff_signed_storage_key(command: RecordStaffSignedReturnCommand) -> str:
    return f"{command.case_no}/staff/{command.matching_segment_id}/{command.idempotency_key.value}-signed.xlsx"


def _manual_staff_template_storage_key(command: ManualStaffContractAttestationCommand) -> str:
    return f"{command.case_no}/staff/{command.matching_segment_id}/{command.idempotency_key.value}-manual-template.xlsx"


def _manual_staff_signed_storage_key(command: ManualStaffContractAttestationCommand) -> str:
    return f"{command.case_no}/staff/{command.matching_segment_id}/{command.idempotency_key.value}-manual-signed.xlsx"


def _staff_segment(connection, case_no: str, segment_id: int) -> dict[str, object]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT segment.id,segment.plan_id,segment.staff_id,segment.assigned_start_date,"
            "segment.assigned_end_date FROM caregiver_matching_plan_segments segment "
            "JOIN caregiver_matching_plans plan ON plan.id=segment.plan_id "
            "WHERE segment.id=%s AND plan.case_no=%s FOR UPDATE",
            (segment_id, case_no),
        )
        row = cursor.fetchone()
    if row is None:
        raise ValueError("contract_signing_segment_not_found")
    return row


def _staff_template_facts(connection, case_no: str, segment: dict[str, object]) -> dict[str, object]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT order_row.case_no,order_row.start_date,order_row.end_date,order_row.service_days,"
            "client.name AS client_name,client.city,client.address,client.service_time,client.service_type,"
            "staff.name AS staff_name,staff.phone AS staff_phone "
            "FROM orders order_row JOIN clients client ON client.case_no=order_row.case_no "
            "JOIN staff ON staff.id=%s WHERE order_row.case_no=%s FOR UPDATE",
            (segment["staff_id"], case_no),
        )
        facts = cursor.fetchone()
    if facts is None:
        raise ValueError("contract_signing_case_facts_not_found")
    return dict(facts)


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


def _insert_generated_document(connection, command, segment, template, content, archive) -> int:
    target_key = f"staff-segment:{segment['id']}"
    snapshot = _sha256(_canonical_json({"case_no": command.case_no, "segment_id": segment["id"], "staff_id": segment["staff_id"]}).encode())
    asset_id = _insert_media_asset(connection, command.case_no, archive.storage_key, template.template_filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", archive.file_size, archive.sha256)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,version_number FROM contract_document_versions "
            "WHERE case_no=%s AND document_scope='staff_segment' AND document_target_key=%s "
            "ORDER BY version_number DESC LIMIT 1 FOR UPDATE",
            (command.case_no, target_key),
        )
        previous = cursor.fetchone()
        version_number = 1 if previous is None else int(previous["version_number"]) + 1
        replaces_document_version_id = None if previous is None else int(previous["id"])
        cursor.execute(
            "INSERT INTO contract_document_versions (case_no,document_scope,document_role,matching_plan_id,matching_segment_id,document_target_key,template_key,template_sha256,mapping_sha256,facts_snapshot_sha256,media_asset_id,version_number,replaces_document_version_id,created_by) "
            "VALUES (%s,'staff_segment','template_generated',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (command.case_no, segment["plan_id"], segment["id"], target_key, template.template_key, template.template_sha256, template.mapping_sha256, snapshot, asset_id, version_number, replaces_document_version_id, command.actor_id),
        )
        return int(cursor.lastrowid)


def _insert_access_grant(connection, command, document_id, binding, *, now):
    credential = create_document_access_credential(now=now, ttl=timedelta(days=7))
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO contract_document_access_grants (document_version_id,case_no,recipient_line_user_id,recipient_subject_type,recipient_subject_reference,token_sha256,expires_at,created_by) "
            "VALUES (%s,%s,%s,'staff',%s,%s,%s,%s)",
            (document_id, command.case_no, binding.line_user_id, binding.subject_reference, credential.token_sha256, credential.expires_at.replace(tzinfo=None), command.actor_id),
        )
        return int(cursor.lastrowid), credential.raw_token


def _insert_sent_event(connection, command, segment, document_id, task_id, grant_id):
    payload = _canonical_json({"command": "send_staff_contract", "correlation_id": command.correlation_id.value})
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO contract_signing_events (case_no,document_version_id,matching_plan_id,matching_segment_id,event_type,delivery_channel,line_delivery_task_id,document_access_grant_id,event_key,actor,payload) "
            "VALUES (%s,%s,%s,%s,'sent','line',%s,%s,%s,%s,%s)",
            (command.case_no, document_id, segment["plan_id"], segment["id"], task_id, grant_id, command.idempotency_key.value, command.actor_id, payload),
        )
        return int(cursor.lastrowid)


def _sent_staff_document(connection, case_no: str, segment_id: int) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT document_version_id FROM contract_signing_events WHERE case_no=%s "
            "AND matching_segment_id=%s AND event_type='sent' ORDER BY id DESC LIMIT 1 FOR UPDATE",
            (case_no, segment_id),
        )
        row = cursor.fetchone()
    if row is None:
        raise ValueError("staff_contract_not_sent")
    return int(row["document_version_id"])


def _require_expected_document_version(expected_document_version_id: int, current_document_version_id: int) -> None:
    if expected_document_version_id != current_document_version_id:
        raise ValueError("contract_document_version_stale")


def _insert_signed_document(connection, command, segment, source_document_id, archive) -> int:
    asset_id = _insert_media_asset(connection, command.case_no, archive.storage_key, command.original_filename, command.mime_type, archive.file_size, archive.sha256)
    target_key = f"staff-segment:{segment['id']}"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COALESCE(MAX(version_number),0)+1 AS next_version FROM contract_document_versions "
            "WHERE case_no=%s AND document_scope='staff_segment' AND document_target_key=%s FOR UPDATE",
            (command.case_no, target_key),
        )
        version_number = int(cursor.fetchone()["next_version"])
        cursor.execute(
            "INSERT INTO contract_document_versions (case_no,document_scope,document_role,matching_plan_id,matching_segment_id,document_target_key,source_document_version_id,media_asset_id,version_number,created_by) "
            "VALUES (%s,'staff_segment','signed_return',%s,%s,%s,%s,%s,%s,%s)",
            (command.case_no, segment["plan_id"], segment["id"], target_key, source_document_id, asset_id, version_number, command.actor_id),
        )
        return int(cursor.lastrowid)


def _insert_signed_event(connection, command, segment, document_id):
    payload_data = {"command": "record_staff_signed_return", "correlation_id": command.correlation_id.value}
    if isinstance(command, ManualStaffContractAttestationCommand):
        payload_data = {
            "command": "record_manual_staff_contract_attestation",
            "confirmation_method": command.confirmation_method,
            "reason": command.reason,
            "correlation_id": command.correlation_id.value,
        }
    payload = _canonical_json(payload_data)
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO contract_signing_events (case_no,document_version_id,matching_plan_id,matching_segment_id,event_type,event_key,actor,payload) "
            "VALUES (%s,%s,%s,%s,'signed_received',%s,%s,%s)",
            (command.case_no, document_id, segment["plan_id"], segment["id"], command.idempotency_key.value, command.actor_id, payload),
        )
        return int(cursor.lastrowid)


_MANUAL_CONFIRMATION_METHODS = frozenset({"phone", "paper", "in_person", "verified_other"})


def _require_manual_confirmation(confirmation_method: str, reason: str) -> None:
    if confirmation_method not in _MANUAL_CONFIRMATION_METHODS:
        raise ValueError("manual_contract_confirmation_method_invalid")
    if not reason.strip():
        raise ValueError("manual_contract_reason_missing")


def _manual_staff_snapshot(connection, case_no: str, segment_id: int, *, lock: bool) -> dict[str, object]:
    suffix = " FOR UPDATE" if lock else ""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT segment.id AS segment_id,segment.plan_id,segment.staff_id,plan.version,plan.status,plan.is_active,"
            "COALESCE((SELECT response.response_value FROM matching_response_events response "
            "WHERE response.plan_id=segment.plan_id AND response.response_type='customer_decision' "
            "ORDER BY response.occurred_at_utc DESC,response.id DESC LIMIT 1),'') AS customer_decision,"
            "EXISTS(SELECT 1 FROM contract_signing_events event WHERE event.matching_segment_id=segment.id "
            "AND event.event_type='signed_received') AS already_signed "
            "FROM caregiver_matching_plan_segments segment JOIN caregiver_matching_plans plan ON plan.id=segment.plan_id "
            "WHERE segment.id=%s AND plan.case_no=%s" + suffix,
            (segment_id, case_no),
        )
        snapshot = cursor.fetchone()
    if snapshot is None:
        raise ValueError("contract_signing_segment_not_found")
    return dict(snapshot)


def _require_manual_staff_snapshot_applicable(snapshot: dict[str, object]) -> None:
    status = str(snapshot["status"])
    if status == "accepted":
        pass
    elif status == "proposed" and snapshot["is_active"] == 1:
        if str(snapshot["customer_decision"]) != "accepted":
            raise ValueError("manual_contract_customer_acceptance_required")
    else:
        raise ValueError("manual_contract_plan_not_current")
    if bool(snapshot["already_signed"]):
        raise ValueError("manual_contract_already_signed")


def _manual_preview_fingerprint(snapshot: dict[str, object], confirmation_method: str, reason: str) -> str:
    payload = {
        "scope": "staff_segment",
        "snapshot": snapshot,
        "confirmation_method": confirmation_method,
        "reason": reason.strip(),
    }
    return _sha256(_canonical_json(payload).encode())


def _create_commitment_if_ready(connection, case_no, plan_id, actor_id):
    if _plan_has_unsigned_segment(connection, case_no, plan_id):
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM precontract_service_commitments WHERE matching_plan_id=%s FOR UPDATE", (plan_id,))
        existing = cursor.fetchone()
        if existing is not None:
            return int(existing["id"])
        segments = _plan_segments(connection, plan_id)
        service_days = _commitment_service_days(connection, case_no, segments)
        snapshot = _sha256(_canonical_json(segments).encode())
        key = f"precontract-commitment:{case_no}:{plan_id}:{snapshot[:16]}"
        cursor.execute(
            "INSERT INTO precontract_service_commitments (case_no,matching_plan_id,commitment_key,plan_snapshot_sha256,created_by) VALUES (%s,%s,%s,%s,%s)",
            (case_no, plan_id, key, snapshot, actor_id),
        )
        commitment_id = int(cursor.lastrowid)
        for segment, service_date in service_days:
            cursor.execute(
                "INSERT INTO precontract_service_commitment_days (commitment_id,matching_segment_id,staff_id,service_date) VALUES (%s,%s,%s,%s)",
                (commitment_id, segment["id"], segment["staff_id"], service_date),
            )
        return commitment_id


def _establish_precontract_deposit(
    connection,
    command,
    commitment_id: int,
    *,
    order_selector: Callable[..., object] | None = None,
    facts_loader: Callable[..., object] | None = None,
    terms_writer: Callable[..., None] | None = None,
) -> None:
    with connection.cursor() as cursor:
        selector = order_selector or select_order
        order = selector(cursor, command.case_no, lock=True)
        loader = facts_loader or load_contract_client_finance_facts
        facts = loader(cursor, order, lock=True)
        candidate = build_precontract_deposit_candidate(
            facts,
            f"precontract-commitment:{commitment_id}",
        )
        if not candidate.mutates:
            return
        writer = terms_writer or persist_client_finance_terms_impact
        writer(
            cursor,
            ContractCompletionClientFinanceCommand(
                precontract_deposit_terms_impact(candidate),
                command.idempotency_key,
                ActorContext(command.actor_id),
                "all staff contract signatures were received",
                command.correlation_id,
                "precontract-commitment",
                commitment_id,
            ),
        )


def _missing_line_delivery_repository(_connection):
    raise RuntimeError("line_delivery_adapter_not_configured")


def _plan_has_unsigned_segment(connection, case_no, plan_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS count FROM caregiver_matching_plan_segments segment "
            "WHERE segment.plan_id=%s AND NOT EXISTS (SELECT 1 FROM contract_signing_events event "
            "WHERE event.case_no=%s AND event.matching_segment_id=segment.id "
            "AND event.event_type='signed_received')",
            (plan_id, case_no),
        )
        return int(cursor.fetchone()["count"]) > 0


def _plan_segments(connection, plan_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,staff_id,assigned_start_date,assigned_end_date FROM caregiver_matching_plan_segments "
            "WHERE plan_id=%s ORDER BY segment_order,id FOR UPDATE",
            (plan_id,),
        )
        return list(cursor.fetchall())


def _commitment_service_days(connection, case_no, segments):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT order_row.start_date,order_row.service_days,client.service_type "
            "FROM orders order_row JOIN clients client ON client.id=order_row.client_id "
            "WHERE order_row.case_no=%s FOR UPDATE",
            (case_no,),
        )
        terms = cursor.fetchone()
        cursor.execute("SELECT holiday_date FROM holidays")
        holiday_dates = {row["holiday_date"] for row in cursor.fetchall()}
    if terms is None:
        raise ValueError("contract_signing_case_facts_not_found")
    return _allocate_commitment_service_days(terms, segments, holiday_dates)


def _allocate_commitment_service_days(terms, segments, holiday_dates):
    start_date = terms["start_date"]
    target_days = int(terms["service_days"] or 0)
    if start_date is None or target_days <= 0:
        raise ValueError("precontract_service_dates_incomplete")
    rest_weekdays = _rest_weekdays(terms["service_type"])
    planned_dates = _planned_service_dates(start_date, target_days, rest_weekdays, holiday_dates)
    allocations = []
    for service_date in planned_dates:
        owners = [
            segment for segment in segments
            if segment["assigned_start_date"] <= service_date <= segment["assigned_end_date"]
        ]
        if len(owners) != 1:
            raise ValueError("precontract_service_days_mismatch")
        allocations.append((owners[0], service_date))
    if len(allocations) != target_days:
        raise ValueError("precontract_service_days_mismatch")
    return tuple(allocations)


def _rest_weekdays(service_mode):
    if service_mode == "週休1日":
        return frozenset({6})
    if service_mode == "週休2日":
        return frozenset({5, 6})
    if service_mode == "連續服務":
        return frozenset()
    raise ValueError("precontract_service_mode_invalid")


def _planned_service_dates(start_date, target_days, rest_weekdays, holiday_dates):
    dates = []
    current = start_date
    while len(dates) < target_days:
        if current.weekday() not in rest_weekdays and current not in holiday_dates:
            dates.append(current)
        current += timedelta(days=1)
    return tuple(dates)


def _inclusive_dates(start, end):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _insert_media_asset(connection, case_no, storage_key, filename, mime_type, file_size, digest):
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO media_assets (category,owner_type,owner_id,storage_provider,storage_key,original_filename,mime_type,file_size,sha256) "
            "VALUES ('contract','contract_signing',%s,'local',%s,%s,%s,%s,%s)",
            (case_no, storage_key, filename, mime_type, file_size, digest),
        )
        return int(cursor.lastrowid)


def _commitment_id(cursor, document_id):
    cursor.execute(
        "SELECT commitment.id FROM precontract_service_commitments commitment "
        "JOIN contract_document_versions document ON document.matching_plan_id=commitment.matching_plan_id "
        "WHERE document.id=%s",
        (document_id,),
    )
    row = cursor.fetchone()
    return None if row is None else int(row["id"])


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
