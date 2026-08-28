"""
File: contract_external_signing_repository.py
Description: 在 caller-owned MySQL 交易鎖定並保存外部簽約回報、recovery 與 closed receipt。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
from typing import Any
import uuid

from domains.contract_signing.external_signing import (
    ExternalSigningSessionFacts,
    ExternalSigningState,
    ExternalSigningTransition,
    StaffSigningReportTarget,
    derive_external_signing_session_id,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.contract_signing.external_signing_contracts import (
    ExternalCompletionReportScope,
    ExternalReportCommandType,
    ExternalSigningReportCommand,
    ExternalSigningReportReceipt,
    ExternalSigningTypedError,
    LegacyManualRecoverySnapshot,
    LegacyManualSigningEvidence,
    ManualAttestationMethod,
    RecordExternalClientSigningReport,
    RecordExternalStaffSigningReport,
    RecordManualExternalClientSigningReport,
    RecordManualExternalStaffSigningReport,
    StoredExternalSigningReportReceipt,
    VerifiedReporterBindingSnapshot,
)
from subsystems.contract_signing.external_signing_workflow import (
    PersistedExternalReport,
    StaffCompletionPrerequisites,
)
from subsystems.contract_signing.final_document_workflow import (
    FinalContractDocumentReadback,
    FinalSignedContractApplyReceipt,
    StoredFinalSignedContractReceipt,
)
from subsystems.controlled_files.workflow import ControlledFileApplyReceipt


class MySqlContractExternalSigningRepository:
    """Borrowed-connection adapter; it never commits, rolls back, or closes."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_session(
        self, session_id: str, *, for_update: bool
    ) -> ExternalSigningSessionFacts | None:
        suffix = _lock_suffix(for_update)
        session = self._one(_SESSION_SELECT_SQL + suffix, (session_id,))
        if session is None:
            return None
        self._require_one(_ORDER_SELECT_SQL + suffix, (session["case_no"],))
        self._require_one(
            _PLAN_SELECT_SQL + suffix,
            (session["matching_plan_id"], session["case_no"]),
        )
        segments = self._all(
            _SEGMENTS_SELECT_SQL + suffix,
            (session["matching_plan_id"],),
        )
        if not segments:
            raise RuntimeError("external_signing_staff_targets_missing")
        commitment = self._one(
            _COMMITMENT_BY_PLAN_SELECT_SQL + suffix,
            (session["matching_plan_id"],),
        )
        if session["commitment_id"] is not None and (
            commitment is None or int(commitment["id"]) != int(session["commitment_id"])
        ):
            raise RuntimeError("external_signing_commitment_stale")
        documents = self._all(
            _STAFF_DOCUMENTS_SELECT_SQL + suffix,
            (session["case_no"], session["matching_plan_id"]),
        )
        document_by_segment = {
            int(row["segment_id"]): int(row["document_version_id"])
            for row in documents
        }
        if any(int(row["segment_id"]) not in document_by_segment for row in segments):
            raise RuntimeError("external_signing_current_staff_documents_missing")
        client = self._require_one(
            _CLIENT_DOCUMENT_SELECT_SQL + suffix,
            (session["case_no"], session["matching_plan_id"]),
        )
        current_document_set = _document_set_fingerprint(
            str(session["case_no"]),
            int(session["matching_plan_id"]),
            segments,
            document_by_segment,
            int(client["document_version_id"]),
        )
        if current_document_set != str(session["current_document_set_sha256"]):
            raise RuntimeError("external_signing_document_set_stale")
        reports = self._all(_REPORT_TARGETS_SELECT_SQL + suffix, (session["id"],))
        staff_reported = tuple(
            sorted(
                int(row["matching_segment_id"])
                for row in reports
                if str(row["report_scope"]) == "staff"
            )
        )
        return ExternalSigningSessionFacts(
            session_id=str(session["external_signing_session_id"]),
            case_no=str(session["case_no"]),
            matching_plan_id=int(session["matching_plan_id"]),
            document_set_fingerprint=str(session["current_document_set_sha256"]),
            staff_targets=tuple(
                StaffSigningReportTarget(
                    int(row["segment_id"]),
                    str(row["staff_id"]),
                    document_by_segment[int(row["segment_id"])],
                )
                for row in segments
            ),
            reported_staff_segment_ids=staff_reported,
            client_subject_reference=str(client["client_id"]),
            client_document_version_id=int(client["document_version_id"]),
            commitment_id=_optional_int(session["commitment_id"]),
            client_reported=any(
                str(row["report_scope"]) == "client" for row in reports
            ),
            state=ExternalSigningState(str(session["session_state"])),
            status_version=int(session["aggregate_version"]),
        )

    def load_active_session_by_case(
        self, case_no: str, *, for_update: bool
    ) -> ExternalSigningSessionFacts | None:
        row = self._one(
            _ACTIVE_SESSION_BY_CASE_SQL + _lock_suffix(for_update), (case_no,)
        )
        if row is None:
            return None
        return self.load_session(
            str(row["external_signing_session_id"]), for_update=for_update
        )

    def derive_current_session(
        self, case_no: str, *, for_update: bool
    ) -> ExternalSigningSessionFacts | None:
        suffix = _lock_suffix(for_update)
        order = self._one(_CURRENT_ORDER_SQL + suffix, (case_no,))
        if order is None:
            return None
        plan = self._one(_CURRENT_ACCEPTED_PLAN_SQL + suffix, (case_no,))
        if plan is None:
            return None
        segments = self._all(_SEGMENTS_SELECT_SQL + suffix, (plan["id"],))
        self._one(_COMMITMENT_BY_PLAN_SELECT_SQL + suffix, (plan["id"],))
        documents = self._all(
            _STAFF_DOCUMENTS_SELECT_SQL + suffix, (case_no, plan["id"])
        )
        document_by_segment = {
            int(row["segment_id"]): int(row["document_version_id"])
            for row in documents
        }
        if not segments or any(
            int(row["segment_id"]) not in document_by_segment for row in segments
        ):
            return None
        client = self._one(
            _CLIENT_DOCUMENT_SELECT_SQL + suffix, (case_no, plan["id"])
        )
        if client is None:
            return None
        document_set = _document_set_fingerprint(
            case_no,
            int(plan["id"]),
            segments,
            document_by_segment,
            int(client["document_version_id"]),
        )
        return ExternalSigningSessionFacts(
            derive_external_signing_session_id(case_no, int(plan["id"]), document_set),
            case_no,
            int(plan["id"]),
            document_set,
            tuple(
                StaffSigningReportTarget(
                    int(row["segment_id"]),
                    str(row["staff_id"]),
                    document_by_segment[int(row["segment_id"])],
                )
                for row in segments
            ),
            (),
            str(order["client_id"]),
            int(client["document_version_id"]),
            None,
            False,
            ExternalSigningState.STAFF_REPORTING,
            0,
        )

    def load_legacy_manual_signing_evidence(
        self, case_no: str, *, for_update: bool
    ) -> tuple[LegacyManualSigningEvidence, ...]:
        rows = self._all(_LEGACY_MANUAL_EVIDENCE_SQL + _lock_suffix(for_update), (case_no,))
        return tuple(_legacy_manual_evidence(row, case_no) for row in rows)

    def activate_session(
        self, facts: ExternalSigningSessionFacts, *, actor_id: str
    ) -> None:
        self._insert(
            _SESSION_ACTIVATE_SQL,
            (
                facts.session_id,
                facts.case_no,
                facts.matching_plan_id,
                facts.document_set_fingerprint,
                actor_id,
            ),
        )

    def find_receipt(
        self, key: IdempotencyKey, *, for_update: bool
    ) -> StoredExternalSigningReportReceipt | None:
        row = self._one(_RECEIPT_BY_KEY_SQL + _lock_suffix(for_update), (key.value,))
        return None if row is None else _stored_receipt(row)

    def find_source_receipt(
        self, source_event_identity: str, *, for_update: bool
    ) -> StoredExternalSigningReportReceipt | None:
        row = self._one(
            _RECEIPT_BY_SOURCE_SQL + _lock_suffix(for_update),
            (source_event_identity,),
        )
        return None if row is None else _stored_receipt(row)

    def load_final_session(
        self,
        case_no: str,
        session_id: str,
        *,
        for_update: bool,
    ) -> ExternalSigningSessionFacts | None:
        session = self.load_session(session_id, for_update=for_update)
        if session is None or session.case_no != case_no:
            return None
        return session

    def find_final_receipt(
        self, key: IdempotencyKey, *, for_update: bool
    ) -> StoredFinalSignedContractReceipt | None:
        row = self._one(
            _FINAL_RECEIPT_SELECT_SQL + _lock_suffix(for_update),
            (key.value,),
        )
        return None if row is None else _stored_final_receipt(row)

    def reporter_binding_is_current(
        self, snapshot: VerifiedReporterBindingSnapshot, *, for_update: bool
    ) -> bool:
        row = self._one(
            _BINDING_SELECT_SQL + _lock_suffix(for_update),
            (snapshot.line_user_id,),
        )
        return row is not None and (
            str(row["binding_status"]) == "bound"
            and str(row["subject_type"]) == snapshot.subject_type.value
            and str(row["subject_reference"]) == snapshot.subject_reference
            and int(row["aggregate_version"]) == snapshot.aggregate_version.value
        )

    def append_report(
        self,
        command: ExternalSigningReportCommand,
        transition: ExternalSigningTransition,
        command_fingerprint: PreviewFingerprint,
        commitment_id: int | None,
    ) -> PersistedExternalReport:
        session = self._require_one(_SESSION_INTERNAL_SELECT_SQL, (command.session_id,))
        manual = isinstance(
            command,
            (RecordManualExternalStaffSigningReport, RecordManualExternalClientSigningReport),
        )
        inbox = None
        if not manual:
            inbox = self._require_one(_INBOX_SELECT_SQL, (command.source_event_identity,))
            _require_inbox_matches(command, inbox)
        report_id = f"cer_{uuid.uuid4().hex}"
        staff = isinstance(
            command,
            (RecordExternalStaffSigningReport, RecordManualExternalStaffSigningReport),
        )
        binding = None if manual else command.reporter_binding
        attestation = command.attestation if manual else None
        parameters = (
            report_id,
            int(session["id"]),
            command.case_no,
            "staff" if staff else "client",
            command.matching_segment_id if staff else None,
            command.expected_document_version_id,
            None if staff else commitment_id,
            "staff" if staff else "customer",
            (
                command.attested_subject_reference
                if manual
                else command.reporter_binding.subject_reference
            ),
            "manual_attested" if manual else "verified_line",
            command.source_event_identity,
            command.source_payload_sha256,
            None if inbox is None else int(inbox["id"]),
            None if binding is None else binding.line_user_id,
            None if binding is None else binding.aggregate_version.value,
            None if attestation is None else attestation.method.value,
            None if attestation is None else attestation.reason,
            None if attestation is None else attestation.evidence_reference,
            None if attestation is None else attestation.evidence_sha256,
            command.idempotency_key.value,
            command_fingerprint.value,
            command.expected_status_version.value,
            transition.resulting_status_version,
            _mysql_utc(command.occurred_at),
            command.actor.actor_id,
        )
        database_id = self._insert(_REPORT_INSERT_SQL, parameters)
        return PersistedExternalReport(report_id, database_id)

    def create_final_pdf_recovery(
        self,
        command: RecordExternalClientSigningReport,
        report: PersistedExternalReport,
        command_fingerprint: PreviewFingerprint,
    ) -> None:
        session = self._require_one(_SESSION_INTERNAL_SELECT_SQL, (command.session_id,))
        recovery_id = f"cfrt_{uuid.uuid4().hex}"
        recovery_key = f"final-pdf-recovery:{command_fingerprint.value}"
        self._insert(
            _RECOVERY_INSERT_SQL,
            (
                recovery_id,
                int(session["id"]),
                report.database_id,
                recovery_key,
                command_fingerprint.value,
                command.actor.actor_id,
            ),
        )

    def advance_session(
        self,
        command: ExternalSigningReportCommand,
        transition: ExternalSigningTransition,
        prerequisites: StaffCompletionPrerequisites | None,
    ) -> None:
        commitment_id = None if prerequisites is None else prerequisites.commitment_id
        reminder_id = (
            None if prerequisites is None else prerequisites.client_reminder_task_id
        )
        with self._connection.cursor() as cursor:
            cursor.execute(
                _SESSION_ADVANCE_SQL,
                (
                    transition.after_state.value,
                    commitment_id,
                    reminder_id,
                    transition.resulting_status_version,
                    command.session_id,
                    command.expected_status_version.value,
                ),
            )
            if cursor.rowcount != 1:
                raise _conflict("external_signing_status_version_stale", "session 版本已變更。")

    def save_receipt(
        self,
        key: IdempotencyKey,
        stored: StoredExternalSigningReportReceipt,
        command: ExternalSigningReportCommand,
        report: PersistedExternalReport,
    ) -> None:
        session = self._require_one(_SESSION_INTERNAL_SELECT_SQL, (command.session_id,))
        receipt_id = _receipt_id(key)
        snapshot = _receipt_snapshot(stored.receipt)
        if stored.recovery is not None:
            snapshot["recovery"] = stored.recovery.persisted_payload()
        self._insert(
            _RECEIPT_INSERT_SQL,
            (
                receipt_id,
                int(session["id"]),
                _database_command_type(stored.receipt.command_type),
                "contract-external-signing-receipt.v1",
                key.value,
                stored.command_fingerprint.value,
                command.expected_status_version.value,
                stored.receipt.resulting_status_version,
                report.database_id,
                _canonical_json(snapshot),
                command.actor.actor_id,
                command.correlation_id.value,
                _mysql_utc(command.occurred_at),
            ),
        )

    def register_final_document(
        self,
        session: ExternalSigningSessionFacts,
        controlled_file: ControlledFileApplyReceipt,
        *,
        actor: ActorContext,
        contract_identity: str,
        applied_at: datetime,
    ) -> FinalContractDocumentReadback:
        session_row = self._require_one(
            _SESSION_INTERNAL_SELECT_SQL, (session.session_id,)
        )
        file_row = self._require_one(
            _CONTROLLED_FILE_SELECT_SQL, (controlled_file.readback.file_id,)
        )
        _require_controlled_file_matches(session, controlled_file, file_row)
        predecessor = self._one(
            _FINAL_DOCUMENT_PREDECESSOR_SQL, (session.case_no,)
        )
        version = 1 if predecessor is None else int(predecessor["version_number"]) + 1
        final_document_id = f"cfd_{uuid.uuid4().hex}"
        self._insert(
            _FINAL_DOCUMENT_INSERT_SQL,
            (
                final_document_id,
                int(session_row["id"]),
                session.case_no,
                session.document_set_fingerprint,
                int(file_row["id"]),
                version,
                contract_identity,
                int(file_row["size_bytes"]),
                str(file_row["content_sha256"]),
                actor.actor_id,
                _mysql_utc(applied_at),
            ),
        )
        return FinalContractDocumentReadback(
            final_document_id=final_document_id,
            case_no=session.case_no,
            file_id=str(file_row["opaque_object_id"]),
            version=version,
            filename=str(file_row["filename"]),
            mime_type=str(file_row["content_type"]),
            size_bytes=int(file_row["size_bytes"]),
            status="completed",
            applied_at=_aware_utc(applied_at),
        )

    def complete_session_and_recovery(
        self,
        session: ExternalSigningSessionFacts,
        document: FinalContractDocumentReadback,
        *,
        resulting_status_version: int,
        applied_at: datetime,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _RECOVERY_FULFILL_SQL,
                (
                    _mysql_utc(applied_at),
                    session.session_id,
                    document.final_document_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("external_signing_final_recovery_state_conflict")
            cursor.execute(
                _FINAL_SESSION_COMPLETE_SQL,
                (
                    resulting_status_version,
                    session.session_id,
                    session.status_version,
                ),
            )
            if cursor.rowcount != 1:
                raise _conflict(
                    "external_signing_status_version_stale", "session 版本已變更。"
                )

    def save_final_receipt(
        self,
        key: IdempotencyKey,
        stored: StoredFinalSignedContractReceipt,
        correlation_id: CorrelationId,
        *,
        expected_status_version: int,
        applied_at: datetime,
    ) -> None:
        context = self._require_one(
            _FINAL_RECEIPT_CONTEXT_SQL,
            (stored.receipt.document.final_document_id,),
        )
        self._insert(
            _FINAL_RECEIPT_INSERT_SQL,
            (
                stored.receipt.receipt_id,
                int(context["session_database_id"]),
                "apply_final_signed_contract",
                "contract-external-signing-receipt.v1",
                key.value,
                stored.command_fingerprint.value,
                stored.command_fingerprint.value,
                expected_status_version,
                stored.receipt.resulting_status_version,
                int(context["final_document_database_id"]),
                _canonical_json(_final_receipt_snapshot(stored.receipt)),
                str(context["actor_ref"]),
                correlation_id.value,
                _mysql_utc(applied_at),
            ),
        )

    def get_final_document(
        self, case_no: str
    ) -> FinalContractDocumentReadback | None:
        row = self._one(_FINAL_DOCUMENT_READBACK_SQL, (case_no,))
        return None if row is None else _final_document_readback(row)

    def _one(self, statement: str, parameters: tuple[object, ...]):
        with self._connection.cursor() as cursor:
            cursor.execute(statement, parameters)
            return cursor.fetchone()

    def _require_one(self, statement: str, parameters: tuple[object, ...]):
        row = self._one(statement, parameters)
        if not isinstance(row, Mapping):
            raise RuntimeError("external_signing_persistence_fact_missing")
        return row

    def _all(self, statement: str, parameters: tuple[object, ...]):
        with self._connection.cursor() as cursor:
            cursor.execute(statement, parameters)
            return tuple(cursor.fetchall())

    def _insert(self, statement: str, parameters: tuple[object, ...]) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(statement, parameters)
            if cursor.rowcount != 1:
                raise RuntimeError("external_signing_persistence_insert_failed")
            return int(cursor.lastrowid)


def _stored_receipt(row: Mapping[str, object]) -> StoredExternalSigningReportReceipt:
    snapshot = _json_mapping(row.get("result_snapshot"))
    if snapshot is None:
        raise _stored_fact_error("external_signing_receipt_snapshot_invalid")
    if any(
        type(snapshot.get(key)) is not bool
        for key in (
            "client_reminder_intent_created",
            "final_pdf_recovery_task_created",
        )
    ):
        raise _stored_fact_error("external_signing_receipt_snapshot_invalid")
    try:
        receipt = ExternalSigningReportReceipt(
            command_type=ExternalReportCommandType(snapshot["command_type"]),
            report_id=snapshot["report_id"],
            session_id=snapshot["session_id"],
            scope=ExternalCompletionReportScope(snapshot["scope"]),
            matching_segment_id=snapshot.get("matching_segment_id"),
            resulting_status_version=snapshot["resulting_status_version"],
            resulting_state=ExternalSigningState(snapshot["resulting_state"]),
            client_reminder_intent_created=snapshot[
                "client_reminder_intent_created"
            ],
            final_pdf_recovery_task_created=snapshot[
                "final_pdf_recovery_task_created"
            ],
        )
        command_fingerprint = PreviewFingerprint(row["command_fingerprint"])
    except (KeyError, TypeError, ValueError, OverflowError):
        raise _stored_fact_error("external_signing_receipt_snapshot_invalid") from None
    recovery_value = snapshot.get("recovery")
    if recovery_value is None:
        recovery = None
    elif isinstance(recovery_value, Mapping):
        recovery = _legacy_recovery_snapshot(recovery_value)
    else:
        raise _stored_fact_error("external_signing_recovery_snapshot_invalid")
    try:
        return StoredExternalSigningReportReceipt(
            command_fingerprint, receipt, recovery
        )
    except (TypeError, ValueError):
        raise _stored_fact_error(
            "external_signing_recovery_snapshot_lineage_invalid"
        ) from None


def _legacy_manual_evidence(
    row: Mapping[str, object], case_no: str
) -> LegacyManualSigningEvidence:
    payload = _json_mapping(row.get("payload"))
    result = _json_mapping(row.get("result_snapshot"))
    document_scope = row.get("document_scope")
    if document_scope == "staff_segment":
        scope = ExternalCompletionReportScope.STAFF
    elif document_scope == "client_contract":
        scope = ExternalCompletionReportScope.CLIENT
    else:
        raise ExternalSigningTypedError(
            category="conflict",
            code="contract_legacy_manual_recovery_evidence_malformed",
            message="歷史人工簽回證據不完整。",
        )
    expected_command = (
        "record_manual_staff_contract_attestation"
        if scope is ExternalCompletionReportScope.STAFF
        else "record_manual_client_contract_attestation"
    )
    valid = (
        row.get("event_case_no") == case_no
        and row.get("document_case_no") == case_no
        and row.get("receipt_case_no") == case_no
        and row.get("event_type") == "signed_received"
        and row.get("document_role") == "signed_return"
        and row.get("event_plan_id") == row.get("document_plan_id")
        and row.get("event_segment_id") == row.get("document_segment_id")
        and row.get("receipt_document_id") == row.get("document_version_id")
        and row.get("receipt_event_id") == row.get("event_id")
        and row.get("idempotency_key") == row.get("event_key")
        and row.get("command_kind") == expected_command
        and payload is not None
        and payload.get("command") == expected_command
        and payload.get("correlation_id") == row.get("correlation_id")
        and payload.get("confirmation_method")
        in {item.value for item in ManualAttestationMethod}
        and isinstance(payload.get("reason"), str)
        and bool(str(payload.get("reason")).strip())
        and result is not None
        and result.get("document_version_id") == row.get("document_version_id")
        and result.get("signing_event_id") == row.get("event_id")
        and all(
            type(row.get(key)) is int and row[key] > 0
            for key in (
                "event_plan_id",
                "document_version_id",
                "source_document_version_id",
                "event_id",
                "receipt_db_id",
            )
        )
        and all(
            isinstance(row.get(key), str) and row[key] == row[key].strip() and bool(row[key])
            for key in ("event_key", "command_kind", "actor", "correlation_id")
        )
        and _is_sha256(row.get("media_sha256"))
    )
    if not valid:
        raise ExternalSigningTypedError(
            category="conflict",
            code="contract_legacy_manual_recovery_evidence_malformed",
            message="歷史人工簽回證據不完整。",
        )
    try:
        return LegacyManualSigningEvidence(
            case_no=case_no,
            scope=scope,
            matching_plan_id=row["event_plan_id"],
            matching_segment_id=row.get("event_segment_id"),
            legacy_document_version_id=row["document_version_id"],
            source_document_version_id=row["source_document_version_id"],
            signing_event_id=row["event_id"],
            command_receipt_id=row["receipt_db_id"],
            event_key=row["event_key"],
            command_kind=row["command_kind"],
            media_sha256=row["media_sha256"],
            actor_ref=row["actor"],
            correlation_id=row["correlation_id"],
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        raise _legacy_evidence_error() from None


def _stored_fact_error(code: str) -> ExternalSigningTypedError:
    return ExternalSigningTypedError(
        category="conflict",
        code=code,
        message=code,
    )


def _legacy_evidence_error() -> ExternalSigningTypedError:
    return ExternalSigningTypedError(
        category="conflict",
        code="contract_legacy_manual_recovery_evidence_malformed",
        message="歷史人工簽回證據不完整。",
    )


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _legacy_recovery_snapshot(value: Mapping[str, object]) -> LegacyManualRecoverySnapshot:
    current = value.get("current")
    legacy = value.get("legacy")
    if (
        value.get("kind") != "contract_legacy_manual_recovery.v1"
        or not isinstance(current, Mapping)
        or not isinstance(legacy, Mapping)
    ):
        raise _stored_fact_error("external_signing_recovery_snapshot_invalid")
    scope_value = value.get("scope")
    legacy_scope_value = legacy.get("scope")
    if not isinstance(scope_value, str) or not isinstance(legacy_scope_value, str):
        raise _stored_fact_error("external_signing_recovery_snapshot_invalid")
    if legacy_scope_value != scope_value:
        raise _stored_fact_error("external_signing_recovery_snapshot_lineage_invalid")
    try:
        scope = ExternalCompletionReportScope(scope_value)
        evidence = LegacyManualSigningEvidence(
            case_no=legacy["case_no"],
            scope=scope,
            matching_plan_id=legacy["matching_plan_id"],
            matching_segment_id=legacy.get("matching_segment_id"),
            legacy_document_version_id=legacy["legacy_document_version_id"],
            source_document_version_id=legacy["source_document_version_id"],
            signing_event_id=legacy["signing_event_id"],
            command_receipt_id=legacy["command_receipt_id"],
            event_key=legacy["event_key"],
            command_kind=legacy["command_kind"],
            media_sha256=legacy["media_sha256"],
            actor_ref=legacy["actor_ref"],
            correlation_id=legacy["correlation_id"],
        )
        if evidence.matching_plan_id != current["matching_plan_id"]:
            raise _stored_fact_error(
                "external_signing_recovery_snapshot_lineage_invalid"
            )
        preview_fingerprint = PreviewFingerprint(value["preview_fingerprint"])
        session_id = current["session_id"]
        matching_segment_id = value.get("matching_segment_id")
        target_subject_reference = current["target_subject_reference"]
        current_matching_plan_id = current["matching_plan_id"]
        current_document_version_id = current["document_version_id"]
        current_document_set_sha256 = current["document_set_sha256"]
        current_commitment_id = current.get("commitment_id")
        confirmation_method = ManualAttestationMethod(value["confirmation_method"])
        reason = value["reason"]
    except (KeyError, TypeError, ValueError, OverflowError):
        raise _stored_fact_error("external_signing_recovery_snapshot_invalid") from None
    try:
        return LegacyManualRecoverySnapshot(
            preview_fingerprint,
            evidence.case_no,
            session_id,
            scope,
            matching_segment_id,
            target_subject_reference,
            current_matching_plan_id,
            current_document_version_id,
            current_document_set_sha256,
            current_commitment_id,
            evidence,
            confirmation_method,
            reason,
        )
    except ValueError as error:
        if str(error) == "client legacy recovery requires a commitment ID":
            raise
        raise _stored_fact_error("external_signing_recovery_snapshot_invalid") from None
    except (TypeError, OverflowError):
        raise _stored_fact_error("external_signing_recovery_snapshot_invalid") from None


def _json_mapping(value: object) -> Mapping[str, object] | None:
    try:
        decoded = json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return decoded if isinstance(decoded, Mapping) else None


def _stored_final_receipt(
    row: Mapping[str, object],
) -> StoredFinalSignedContractReceipt:
    document = _final_document_readback(row)
    receipt = FinalSignedContractApplyReceipt(
        receipt_id=str(row["receipt_id"]),
        session_id=str(row["external_signing_session_id"]),
        resulting_status_version=int(row["result_status_version"]),
        resulting_state=ExternalSigningState(str(row["session_state"])),
        document=document,
        contract_identity=str(row["contract_identity"]),
    )
    return StoredFinalSignedContractReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])), receipt
    )


