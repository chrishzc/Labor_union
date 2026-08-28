"""
File: test_contract_external_signing_repository.py
Description: 驗證外部簽約 MySQL adapter 的 borrowed transaction、鎖定與去敏 receipt snapshot。
"""

from __future__ import annotations

from datetime import datetime, timezone
import json

from domains.contract_signing.external_signing import (
    ExternalSigningSessionFacts,
    ExternalSigningState,
    ExternalSigningTransition,
    StaffSigningReportTarget,
)
from infrastructure.db.contract_external_signing_repository import (
    MySqlContractExternalSigningRepository,
    _document_set_fingerprint,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.contract_signing.external_signing_contracts import (
    ExternalCompletionReportScope,
    ExternalReportCommandType,
    ExternalReporterSubjectType,
    ExternalSigningReportReceipt,
    RecordExternalStaffSigningReport,
    ManualAttestationEvidence,
    ManualAttestationMethod,
    RecordManualExternalStaffSigningReport,
    StoredExternalSigningReportReceipt,
    VerifiedReporterBindingSnapshot,
)
from subsystems.contract_signing.external_signing_workflow import PersistedExternalReport
from subsystems.contract_signing.final_document_workflow import (
    FinalContractDocumentReadback,
    FinalSignedContractApplyReceipt,
    StoredFinalSignedContractReceipt,
)
from subsystems.controlled_files.workflow import (
    ControlledFileApplyOutcome,
    ControlledFileApplyReceipt,
    ControlledFileOwner,
    ControlledFilePurpose,
    ControlledFileReadback,
)


def test_binding_validation_uses_fresh_lock_without_owning_transaction() -> None:
    connection = FakeConnection(
        {
            "line_identity_bindings": {
                "binding_status": "bound",
                "subject_type": "staff",
                "subject_reference": "501",
                "aggregate_version": 3,
            }
        }
    )
    repository = MySqlContractExternalSigningRepository(connection)

    assert repository.reporter_binding_is_current(_binding(), for_update=True) is True
    assert connection.executions[-1][0].endswith(" FOR UPDATE")
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0


def test_saved_receipt_snapshot_excludes_digest_fingerprint_and_locator() -> None:
    connection = FakeConnection({"contract_external_signing_sessions": {"id": 5}})
    repository = MySqlContractExternalSigningRepository(connection)
    command = _command()
    receipt = ExternalSigningReportReceipt(
        ExternalReportCommandType.RECORD_STAFF_REPORT,
        "cer_1234567890abcdef1234567890abcdef",
        command.session_id,
        ExternalCompletionReportScope.STAFF,
        11,
        1,
        ExternalSigningState.STAFF_REPORTING,
        False,
        False,
    )

    repository.save_receipt(
        command.idempotency_key,
        StoredExternalSigningReportReceipt(PreviewFingerprint("d" * 64), receipt),
        command,
        PersistedExternalReport(receipt.report_id, 81),
    )

    insert = next(item for item in connection.executions if item[0].startswith("INSERT INTO"))
    snapshot = json.loads(insert[1][9])
    serialized = json.dumps(snapshot)
    assert "sha256" not in serialized
    assert "fingerprint" not in serialized
    assert "locator" not in serialized
    assert "url" not in serialized.lower()
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0


def test_register_final_document_resolves_opaque_file_without_leaking_storage() -> None:
    connection = FakeConnection(
        {
            "contract_external_signing_sessions": {"id": 5},
            "controlled_file_objects": _controlled_file_row(),
        }
    )
    repository = MySqlContractExternalSigningRepository(connection)

    result = repository.register_final_document(
        _final_session(),
        _controlled_receipt(),
        actor=ActorContext("operator:1"),
        contract_identity="contract:CASE-001:v1",
        applied_at=datetime(2026, 8, 26, 12, tzinfo=timezone.utc),
    )

    controlled_select = next(
        statement for statement, _ in connection.executions
        if "FROM controlled_file_objects" in statement
    )
    assert "storage_locator" not in controlled_select
    assert result.file_id == "cf_1234567890abcdef1234567890abcdef"
    assert result.mime_type == "application/pdf"
    assert not hasattr(result, "sha256_digest")
    assert connection.commit_calls == connection.rollback_calls == 0


def test_complete_session_fulfills_recovery_and_cas_without_commit() -> None:
    connection = FakeConnection({})
    repository = MySqlContractExternalSigningRepository(connection)
    document = repository_readback()

    repository.complete_session_and_recovery(
        _final_session(),
        document,
        resulting_status_version=4,
        applied_at=document.applied_at,
    )

    updates = [item for item in connection.executions if item[0].startswith("UPDATE")]
    assert len(updates) == 2
    assert "task_state='fulfilled'" in updates[0][0]
    assert "session_state='completed'" in updates[1][0]
    assert connection.commit_calls == connection.rollback_calls == 0


def test_final_receipt_snapshot_and_readback_are_public_safe() -> None:
    connection = FakeConnection(
        {
            "contract_final_document_versions document": {
                "final_document_database_id": 91,
                "session_database_id": 5,
                "actor_ref": "operator:1",
            }
        }
    )
    repository = MySqlContractExternalSigningRepository(connection)
    receipt = FinalSignedContractApplyReceipt(
        "cesr_1234567890abcdef1234567890abcdef",
        _final_session().session_id,
        4,
        ExternalSigningState.COMPLETED,
        repository_readback(),
        "contract:CASE-001:v1",
    )

    repository.save_final_receipt(
        IdempotencyKey("contract-final:001"),
        StoredFinalSignedContractReceipt(PreviewFingerprint("e" * 64), receipt),
        CorrelationId("corr-final-001"),
        expected_status_version=3,
        applied_at=receipt.document.applied_at,
    )

    insert = next(item for item in connection.executions if item[0].startswith("INSERT INTO"))
    snapshot = json.loads(insert[1][10])
    serialized = json.dumps(snapshot).lower()
    assert all(term not in serialized for term in ("sha256", "fingerprint", "locator", "url"))
    assert insert[1][2] == "apply_final_signed_contract"
    assert connection.commit_calls == connection.rollback_calls == 0


def test_find_final_receipt_and_get_readback_expose_only_opaque_identity() -> None:
    row = _final_readback_row()
    receipt_connection = FakeConnection(
        {"contract_external_signing_receipts receipt": row}
    )
    receipt_repository = MySqlContractExternalSigningRepository(receipt_connection)

    stored = receipt_repository.find_final_receipt(
        IdempotencyKey("contract-final:001"), for_update=True
    )

    assert stored is not None
    assert stored.receipt.document.file_id.startswith("cf_")
    assert receipt_connection.executions[-1][0].endswith(" FOR UPDATE")
    assert "storage_locator" not in receipt_connection.executions[-1][0]
    assert "content_sha256" not in receipt_connection.executions[-1][0]

    readback_connection = FakeConnection(
        {"contract_final_document_versions document": row}
    )
    readback_repository = MySqlContractExternalSigningRepository(readback_connection)
    readback = readback_repository.get_final_document("CASE-001")
    assert readback == stored.receipt.document
    assert not hasattr(readback, "sha256_digest")


def test_manual_report_persists_manual_columns_without_line_inbox() -> None:
    connection = FakeConnection({"contract_external_signing_sessions": {"id": 5}})
    repository = MySqlContractExternalSigningRepository(connection)
    command = _manual_command()
    transition = ExternalSigningTransition(
        ExternalSigningState.STAFF_REPORTING, 1, (11,), False
    )

    repository.append_report(
        command, transition, PreviewFingerprint("d" * 64), None
    )

    insert = next(item for item in connection.executions if item[0].startswith("INSERT INTO"))
    assert insert[1][9] == "manual_attested"
    assert insert[1][12:15] == (None, None, None)
    assert insert[1][15] == "phone"
    assert insert[1][17] == "evidence:manual:001"
    assert not any("line_inbox_events" in sql for sql, _ in connection.executions)


def test_load_session_requires_current_active_accepted_plan_and_document_set() -> None:
    segments = [{"segment_id": 11, "staff_id": "501"}]
    fingerprint = _document_set_fingerprint(
        "CASE-001", 9, segments, {11: 101}, 201
    )
    connection = ScriptedConnection([
        _session_row(fingerprint),
        {"case_no": "CASE-001"},
        {"id": 9},
        segments,
        {"id": 44},
        [{"segment_id": 11, "document_version_id": 101}],
        {"client_id": "301", "document_version_id": 201},
        [],
    ])

    facts = MySqlContractExternalSigningRepository(connection).load_session(
        _final_session().session_id, for_update=True
    )

    assert facts is not None
    plan_sql, plan_params = connection.executions[2]
    assert "case_no=%s" in plan_sql
    assert "status='accepted'" in plan_sql
    assert "is_active=1" in plan_sql
    assert plan_sql.endswith(" FOR UPDATE")
    assert plan_params == (9, "CASE-001")


def test_load_session_rejects_changed_current_document_set() -> None:
    segments = [{"segment_id": 11, "staff_id": "501"}]
    connection = ScriptedConnection([
        _session_row("a" * 64),
        {"case_no": "CASE-001"},
        {"id": 9},
        segments,
        {"id": 44},
        [{"segment_id": 11, "document_version_id": 102}],
        {"client_id": "301", "document_version_id": 201},
    ])

    repository = MySqlContractExternalSigningRepository(connection)

    try:
        repository.load_session(_final_session().session_id, for_update=False)
    except RuntimeError as error:
        assert str(error) == "external_signing_document_set_stale"
    else:
        raise AssertionError("stale document set must fail closed")


def _session_row(fingerprint: str) -> dict[str, object]:
    return {
        "id": 5,
        "external_signing_session_id": _final_session().session_id,
        "case_no": "CASE-001",
        "matching_plan_id": 9,
        "current_document_set_sha256": fingerprint,
        "commitment_id": None,
        "session_state": "staff_reporting",
        "aggregate_version": 0,
    }


def _final_session() -> ExternalSigningSessionFacts:
    return ExternalSigningSessionFacts(
        "ces_1234567890abcdef1234567890abcdef",
        "CASE-001",
        9,
        "a" * 64,
        (StaffSigningReportTarget(11, "501", 101),),
        (11,),
        "301",
        201,
        44,
        True,
        ExternalSigningState.CLIENT_REPORTED_FINAL_PDF_PENDING,
        3,
    )


def _controlled_file_row():
    return {
        "id": 61,
        "opaque_object_id": "cf_1234567890abcdef1234567890abcdef",
        "owner_type": "contract_signing",
        "subject_reference": "CASE-001",
        "purpose": "final_signed_contract",
        "filename": "final.pdf",
        "content_type": "application/pdf",
        "size_bytes": 2048,
        "content_sha256": "f" * 64,
    }


def _final_readback_row():
    return {
        "receipt_id": "cesr_1234567890abcdef1234567890abcdef",
        "command_fingerprint": "e" * 64,
        "result_status_version": 4,
        "external_signing_session_id": _final_session().session_id,
        "contract_identity": "contract:CASE-001:v1",
        "final_document_id": "cfd_1234567890abcdef1234567890abcdef",
        "case_no": "CASE-001",
        "file_id": "cf_1234567890abcdef1234567890abcdef",
        "version_number": 1,
        "filename": "final.pdf",
        "content_type": "application/pdf",
        "size_bytes": 2048,
        "session_state": "completed",
        "applied_at_utc": datetime(2026, 8, 26, 12),
    }


def _controlled_receipt() -> ControlledFileApplyReceipt:
    return ControlledFileApplyReceipt(
        "cfr_1234567890abcdef1234567890abcdef",
        ControlledFileApplyOutcome.CREATED,
        ControlledFileReadback(
            "cf_1234567890abcdef1234567890abcdef",
            ControlledFileOwner.CONTRACT_SIGNING,
            ControlledFilePurpose.FINAL_SIGNED_CONTRACT,
            "CASE-001",
            "final.pdf",
            "contracts/CASE-001",
            1,
            "f" * 64,
            "application/pdf",
            2048,
            "created",
            datetime(2026, 8, 26, 12, tzinfo=timezone.utc),
        ),
    )


def repository_readback() -> FinalContractDocumentReadback:
    return FinalContractDocumentReadback(
        "cfd_1234567890abcdef1234567890abcdef",
        "CASE-001",
        "cf_1234567890abcdef1234567890abcdef",
        1,
        "final.pdf",
        "application/pdf",
        2048,
        "completed",
        datetime(2026, 8, 26, 12, tzinfo=timezone.utc),
    )


class FakeCursor:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.rowcount = 0
        self.lastrowid = 91
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, parameters=()):
        self.connection.executions.append((statement, parameters))
        self.rowcount = 1 if statement.startswith(("INSERT", "UPDATE")) else 0
        self.row = next(
            (value for key, value in self.connection.rows.items() if key in statement),
            None,
        )

    def fetchone(self):
        return self.row

    def fetchall(self):
        return () if self.row is None else (self.row,)


