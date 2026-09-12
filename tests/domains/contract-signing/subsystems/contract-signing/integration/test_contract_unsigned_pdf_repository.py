"""
File: test_contract_unsigned_pdf_repository.py
Description: 驗證未簽契約 PDF MySQL adapter 的 current identity、opaque storage 與 audit 邊界。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from shared_kernel.identities import ActorContext
from infrastructure.db.contract_unsigned_pdf_repository import (
    MySqlContractUnsignedPdfRepository,
)
from subsystems.contract_signing.unsigned_contract_pdf import (
    UnsignedContractPdfDownloadAudit,
    UnsignedContractPdfError,
)
from subsystems.contract_signing.unsigned_contract_pdf_persistence import (
    UnsignedContractPdfPersistenceSource,
)
from subsystems.controlled_files.workflow import (
    ControlledFileApplyOutcome,
    ControlledFileApplyReceipt,
    ControlledFileOwner,
    ControlledFilePurpose,
    ControlledFileReadback,
)


_DIGEST = "a" * 64


class _Cursor:
    def __init__(self, rows, insert_ids=()):
        self._rows = rows
        self._insert_ids = list(insert_ids)
        self.executions: list[tuple[str, tuple[object, ...]]] = []
        self.lastrowid = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, parameters):
        self.executions.append((sql, tuple(parameters)))
        if sql.startswith("INSERT") and self._insert_ids:
            self.lastrowid = self._insert_ids.pop(0)

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None


class _Connection:
    def __init__(self, rows, insert_ids=()):
        self.cursor_instance = _Cursor(rows, insert_ids)
        self.commit_calls = 0
        self.rollback_calls = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1


def test_load_current_pdf_constrains_case_document_role_current_and_controlled_object():
    connection = _Connection(
        [
            {
                "case_no": "CASE-1",
                "document_version_id": 41,
                "document_role": "template_generated",
                "file_id": "cf_" + "c" * 32,
                "original_filename": "unsigned-contract.pdf",
                "mime_type": "application/pdf",
                "file_size": 18,
                "sha256": _DIGEST,
            }
        ]
    )

    result = MySqlContractUnsignedPdfRepository(connection).load_current_pdf("CASE-1", 41)

    assert result is not None
    assert result.object_reference == "cf_" + "c" * 32
    sql, parameters = connection.cursor_instance.executions[0]
    assert "document.case_no=%s" in sql
    assert "document.id=%s" in sql
    assert "document.document_role='template_generated'" in sql
    assert "newer.version_number>document.version_number" in sql
    assert "object_row.purpose='unsigned_contract'" in sql
    assert "object_row.opaque_object_id=asset.storage_key" in sql
    assert "document.replaces_document_version_id" in sql
    assert sql.count("COLLATE utf8mb4_unicode_ci") == 2
    assert parameters == ("CASE-1", 41)
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0


def test_load_render_source_reads_the_current_immutable_xlsx_document():
    workbook = b"PK\x03\x04immutable-workbook"
    connection = _Connection(
        [
            {
                "case_no": "CASE-1",
                "document_version_id": 41,
                "document_scope": "staff_segment",
                "document_role": "template_generated",
                "matching_plan_id": 9,
                "matching_segment_id": 12,
                "template_key": "staff-contract-v1",
                "template_sha256": _DIGEST,
                "mapping_sha256": "b" * 64,
                "storage_key": "contracts/source.xlsx",
                "original_filename": "CASE-1-staff-contract.xlsx",
                "file_size": len(workbook),
                "sha256": _DIGEST,
            },
        ]
    )
    reads = []

    def read_archive(**kwargs):
        reads.append(kwargs)
        return workbook

    result = MySqlContractUnsignedPdfRepository(
        connection,
        archive_root=Path("/safe/archive"),
        archive_reader=read_archive,
    ).load_render_source("CASE-1", 41)

    assert result is not None
    assert result.source_content == workbook
    assert result.source_filename == "CASE-1-staff-contract.xlsx"
    assert reads == [{
        "storage_root": Path("/safe/archive"),
        "storage_key": "contracts/source.xlsx",
        "expected_sha256": _DIGEST,
    }]
    source_sql, source_parameters = connection.cursor_instance.executions[0]
    assert "asset.mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'" in source_sql
    assert "document.document_role='template_generated'" in source_sql
    assert "newer.version_number>document.version_number" in source_sql
    assert source_parameters == ("CASE-1", 41)


def test_invalid_persisted_pdf_metadata_is_typed_and_does_not_leak_locator():
    connection = _Connection(
        [
            {
                "case_no": "CASE-1",
                "document_version_id": 41,
                "document_role": "template_generated",
                "file_id": "/nas/private/unsigned.pdf",
                "original_filename": "unsigned-contract.pdf",
                "mime_type": "application/pdf",
                "file_size": 18,
                "sha256": _DIGEST,
            }
        ]
    )

    with pytest.raises(UnsignedContractPdfError) as captured:
        MySqlContractUnsignedPdfRepository(connection).load_current_pdf("CASE-1", 41)

    assert captured.value.code == "contract_pdf_persisted_metadata_invalid"
    assert "/nas/" not in str(captured.value)


def test_register_persisted_pdf_uses_exact_controlled_lineage_without_commit():
    file_id = "cf_" + "c" * 32
    connection = _Connection(
        [
            None,
            {
                "file_id": file_id,
                "filename": "unsigned.pdf",
                "content_type": "application/pdf",
                "size_bytes": 18,
                "content_sha256": _DIGEST,
            },
        ],
        insert_ids=(51, 52),
    )
    repository = MySqlContractUnsignedPdfRepository(connection, storage_provider="nas")
    readback = ControlledFileReadback(
        file_id=file_id,
        owner=ControlledFileOwner.CONTRACT_SIGNING,
        purpose=ControlledFilePurpose.UNSIGNED_CONTRACT,
        subject_reference="CASE-1",
        filename="unsigned.pdf",
        logical_folder="contracts/unsigned",
        version=1,
        sha256_digest=_DIGEST,
        mime_type="application/pdf",
        size_bytes=18,
        status="active",
        applied_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
    )
    receipt = ControlledFileApplyReceipt(
        "cfr_" + "e" * 32,
        ControlledFileApplyOutcome.CREATED,
        readback,
    )
    source = UnsignedContractPdfPersistenceSource(
        case_no="CASE-1",
        document_version_id=41,
        document_scope="staff_segment",
        matching_plan_id=9,
        matching_segment_id=12,
        document_target_key="staff-segment:12",
        template_key="staff-contract-v1",
        template_sha256="a" * 64,
        mapping_sha256="b" * 64,
        facts_snapshot_sha256="d" * 64,
        version_number=3,
        is_current=True,
    )

    result = repository.register_persisted_pdf(
        source=source,
        controlled_file_receipt=receipt,
        renderer_identity="libreoffice-headless-v1",
        actor=ActorContext("admin:7"),
    )

    assert result == 52
    controlled_sql, controlled_parameters = connection.cursor_instance.executions[1]
    asset_sql, asset_parameters = connection.cursor_instance.executions[2]
    document_sql, document_parameters = connection.cursor_instance.executions[3]
    assert "purpose='unsigned_contract'" in controlled_sql
    assert controlled_parameters == (
        file_id,
        "CASE-1",
        "unsigned-contract:41:libreoffice-headless-v1",
    )
    assert "INSERT INTO media_assets" in asset_sql
    assert "nas" in asset_parameters
    assert "INSERT INTO contract_document_versions" in document_sql
    assert 41 in document_parameters
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0


def test_register_persisted_pdf_replays_the_existing_document_for_the_same_controlled_file():
    connection = _Connection([{"document_version_id": 52}])
    repository = MySqlContractUnsignedPdfRepository(connection, storage_provider="nas")
    readback = ControlledFileReadback(
        file_id="cf_" + "d" * 32,
        owner=ControlledFileOwner.CONTRACT_SIGNING,
        purpose=ControlledFilePurpose.UNSIGNED_CONTRACT,
        subject_reference="CASE-1",
        filename="unsigned.pdf",
        logical_folder="contracts/unsigned",
        version=1,
        sha256_digest=_DIGEST,
        mime_type="application/pdf",
        size_bytes=18,
        status="active",
        applied_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
    )
    receipt = ControlledFileApplyReceipt(
        "cfr_" + "e" * 32,
        ControlledFileApplyOutcome.REPLAYED,
        readback,
    )
    source = UnsignedContractPdfPersistenceSource(
        case_no="CASE-1",
        document_version_id=41,
        document_scope="staff_segment",
        matching_plan_id=9,
        matching_segment_id=12,
        document_target_key="staff-segment:12",
        template_key="staff-contract-v1",
        template_sha256="a" * 64,
        mapping_sha256="b" * 64,
        facts_snapshot_sha256="d" * 64,
        version_number=3,
        is_current=True,
    )

    result = repository.register_persisted_pdf(
        source=source,
        controlled_file_receipt=receipt,
        renderer_identity="libreoffice-headless-v1",
        actor=ActorContext("admin:7"),
    )

    assert result == 52
    assert len(connection.cursor_instance.executions) == 1
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0


def test_lock_source_uses_case_then_source_then_current_target_lock_order():
    connection = _Connection(
        [
            {"case_no": "CASE-1"},
            {
                "document_scope": "staff_segment",
                "matching_plan_id": 9,
                "matching_segment_id": 12,
                "document_target_key": "staff-segment:12",
                "template_key": "staff-contract-v1",
                "template_sha256": "a" * 64,
                "mapping_sha256": "b" * 64,
                "facts_snapshot_sha256": "d" * 64,
                "version_number": 3,
            },
            {"document_version_id": 41},
        ]
    )

    result = MySqlContractUnsignedPdfRepository(connection).lock_source_for_persistence(
        "CASE-1", 41
    )

    assert result.is_current is True
    statements = connection.cursor_instance.executions
    assert "FROM orders" in statements[0][0]
    assert "FOR UPDATE" in statements[0][0]
    assert "FROM contract_document_versions" in statements[1][0]
    assert statements[1][1] == ("CASE-1", 41)
    assert "ORDER BY version_number DESC" in statements[2][0]
    assert statements[2][1] == ("CASE-1", "staff_segment", "staff-segment:12")


def test_append_audit_uses_borrowed_transaction_and_excludes_locator_and_digest():
    connection = _Connection([])
    repository = MySqlContractUnsignedPdfRepository(connection)

    repository.append_durable_download_audit(
        UnsignedContractPdfDownloadAudit(
            case_no="CASE-1",
            document_version_id=41,
            actor_id="admin:7",
            correlation_id="corr-1",
            filename="unsigned-contract.pdf",
            mime_type="application/pdf",
            size_bytes=18,
        )
    )

    sql, parameters = connection.cursor_instance.executions[0]
    assert "INSERT INTO admin_audit_logs" in sql
    assert parameters[0] == 7
    assert "contract_unsigned_pdf_downloaded" in parameters
    assert all("storage" not in str(value).lower() for value in parameters)
    assert all(_DIGEST not in str(value) for value in parameters)
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0


def test_append_audit_records_explicit_local_bypass_as_system_actor():
    connection = _Connection([])
    repository = MySqlContractUnsignedPdfRepository(connection)

    repository.append_durable_download_audit(
        UnsignedContractPdfDownloadAudit(
            case_no="CASE-1",
            document_version_id=41,
            actor_id="system:local_bypass",
            correlation_id="corr-local-1",
            filename="unsigned-contract.pdf",
            mime_type="application/pdf",
            size_bytes=18,
        )
    )

    sql, parameters = connection.cursor_instance.executions[0]
    assert "INSERT INTO admin_audit_logs" in sql
    assert parameters[0] is None
    assert "contract_unsigned_pdf_downloaded" in parameters