def _final_document_readback(
    row: Mapping[str, object],
) -> FinalContractDocumentReadback:
    return FinalContractDocumentReadback(
        final_document_id=str(row["final_document_id"]),
        case_no=str(row["case_no"]),
        file_id=str(row["file_id"]),
        version=int(row["version_number"]),
        filename=str(row["filename"]),
        mime_type=str(row["content_type"]),
        size_bytes=int(row["size_bytes"]),
        status=str(row["session_state"]),
        applied_at=_aware_utc(row["applied_at_utc"]),
    )


def _receipt_snapshot(receipt: ExternalSigningReportReceipt) -> dict[str, object]:
    return {
        "client_reminder_intent_created": receipt.client_reminder_intent_created,
        "command_type": receipt.command_type.value,
        "final_pdf_recovery_task_created": receipt.final_pdf_recovery_task_created,
        "matching_segment_id": receipt.matching_segment_id,
        "report_id": receipt.report_id,
        "resulting_state": receipt.resulting_state.value,
        "resulting_status_version": receipt.resulting_status_version,
        "scope": receipt.scope.value,
        "session_id": receipt.session_id,
    }


def _final_receipt_snapshot(
    receipt: FinalSignedContractApplyReceipt,
) -> dict[str, object]:
    document = receipt.document
    return {
        "contract_identity": receipt.contract_identity,
        "document": {
            "applied_at": document.applied_at.astimezone(timezone.utc).isoformat(),
            "case_no": document.case_no,
            "file_id": document.file_id,
            "filename": document.filename,
            "final_document_id": document.final_document_id,
            "mime_type": document.mime_type,
            "size_bytes": document.size_bytes,
            "status": document.status,
            "version": document.version,
        },
        "receipt_id": receipt.receipt_id,
        "resulting_state": receipt.resulting_state.value,
        "resulting_status_version": receipt.resulting_status_version,
        "session_id": receipt.session_id,
    }