class FakeConnection:
    def __init__(self, rows) -> None:
        self.rows = rows
        self.executions = []
        self.commit_calls = 0
        self.rollback_calls = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1


class ScriptedCursor(FakeCursor):
    def execute(self, statement, parameters=()):
        self.connection.executions.append((statement, parameters))
        self.rowcount = 0
        self.row = self.connection.script.pop(0)

    def fetchone(self):
        if isinstance(self.row, list):
            return self.row[0] if self.row else None
        return self.row

    def fetchall(self):
        if isinstance(self.row, list):
            return tuple(self.row)
        return () if self.row is None else (self.row,)


class ScriptedConnection(FakeConnection):
    def __init__(self, script) -> None:
        super().__init__({})
        self.script = list(script)

    def cursor(self):
        return ScriptedCursor(self)


def _binding():
    return VerifiedReporterBindingSnapshot(
        "U-staff", ExternalReporterSubjectType.STAFF, "501", ExpectedVersion(3)
    )


def _command():
    return RecordExternalStaffSigningReport(
        "ces_1234567890abcdef1234567890abcdef",
        "CASE-001",
        9,
        11,
        101,
        _binding(),
        "line-event-staff-001",
        "b" * 64,
        datetime(2026, 8, 26, 10, tzinfo=timezone.utc),
        ExpectedVersion(0),
        ActorContext("line_user_id:U-staff"),
        IdempotencyKey("external-report:staff:001"),
        CorrelationId("corr-staff-001"),
    )


def _manual_command():
    return RecordManualExternalStaffSigningReport(
        "ces_1234567890abcdef1234567890abcdef", "CASE-001", 9, 11, 101, "501",
        ManualAttestationEvidence(
            ManualAttestationMethod.PHONE, "confirmed by administrator",
            "evidence:manual:001", "e" * 64,
        ),
        "manual-event-001", "c" * 64,
        datetime(2026, 8, 26, 10, tzinfo=timezone.utc), ExpectedVersion(0),
        ActorContext("admin:17"), IdempotencyKey("external-report:manual:001"),
        CorrelationId("corr-manual-001"),
    )
