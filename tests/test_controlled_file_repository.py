"""
File: test_controlled_file_repository.py
Description: 驗證受控檔案 MySQL repository 的鎖、映射、CAS 與零 hidden commit。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from infrastructure.db.controlled_file_repository import (
    MySqlControlledFileWorkflowRepository,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.controlled_files.contracts import (
    ControlledFileStagingCleanupReason,
    ControlledFileStagingRegistrationStatus,
)
from subsystems.controlled_files.reconciliation import (
    ControlledFileReconciliationEvent,
    ControlledFileReconciliationOutcome,
)
from subsystems.controlled_files.gc import ControlledFileGcError
from subsystems.controlled_files.cleanup import (
    CleanupControlledFileStaging,
    ControlledFileCleanupOutcome,
    ControlledFileCleanupReceipt,
    ControlledFileCleanupTerminal,
)
from subsystems.controlled_files.workflow import (
    ControlledFileApplyOutcome,
    ControlledFileApplyReceipt,
    ControlledFileCandidate,
    ControlledFileCommandClaim,
    ControlledFileIntent,
    ControlledFileOwner,
    ControlledFilePurpose,
    ControlledFileReadback,
    StoredControlledFileApplyReceipt,
)


NOW = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
EXPIRES = NOW + timedelta(hours=24)
STAGING_ID = "cfs_1234567890abcdef1234567890abcdef"
FILE_ID = "cf_1234567890abcdef1234567890abcdef"
DIGEST = hashlib.sha256(b"signed-contract").hexdigest()


class ScriptedCursor:
    def __init__(self, rows=(), rowcounts=()) -> None:
        self.rows = list(rows)
        self.rowcounts = list(rowcounts)
        self.executions = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters=()):
        self.executions.append((statement, parameters))
        self.rowcount = self.rowcounts.pop(0) if self.rowcounts else 0

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows


class FakeConnection:
    def __init__(self, cursor) -> None:
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _candidate() -> ControlledFileCandidate:
    return ControlledFileCandidate(
        staging_id=STAGING_ID,
        staging_version=1,
        owner=ControlledFileOwner.CONTRACT_SIGNING,
        purpose=ControlledFilePurpose.FINAL_SIGNED_CONTRACT,
        subject_reference="CASE-001",
        object_key="final-contract",
        logical_folder="contracts",
        filename="contract.pdf",
        mime_type="application/pdf",
        size_bytes=15,
        sha256_digest=DIGEST,
        expires_at=EXPIRES,
    )


def _staging_row():
    candidate = _candidate()
    return {
        "id": 8,
        "staging_id": candidate.staging_id,
        "storage_locator": ".controlled-file-staging/object/payload",
        "owner_type": candidate.owner.value,
        "subject_reference": candidate.subject_reference,
        "object_key": candidate.object_key,
        "purpose": candidate.purpose.value,
        "logical_folder": candidate.logical_folder,
        "original_filename": candidate.filename,
        "content_type": candidate.mime_type,
        "size_bytes": candidate.size_bytes,
        "content_sha256": candidate.sha256_digest,
        "staging_state": "staged",
        "staging_version": 1,
        "expires_at_utc": EXPIRES.replace(tzinfo=None),
    }


def _readback(file_id=FILE_ID):
    candidate = _candidate()
    return ControlledFileReadback(
        file_id=file_id,
        owner=candidate.owner,
        purpose=candidate.purpose,
        subject_reference=candidate.subject_reference,
        filename=candidate.filename,
        logical_folder=candidate.logical_folder,
        version=1,
        sha256_digest=candidate.sha256_digest,
        mime_type=candidate.mime_type,
        size_bytes=candidate.size_bytes,
        status="registered",
        applied_at=NOW,
    )


def test_load_staging_maps_state_and_applies_requested_lock_without_commit() -> None:
    row = _staging_row()
    cursor = ScriptedCursor([row])
    connection = FakeConnection(cursor)

    result = MySqlControlledFileWorkflowRepository(connection).load_staging(
        STAGING_ID, for_update=True
    )

    assert result is not None
    assert result.registration_status is ControlledFileStagingRegistrationStatus.UNREGISTERED
    assert result.version == 1
    assert result.staging.expires_at == EXPIRES
    assert result.stored_intent == ControlledFileIntent(
        staging_id=STAGING_ID,
        owner=ControlledFileOwner.CONTRACT_SIGNING,
        purpose=ControlledFilePurpose.FINAL_SIGNED_CONTRACT,
        subject_reference="CASE-001",
        object_key="final-contract",
        logical_folder="contracts",
    )
    assert cursor.executions[0][0].endswith(" FOR UPDATE")
    assert cursor.executions[0][1] == (STAGING_ID,)
    assert connection.commits == connection.rollbacks == 0


def test_gc_candidate_query_fails_closed_without_reference_and_lease_ssot() -> None:
    cursor = ScriptedCursor()
    connection = FakeConnection(cursor)

    with pytest.raises(ControlledFileGcError) as captured:
        MySqlControlledFileWorkflowRepository(connection).list_staging_gc_candidates(
            limit=10, observed_at=NOW
        )

    assert captured.value.code == "controlled_file_gc_reference_authority_not_ready"
    assert cursor.executions == []
    assert connection.commits == connection.rollbacks == 0


@pytest.mark.parametrize(
    ("owner", "subject", "table"),
    [
        (ControlledFileOwner.CONTRACT_SIGNING, "CASE-001", "orders"),
        (ControlledFileOwner.SCHEDULING, "CASE-001", "orders"),
        (ControlledFileOwner.ORDERS, "CASE-001", "orders"),
        (ControlledFileOwner.STAFF, "42", "staff"),
        (ControlledFileOwner.LINE_INTEGRATION, "menu-staff", "line_rich_menu_publications"),
    ],
)
def test_owner_subject_exists_uses_closed_parameterized_routing(owner, subject, table) -> None:
    cursor = ScriptedCursor([{"present": 1}])
    connection = FakeConnection(cursor)
    intent = ControlledFileIntent(
        staging_id=STAGING_ID,
        owner=owner,
        purpose={
            ControlledFileOwner.CONTRACT_SIGNING: ControlledFilePurpose.FINAL_SIGNED_CONTRACT,
            ControlledFileOwner.SCHEDULING: ControlledFilePurpose.BABY_LOG_PHOTO,
            ControlledFileOwner.ORDERS: ControlledFilePurpose.ORDER_NOTICE,
            ControlledFileOwner.STAFF: ControlledFilePurpose.STAFF_RESUME,
            ControlledFileOwner.LINE_INTEGRATION: ControlledFilePurpose.RICH_MENU_BACKGROUND,
        }[owner],
        subject_reference=subject,
        object_key="object",
        logical_folder="folder",
    )

    assert MySqlControlledFileWorkflowRepository(connection).owner_subject_exists(
        intent, for_update=True
    )
    statement, parameters = cursor.executions[0]
    assert table in statement and statement.endswith(" FOR UPDATE")
    assert subject not in statement
    assert all(parameter == subject for parameter in parameters)
    assert connection.commits == 0


def test_claim_command_returns_created_or_mismatch_without_hidden_commit() -> None:
    fingerprint = PreviewFingerprint("a" * 64)
    created_cursor = ScriptedCursor(rowcounts=[1])
    created_connection = FakeConnection(created_cursor)
    repository = MySqlControlledFileWorkflowRepository(created_connection)

    assert repository.claim_command(IdempotencyKey("controlled-file:1"), fingerprint, CorrelationId("corr-1")) is ControlledFileCommandClaim.CREATED
    assert "INSERT IGNORE" in created_cursor.executions[0][0]
    assert created_connection.commits == 0

    mismatch_cursor = ScriptedCursor(
        [{"command_family": "other", "aggregate_identity": "other", "command_fingerprint": "b" * 64}],
        rowcounts=[0, 0],
    )
    mismatch_connection = FakeConnection(mismatch_cursor)
    mismatch = MySqlControlledFileWorkflowRepository(mismatch_connection).claim_command(
        IdempotencyKey("controlled-file:1"), fingerprint, CorrelationId("corr-1")
    )
    assert mismatch is ControlledFileCommandClaim.MISMATCH
    assert mismatch_cursor.executions[1][0].endswith(" FOR UPDATE")
    assert mismatch_connection.commits == 0


def test_register_file_locks_version_chain_and_never_projects_locator() -> None:
    cursor = ScriptedCursor([_staging_row(), None], rowcounts=[0, 0, 1])
    connection = FakeConnection(cursor)

    result = MySqlControlledFileWorkflowRepository(connection).register_file(
        _candidate(), actor=ActorContext("admin-001"), applied_at=NOW
    )

    assert result.file_id.startswith("cf_") and len(result.file_id) == 35
    assert result.version == 1
    assert "storage_locator" not in repr(result)
    assert cursor.executions[0][0].endswith(" FOR UPDATE")
    assert cursor.executions[1][0].endswith(" FOR UPDATE")
    insert_sql, insert_values = cursor.executions[2]
    assert "INSERT INTO controlled_file_objects" in insert_sql
    assert insert_values[8] == _staging_row()["storage_locator"]
    assert connection.commits == 0


def test_mark_staging_registered_is_compare_and_swap_without_commit() -> None:
    cursor = ScriptedCursor(rowcounts=[1])
    connection = FakeConnection(cursor)

    MySqlControlledFileWorkflowRepository(connection).mark_staging_registered(
        STAGING_ID, expected_version=ExpectedVersion(1), file_id=FILE_ID
    )

    statement, parameters = cursor.executions[0]
    assert "staging_state='staged'" in statement
    assert "staging_version=%s" in statement
    assert parameters == (STAGING_ID, 1, FILE_ID)
    assert connection.commits == 0


def test_save_and_reload_receipt_use_canonical_snapshot_without_locator() -> None:
    receipt = ControlledFileApplyReceipt(
        receipt_id="cfr_1234567890abcdef1234567890abcdef",
        outcome=ControlledFileApplyOutcome.CREATED,
        readback=_readback(),
    )
    stored = StoredControlledFileApplyReceipt(PreviewFingerprint("a" * 64), receipt)
    context = {
        "staging_object_id": 8,
        "controlled_object_id": 9,
        "actor_ref": "admin-001",
        "correlation_id": "controlled-file:1",
        "staging_id": STAGING_ID,
        "expected_staging_version": 1,
        "expires_at_utc": EXPIRES.replace(tzinfo=None),
        "owner_type": "contract_signing",
        "subject_reference": "CASE-001",
        "object_key": "final-contract",
        "purpose": "final_signed_contract",
        "logical_folder": "contracts",
        "filename": "contract.pdf",
        "logical_folder": "contracts",
        "content_type": "application/pdf",
        "size_bytes": 15,
        "content_sha256": DIGEST,
    }
    cursor = ScriptedCursor([context], rowcounts=[0, 1])
    connection = FakeConnection(cursor)
    repository = MySqlControlledFileWorkflowRepository(connection)

    repository.save_receipt(
        IdempotencyKey("controlled-file:1"), stored, CorrelationId("corr-1")
    )

    select_parameters = cursor.executions[0][1]
    assert select_parameters == (FILE_ID,)
    insert_values = cursor.executions[1][1]
    snapshot = json.loads(insert_values[9])
    assert snapshot["file_id"] == FILE_ID
    assert "storage_locator" not in snapshot
    assert insert_values[7] != stored.command_fingerprint.value
    assert insert_values[11] == "corr-1"
    assert connection.commits == 0

    row = {
        "receipt_id": receipt.receipt_id,
        "command_type": receipt.receipt_type,
        "schema_version": receipt.schema_version,
        "command_fingerprint": "a" * 64,
        "result_snapshot": json.dumps(snapshot),
        "file_id": FILE_ID,
        "owner_type": "contract_signing",
        "purpose": "final_signed_contract",
        "subject_reference": "CASE-001",
        "filename": "contract.pdf",
        "logical_folder": "contracts",
        "version_number": 1,
        "content_sha256": DIGEST,
        "content_type": "application/pdf",
        "size_bytes": 15,
        "applied_at_utc": NOW.replace(tzinfo=None),
    }
    replay_cursor = ScriptedCursor([row])
    replay = MySqlControlledFileWorkflowRepository(FakeConnection(replay_cursor)).find_receipt(
        IdempotencyKey("controlled-file:1"), for_update=True
    )
    assert replay == stored
    assert replay_cursor.executions[0][0].endswith(" FOR UPDATE")


def test_receipt_readback_rejects_corrupt_snapshot() -> None:
    row = {
        "receipt_id": "cfr_1234567890abcdef1234567890abcdef",
        "command_type": "controlled_file_apply",
        "schema_version": "controlled-file-apply-receipt.v1",
        "command_fingerprint": "a" * 64,
        "result_snapshot": "{}",
        "file_id": FILE_ID,
        "owner_type": "contract_signing",
        "purpose": "final_signed_contract",
        "subject_reference": "CASE-001",
        "filename": "contract.pdf",
        "logical_folder": "contracts",
        "version_number": 1,
        "content_sha256": DIGEST,
        "content_type": "application/pdf",
        "size_bytes": 15,
        "applied_at_utc": NOW.replace(tzinfo=None),
    }
    repository = MySqlControlledFileWorkflowRepository(FakeConnection(ScriptedCursor([row])))

    with pytest.raises(RuntimeError, match="receipt_corrupt"):
        repository.find_receipt(IdempotencyKey("controlled-file:1"), for_update=False)


@pytest.mark.parametrize(
    ("outcome", "file_id", "staging_id", "target"),
    [
        (ControlledFileReconciliationOutcome.EXACT, FILE_ID, STAGING_ID, FILE_ID),
        (
            ControlledFileReconciliationOutcome.ORPHAN_OBJECT,
            None,
            STAGING_ID,
            STAGING_ID,
        ),
    ],
)
def test_append_reconciliation_event_uses_targeted_insert_without_hidden_commit(
    outcome, file_id, staging_id, target
) -> None:
    event = ControlledFileReconciliationEvent(
        event_id="cfe_1234567890abcdef1234567890abcdef",
        outcome=outcome,
        observation_fingerprint=PreviewFingerprint("c" * 64),
        observed_at=NOW,
        actor=ActorContext("reconciliation-worker"),
        correlation_id=CorrelationId("corr-reconcile-001"),
        file_id=file_id,
        staging_id=staging_id,
        observed_sha256=DIGEST,
        observed_size_bytes=15,
    )
    cursor = ScriptedCursor(rowcounts=[1])
    connection = FakeConnection(cursor)

    MySqlControlledFileWorkflowRepository(connection).append_reconciliation_event(event)

    statement, parameters = cursor.executions[0]
    assert "INSERT IGNORE INTO controlled_file_reconciliation_events" in statement
    assert parameters[-1] == target
    snapshot = json.loads(parameters[5])
    assert snapshot["outcome"] == outcome.value
    assert "locator" not in snapshot
    assert connection.commits == connection.rollbacks == 0


def _cleanup_command():
    return CleanupControlledFileStaging(
        staging_id=STAGING_ID,
        reason=ControlledFileStagingCleanupReason.EXPIRED,
        expected_staging_version=ExpectedVersion(1),
        expected_sha256=DIGEST,
        idempotency_key=IdempotencyKey("controlled-file.cleanup:repository-001"),
        actor=ActorContext("cleanup-worker"),
        correlation_id=CorrelationId("corr-cleanup-repository-001"),
    )


def test_cleanup_repository_claims_then_completes_without_hidden_commit():
    command = _cleanup_command()
    cursor = ScriptedCursor(rowcounts=[1, 1, 1, 1])
    connection = FakeConnection(cursor)
    repository = MySqlControlledFileWorkflowRepository(connection)

    stored = repository.begin_cleanup(
        command,
        cleanup_id="cfc_1234567890abcdef1234567890abcdef",
        command_fingerprint=PreviewFingerprint("d" * 64),
        occurred_at=NOW,
    )
    receipt = ControlledFileCleanupReceipt(
        cleanup_id=stored.cleanup_id,
        staging_id=stored.staging_id,
        reason=stored.reason,
        outcome=ControlledFileCleanupOutcome.CLEANED,
        cleaned_at=NOW,
    )
    repository.complete_cleanup(stored, receipt, occurred_at=NOW)

    assert stored.terminal is ControlledFileCleanupTerminal.INTENT
    assert "event_sequence,event_type" in cursor.executions[0][0]
    assert "staging_state='quarantined'" in cursor.executions[1][0]
    assert "staging_state='cleaned'" in cursor.executions[2][0]
    assert "'completed'" not in cursor.executions[3][0]
    assert cursor.executions[3][1][1] == "completed"
    assert connection.commits == connection.rollbacks == 0