def _require_controlled_file_matches(session, receipt, row):
    readback = receipt.readback
    matches = (
        str(row["opaque_object_id"]) == readback.file_id
        and readback.owner.value == "contract_signing"
        and readback.purpose.value == "final_signed_contract"
        and readback.subject_reference == session.case_no
        and str(row["owner_type"]) == "contract_signing"
        and str(row["purpose"]) == "final_signed_contract"
        and str(row["subject_reference"]) == session.case_no
        and str(row["filename"]) == readback.filename
        and str(row["content_type"]) == "application/pdf"
        and str(row["content_type"]) == readback.mime_type
        and int(row["size_bytes"]) == readback.size_bytes
        and str(row["content_sha256"]) == readback.sha256_digest
    )
    if not matches:
        raise _conflict(
            "final_contract_controlled_file_stale", "受控 PDF facts 已變更。"
        )


def _require_inbox_matches(command, inbox):
    matches = (
        str(inbox["payload_fingerprint"]) == command.source_payload_sha256
        and str(inbox["source_user_id"]) == command.reporter_binding.line_user_id
    )
    if not matches:
        raise _conflict("external_signing_source_event_stale", "LINE source event 已變更。")


def _database_command_type(command_type):
    return (
        "record_staff_report"
        if command_type is ExternalReportCommandType.RECORD_STAFF_REPORT
        else "record_client_report"
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _receipt_id(key: IdempotencyKey) -> str:
    suffix = key.value.rsplit(":", 1)[-1]
    if len(suffix) == 32 and all(character in "0123456789abcdef" for character in suffix):
        return f"cesr_{suffix}"
    return f"cesr_{hashlib.sha256(key.value.encode('utf-8')).hexdigest()[:32]}"


def _mysql_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


def _lock_suffix(for_update: bool) -> str:
    return " FOR UPDATE" if for_update else ""


def _conflict(code: str, message: str) -> ExternalSigningTypedError:
    return ExternalSigningTypedError(
        category="conflict", code=code, message=message, retryable=False
    )


def _document_set_fingerprint(
    case_no: str,
    matching_plan_id: int,
    segments: list[Mapping[str, Any]],
    document_by_segment: Mapping[int, int],
    client_document_version_id: int,
) -> str:
    return fingerprint_payload(
        {
            "case_no": case_no,
            "matching_plan_id": matching_plan_id,
            "staff_documents": [
                [int(row["segment_id"]), document_by_segment[int(row["segment_id"])]]
                for row in segments
            ],
            "client_document_id": client_document_version_id,
        }
    ).value


_SESSION_SELECT_SQL = (
    "SELECT id,external_signing_session_id,case_no,matching_plan_id,"
    "current_document_set_sha256,commitment_id,session_state,aggregate_version "
    "FROM contract_external_signing_sessions WHERE external_signing_session_id=%s"
)
_ACTIVE_SESSION_BY_CASE_SQL = (
    "SELECT external_signing_session_id FROM contract_external_signing_sessions "
    "WHERE active_case_key=%s"
)
_CURRENT_ORDER_SQL = "SELECT case_no,client_id FROM orders WHERE case_no=%s"
_CURRENT_ACCEPTED_PLAN_SQL = (
    "SELECT id FROM caregiver_matching_plans WHERE case_no=%s "
    "AND status='accepted' AND is_active=1"
)
_SESSION_ACTIVATE_SQL = (
    "INSERT INTO contract_external_signing_sessions "
    "(external_signing_session_id,case_no,matching_plan_id,current_document_set_sha256,"
    "activated_by_actor) VALUES (%s,%s,%s,%s,%s)"
)
_SESSION_INTERNAL_SELECT_SQL = (
    "SELECT id FROM contract_external_signing_sessions "
    "WHERE external_signing_session_id=%s FOR UPDATE"
)
_ORDER_SELECT_SQL = "SELECT case_no FROM orders WHERE case_no=%s"
_PLAN_SELECT_SQL = (
    "SELECT id FROM caregiver_matching_plans WHERE id=%s AND case_no=%s "
    "AND status='accepted' AND is_active=1"
)
_SEGMENTS_SELECT_SQL = (
    "SELECT id AS segment_id,staff_id FROM caregiver_matching_plan_segments "
    "WHERE plan_id=%s ORDER BY id"
)
_COMMITMENT_BY_PLAN_SELECT_SQL = (
    "SELECT id FROM precontract_service_commitments WHERE matching_plan_id=%s"
)
_STAFF_DOCUMENTS_SELECT_SQL = (
    "SELECT segment.id AS segment_id,document.id AS document_version_id "
    "FROM caregiver_matching_plan_segments segment JOIN contract_document_versions document "
    "ON document.matching_segment_id=segment.id AND document.case_no=%s "
    "AND document.document_scope='staff_segment' AND document.document_role='template_generated' "
    "AND NOT EXISTS (SELECT 1 FROM contract_document_versions newer WHERE "
    "newer.case_no=document.case_no AND newer.document_scope=document.document_scope "
    "AND newer.document_target_key=document.document_target_key "
    "AND newer.document_role='template_generated' AND newer.version_number>document.version_number) "
    "WHERE segment.plan_id=%s ORDER BY segment.id"
)
_CLIENT_DOCUMENT_SELECT_SQL = (
    "SELECT orders.client_id,document.id AS document_version_id FROM orders "
    "JOIN contract_document_versions document ON document.case_no=orders.case_no "
    "WHERE orders.case_no=%s AND document.matching_plan_id=%s "
    "AND document.document_scope='client_contract' AND document.document_role='template_generated' "
    "ORDER BY document.version_number DESC,document.id DESC LIMIT 1"
)
_REPORT_TARGETS_SELECT_SQL = (
    "SELECT report_scope,matching_segment_id FROM contract_external_completion_reports "
    "WHERE external_signing_session_id=%s ORDER BY id"
)
_LEGACY_MANUAL_EVIDENCE_SQL = (
    "SELECT event.id AS event_id,event.case_no AS event_case_no,event.document_version_id,"
    "event.matching_plan_id AS event_plan_id,event.matching_segment_id AS event_segment_id,"
    "event.event_type,event.event_key,event.actor,event.payload,"
    "document.case_no AS document_case_no,document.document_scope,document.document_role,"
    "document.matching_plan_id AS document_plan_id,"
    "document.matching_segment_id AS document_segment_id,"
    "document.source_document_version_id,asset.sha256 AS media_sha256,"
    "receipt.id AS receipt_db_id,receipt.idempotency_key,receipt.command_kind,"
    "receipt.case_no AS receipt_case_no,receipt.document_version_id AS receipt_document_id,"
    "receipt.signing_event_id AS receipt_event_id,receipt.correlation_id,receipt.result_snapshot "
    "FROM contract_signing_events event "
    "JOIN contract_document_versions document ON document.id=event.document_version_id "
    "JOIN media_assets asset ON asset.id=document.media_asset_id "
    "JOIN contract_signing_command_receipts receipt ON receipt.signing_event_id=event.id "
    "WHERE event.case_no=%s AND event.event_type='signed_received' "
    "AND document.document_role='signed_return' ORDER BY event.id,receipt.id"
)
_BINDING_SELECT_SQL = (
    "SELECT binding_status,subject_type,subject_reference,aggregate_version "
    "FROM line_identity_bindings WHERE line_user_id=%s"
)
_INBOX_SELECT_SQL = (
    "SELECT id,payload_fingerprint,source_user_id FROM line_inbox_events "
    "WHERE event_identity=%s FOR UPDATE"
)
_RECEIPT_BY_KEY_SQL = (
    "SELECT command_fingerprint,result_snapshot FROM contract_external_signing_receipts "
    "WHERE idempotency_key=%s"
)
_RECEIPT_BY_SOURCE_SQL = (
    "SELECT receipt.command_fingerprint,receipt.result_snapshot "
    "FROM contract_external_completion_reports report "
    "JOIN contract_external_signing_receipts receipt ON receipt.completion_report_id=report.id "
    "WHERE report.source_event_identity=%s"
)
_REPORT_INSERT_SQL = (
    "INSERT INTO contract_external_completion_reports "
    "(report_id,external_signing_session_id,case_no,report_scope,matching_segment_id,"
    "document_version_id,commitment_id,reporter_subject_type,reporter_subject_reference,"
    "source_kind,source_event_identity,source_payload_sha256,line_inbox_event_id,"
    "verified_line_user_id,verified_binding_version,manual_confirmation_method,manual_reason,"
    "manual_evidence_reference,manual_evidence_sha256,idempotency_key,command_fingerprint,"
    "expected_status_version,resulting_status_version,occurred_at_utc,actor_ref) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_RECOVERY_INSERT_SQL = (
    "INSERT INTO contract_final_pdf_recovery_tasks "
    "(recovery_task_id,external_signing_session_id,client_report_id,idempotency_key,"
    "command_fingerprint,created_by_actor) VALUES (%s,%s,%s,%s,%s,%s)"
)
_SESSION_ADVANCE_SQL = (
    "UPDATE contract_external_signing_sessions SET session_state=%s,"
    "commitment_id=COALESCE(%s,commitment_id),"
    "client_reminder_task_id=COALESCE(%s,client_reminder_task_id),aggregate_version=%s "
    "WHERE external_signing_session_id=%s AND aggregate_version=%s"
)
_RECEIPT_INSERT_SQL = (
    "INSERT INTO contract_external_signing_receipts "
    "(receipt_id,external_signing_session_id,command_type,schema_version,idempotency_key,"
    "command_fingerprint,preview_fingerprint,expected_status_version,result_status_version,"
    "completion_report_id,final_document_version_id,result_snapshot,outcome_state,actor_ref,"
    "correlation_id,applied_at_utc) VALUES (%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s,NULL,%s,'recorded',%s,%s,%s)"
)
_CONTROLLED_FILE_SELECT_SQL = (
    "SELECT id,opaque_object_id,owner_type,subject_reference,purpose,filename,"
    "content_type,size_bytes,content_sha256 FROM controlled_file_objects "
    "WHERE opaque_object_id=%s FOR UPDATE"
)
_FINAL_DOCUMENT_PREDECESSOR_SQL = (
    "SELECT id,version_number FROM contract_final_document_versions "
    "WHERE case_no=%s ORDER BY version_number DESC,id DESC LIMIT 1 FOR UPDATE"
)
_FINAL_DOCUMENT_INSERT_SQL = (
    "INSERT INTO contract_final_document_versions "
    "(final_document_id,external_signing_session_id,case_no,source_document_set_sha256,"
    "controlled_file_object_id,version_number,contract_identity,content_type,size_bytes,"
    "content_sha256,created_by_actor,created_at_utc) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,'application/pdf',%s,%s,%s,%s)"
)
_RECOVERY_FULFILL_SQL = (
    "UPDATE contract_final_pdf_recovery_tasks recovery "
    "JOIN contract_external_signing_sessions session "
    "ON session.id=recovery.external_signing_session_id "
    "JOIN contract_final_document_versions document "
    "ON document.external_signing_session_id=session.id "
    "SET recovery.task_state='fulfilled',recovery.aggregate_version=recovery.aggregate_version+1,"
    "recovery.fulfilled_at_utc=%s WHERE session.external_signing_session_id=%s "
    "AND document.final_document_id=%s AND recovery.task_state='pending'"
)
_FINAL_SESSION_COMPLETE_SQL = (
    "UPDATE contract_external_signing_sessions SET session_state='completed',"
    "aggregate_version=%s WHERE external_signing_session_id=%s "
    "AND aggregate_version=%s AND session_state='client_reported_final_pdf_pending'"
)
_FINAL_READBACK_COLUMNS = (
    "document.final_document_id,document.case_no,object.opaque_object_id AS file_id,"
    "document.version_number,object.filename,object.content_type,object.size_bytes,"
    "session.session_state,document.created_at_utc AS applied_at_utc"
)
_FINAL_DOCUMENT_READBACK_SQL = (
    "SELECT " + _FINAL_READBACK_COLUMNS + " FROM contract_final_document_versions document "
    "JOIN contract_external_signing_sessions session "
    "ON session.id=document.external_signing_session_id "
    "JOIN controlled_file_objects object ON object.id=document.controlled_file_object_id "
    "WHERE document.case_no=%s AND session.session_state='completed' "
    "ORDER BY document.version_number DESC,document.id DESC LIMIT 1"
)
_FINAL_RECEIPT_SELECT_SQL = (
    "SELECT receipt.receipt_id,receipt.command_fingerprint,receipt.result_status_version,"
    "session.external_signing_session_id,document.contract_identity," + _FINAL_READBACK_COLUMNS
    + " FROM contract_external_signing_receipts receipt "
    "JOIN contract_external_signing_sessions session "
    "ON session.id=receipt.external_signing_session_id "
    "JOIN contract_final_document_versions document "
    "ON document.id=receipt.final_document_version_id "
    "JOIN controlled_file_objects object ON object.id=document.controlled_file_object_id "
    "WHERE receipt.idempotency_key=%s AND receipt.command_type='apply_final_signed_contract'"
)
_FINAL_RECEIPT_CONTEXT_SQL = (
    "SELECT document.id AS final_document_database_id,"
    "document.external_signing_session_id AS session_database_id,"
    "document.created_by_actor AS actor_ref FROM contract_final_document_versions document "
    "WHERE document.final_document_id=%s FOR UPDATE"
)
_FINAL_RECEIPT_INSERT_SQL = (
    "INSERT INTO contract_external_signing_receipts "
    "(receipt_id,external_signing_session_id,command_type,schema_version,idempotency_key,"
    "command_fingerprint,preview_fingerprint,expected_status_version,result_status_version,"
    "completion_report_id,final_document_version_id,result_snapshot,outcome_state,actor_ref,"
    "correlation_id,applied_at_utc) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s,%s,'completed',%s,%s,%s)"
)


__all__ = ["MySqlContractExternalSigningRepository"]
