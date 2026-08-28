"""
File: contract_unsigned_pdf_repository.py
Description: 以 caller-owned MySQL 交易鎖定、保存與讀取 current controlled 未簽契約 PDF 並追加 audit。
"""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from shared_kernel.identities import ActorContext
from subsystems.contract_signing.unsigned_contract_pdf import (
    StoredUnsignedContractPdf,
    UnsignedContractPdfDownloadAudit,
    UnsignedContractPdfError,
    UnsignedContractRenderSource,
)
from subsystems.contract_signing.unsigned_contract_pdf_persistence import (
    UnsignedContractPdfPersistenceSource,
)
from subsystems.controlled_files.workflow import (
    ControlledFileApplyReceipt,
    ControlledFileOwner,
    ControlledFilePurpose,
    ControlledFileReadback,
)


_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class MySqlContractUnsignedPdfRepository:
    """Borrowed-connection adapter; outer composition owns commit, rollback and close."""

    def __init__(self, connection: Any, *, storage_provider: str = "local") -> None:
        if storage_provider not in {"local", "nas"}:
            raise ValueError("unsigned PDF storage provider is invalid")
        self._connection = connection
        self._storage_provider = storage_provider

    def load_render_source(
        self, case_no: str, document_version_id: int
    ) -> UnsignedContractRenderSource | None:
        row = self._one(_RENDER_SOURCE_SQL, (case_no, document_version_id))
        if row is None:
            return None
        try:
            scope = str(row["document_scope"])
            if scope == "staff_segment":
                facts = self._one(
                    _STAFF_FACTS_SQL,
                    (
                        int(row["matching_segment_id"]),
                        int(row["matching_plan_id"]),
                        case_no,
                    ),
                )
            elif scope == "client_contract":
                facts = self._one(
                    _CLIENT_FACTS_SQL,
                    (int(row["matching_plan_id"]), case_no),
                )
            else:
                raise ValueError("unknown document scope")
            if facts is None:
                raise ValueError("render facts missing")
            return UnsignedContractRenderSource(
                case_no=str(row["case_no"]),
                document_version_id=int(row["document_version_id"]),
                document_role=str(row["document_role"]),
                is_current=True,
                template_key=str(row["template_key"]),
                template_sha256=str(row["template_sha256"]),
                mapping_sha256=str(row["mapping_sha256"]),
                facts=dict(facts),
            )
        except (KeyError, TypeError, ValueError):
            raise _metadata_error("contract_pdf_render_source_invalid") from None

    def load_current_pdf(
        self, case_no: str, document_version_id: int
    ) -> StoredUnsignedContractPdf | None:
        row = self._one(_CURRENT_PDF_SQL, (case_no, document_version_id))
        if row is None:
            return None
        try:
            return StoredUnsignedContractPdf(
                case_no=str(row["case_no"]),
                document_version_id=int(row["document_version_id"]),
                document_role=str(row["document_role"]),
                is_current=True,
                object_reference=str(row["file_id"]),
                filename=str(row["original_filename"]),
                mime_type=str(row["mime_type"]),
                size_bytes=int(row["file_size"]),
                sha256=str(row["sha256"]),
            )
        except (KeyError, TypeError, ValueError):
            raise _metadata_error("contract_pdf_persisted_metadata_invalid") from None

    def register_persisted_pdf(
        self,
        *,
        source: UnsignedContractPdfPersistenceSource,
        controlled_file_receipt: ControlledFileApplyReceipt,
        renderer_identity: str,
        actor: ActorContext,
    ) -> int:
        readback = controlled_file_receipt.readback
        _require_unsigned_readback(
            readback,
            case_no=source.case_no,
        )
        existing = self._one(
            _EXISTING_PDF_BY_FILE_SQL,
            (readback.file_id, source.case_no, source.document_version_id),
        )
        if existing is not None:
            try:
                return int(existing["document_version_id"])
            except (KeyError, TypeError, ValueError):
                raise _metadata_error("contract_pdf_persisted_metadata_invalid") from None
        if not source.is_current:
            raise UnsignedContractPdfError(
                category="conflict",
                code="contract_pdf_document_stale",
                message="未簽契約來源已不是 current template-generated 文件。",
            )
        controlled = self._one(
            _CONTROLLED_UNSIGNED_PDF_SQL,
            (
                readback.file_id,
                source.case_no,
                _object_key(source.document_version_id, renderer_identity),
            ),
        )
        try:
            if controlled is None or not _controlled_matches_readback(controlled, readback):
                raise ValueError("controlled PDF mismatch")
            media_asset_id = self._insert(
                _MEDIA_ASSET_INSERT_SQL,
                (
                    source.case_no,
                    self._storage_provider,
                    readback.file_id,
                    readback.filename,
                    readback.mime_type,
                    readback.size_bytes,
                    readback.sha256_digest,
                ),
            )
            return self._insert(
                _DOCUMENT_INSERT_SQL,
                (
                    source.case_no,
                    source.document_scope,
                    source.matching_plan_id,
                    source.matching_segment_id,
                    source.document_target_key,
                    source.template_key,
                    source.template_sha256,
                    source.mapping_sha256,
                    source.facts_snapshot_sha256,
                    media_asset_id,
                    source.version_number + 1,
                    source.document_version_id,
                    actor.actor_id,
                ),
            )
        except UnsignedContractPdfError:
            raise
        except (KeyError, TypeError, ValueError):
            raise _metadata_error("contract_pdf_persistence_lineage_invalid") from None

    def lock_source_for_persistence(
        self, case_no: str, source_document_version_id: int
    ) -> UnsignedContractPdfPersistenceSource:
        case = self._one(_CASE_LOCK_SQL, (case_no,))
        source = self._one(
            _PERSISTENCE_SOURCE_LOCK_SQL,
            (case_no, source_document_version_id),
        )
        if case is None or source is None:
            raise UnsignedContractPdfError(
                category="not_found",
                code="contract_pdf_source_not_found",
                message="找不到未簽契約來源。",
            )
        try:
            current = self._one(
                _CURRENT_TARGET_DOCUMENT_LOCK_SQL,
                (
                    case_no,
                    str(source["document_scope"]),
                    str(source["document_target_key"]),
                ),
            )
            return UnsignedContractPdfPersistenceSource(
                case_no=case_no,
                document_version_id=source_document_version_id,
                document_scope=str(source["document_scope"]),
                matching_plan_id=int(source["matching_plan_id"]),
                matching_segment_id=(
                    None
                    if source["matching_segment_id"] is None
                    else int(source["matching_segment_id"])
                ),
                document_target_key=str(source["document_target_key"]),
                template_key=str(source["template_key"]),
                template_sha256=str(source["template_sha256"]),
                mapping_sha256=str(source["mapping_sha256"]),
                facts_snapshot_sha256=str(source["facts_snapshot_sha256"]),
                version_number=int(source["version_number"]),
                is_current=(
                    current is not None
                    and int(current["document_version_id"])
                    == source_document_version_id
                ),
            )
        except (KeyError, TypeError, ValueError):
            raise _metadata_error("contract_pdf_persistence_lineage_invalid") from None

    def append_durable_download_audit(
        self, audit: UnsignedContractPdfDownloadAudit
    ) -> None:
        try:
            admin_user_id = _admin_user_id(audit.actor_id)
            details = json.dumps(
                {
                    "schema": "contract-unsigned-pdf-download-audit.v1",
                    "case_no": audit.case_no,
                    "correlation_id": audit.correlation_id,
                    "document_version_id": audit.document_version_id,
                    "filename": audit.filename,
                    "mime_type": audit.mime_type,
                    "size_bytes": audit.size_bytes,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            raise _metadata_error("contract_pdf_download_audit_invalid") from None
        self._execute(
            _AUDIT_INSERT_SQL,
            (
                admin_user_id,
                "contract_unsigned_pdf_downloaded",
                "contract_document_version",
                str(audit.document_version_id),
                200,
                details,
            ),
        )

    def _one(
        self, sql: str, parameters: tuple[object, ...]
    ) -> Mapping[str, object] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            row = cursor.fetchone()
        return row

    def _execute(self, sql: str, parameters: tuple[object, ...]) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(sql, parameters)

    def _insert(self, sql: str, parameters: tuple[object, ...]) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            return int(cursor.lastrowid)


def _admin_user_id(actor_id: str) -> int:
    prefix, separator, value = actor_id.partition(":")
    if prefix != "admin" or separator != ":" or not value.isascii() or not value.isdigit():
        raise ValueError("invalid persisted admin actor")
    identifier = int(value)
    if identifier <= 0:
        raise ValueError("invalid persisted admin actor")
    return identifier


def _object_key(source_document_version_id: int, renderer_identity: str) -> str:
    return f"unsigned-contract:{source_document_version_id}:{renderer_identity}"


def _require_unsigned_readback(
    readback: ControlledFileReadback,
    *,
    case_no: str,
) -> None:
    if (
        readback.owner is not ControlledFileOwner.CONTRACT_SIGNING
        or readback.purpose is not ControlledFilePurpose.UNSIGNED_CONTRACT
        or readback.subject_reference != case_no
        or readback.mime_type != "application/pdf"
        or readback.size_bytes <= 0
        or not readback.filename.lower().endswith(".pdf")
    ):
        raise _metadata_error("contract_pdf_controlled_file_invalid")


def _controlled_matches_readback(
    row: Mapping[str, object], readback: ControlledFileReadback
) -> bool:
    return (
        str(row["file_id"]) == readback.file_id
        and str(row["filename"]) == readback.filename
        and str(row["content_type"]) == readback.mime_type
        and int(row["size_bytes"]) == readback.size_bytes
        and str(row["content_sha256"]) == readback.sha256_digest
    )


def _metadata_error(code: str) -> UnsignedContractPdfError:
    return UnsignedContractPdfError(
        category="domain_blocked",
        code=code,
        message="未簽契約 PDF 的保存資料無效。",
    )


_CURRENT_PREDICATE = (
    "NOT EXISTS (SELECT 1 FROM contract_document_versions newer WHERE "
    "newer.case_no=document.case_no AND newer.document_scope=document.document_scope "
    "AND newer.document_target_key=document.document_target_key "
    "AND newer.document_role='template_generated' "
    "AND newer.version_number>document.version_number)"
)
_RENDER_SOURCE_SQL = (
    "SELECT document.case_no,document.id AS document_version_id,document.document_scope,"
    "document.document_role,document.matching_plan_id,document.matching_segment_id,"
    "document.template_key,document.template_sha256,document.mapping_sha256 "
    "FROM contract_document_versions document JOIN media_assets asset "
    "ON asset.id=document.media_asset_id "
    "WHERE document.case_no=%s AND document.id=%s "
    "AND document.document_role='template_generated' "
    "AND document.source_document_version_id IS NULL "
    "AND asset.category='contract' AND asset.deleted_at IS NULL "
    f"AND asset.mime_type='{_XLSX_MEDIA_TYPE}' AND {_CURRENT_PREDICATE}"
)
_STAFF_FACTS_SQL = (
    "SELECT order_row.case_no,order_row.start_date,order_row.end_date,order_row.service_days,"
    "client.name AS client_name,client.city,client.address,client.service_time,client.service_type,"
    "staff.name AS staff_name,staff.phone AS staff_phone "
    "FROM caregiver_matching_plan_segments segment "
    "JOIN staff ON staff.id=segment.staff_id "
    "JOIN orders order_row ON segment.id=%s AND segment.plan_id=%s "
    "JOIN clients client ON client.case_no=order_row.case_no "
    "WHERE order_row.case_no=%s"
)
_CLIENT_FACTS_SQL = (
    "SELECT order_row.case_no,order_row.service_days,order_row.service_hours_per_day,"
    "order_row.floor_fee,client.name AS client_name,client.phone,client.address,"
    "client.service_time,client.service_type,client.baby_info,client.notes,"
    "MIN(day_row.service_date) AS committed_service_start_date,"
    "MAX(day_row.service_date) AS committed_service_end_date "
    "FROM orders order_row JOIN clients client ON client.case_no=order_row.case_no "
    "JOIN precontract_service_commitments commitment "
    "ON commitment.case_no=order_row.case_no AND commitment.matching_plan_id=%s "
    "JOIN precontract_service_commitment_days day_row ON day_row.commitment_id=commitment.id "
    "WHERE order_row.case_no=%s"
)
_CURRENT_PDF_SQL = (
    "SELECT document.case_no,document.id AS document_version_id,document.document_role,"
    "object_row.opaque_object_id AS file_id,asset.original_filename,asset.mime_type,"
    "asset.file_size,asset.sha256 "
    "FROM contract_document_versions document JOIN media_assets asset "
    "ON asset.id=document.media_asset_id JOIN controlled_file_objects object_row "
    "ON object_row.opaque_object_id=asset.storage_key "
    "AND object_row.owner_type='contract_signing' "
    "AND object_row.purpose='unsigned_contract' "
    "AND object_row.subject_reference=document.case_no "
    "AND object_row.filename=asset.original_filename "
    "AND object_row.content_type=asset.mime_type "
    "AND object_row.size_bytes=asset.file_size "
    "AND object_row.content_sha256=asset.sha256 "
    "AND object_row.object_key COLLATE utf8mb4_unicode_ci LIKE "
    "CONCAT('unsigned-contract:',CAST(document.replaces_document_version_id AS CHAR),':%%') "
    "COLLATE utf8mb4_unicode_ci "
    "WHERE document.case_no=%s AND document.id=%s "
    "AND document.document_role='template_generated' "
    "AND document.source_document_version_id IS NULL "
    "AND document.replaces_document_version_id IS NOT NULL "
    "AND asset.category='contract' AND asset.owner_type='contract_signing' "
    "AND asset.deleted_at IS NULL AND asset.storage_provider IN ('local','nas') "
    "AND asset.mime_type='application/pdf' "
    f"AND {_CURRENT_PREDICATE}"
)
_EXISTING_PDF_BY_FILE_SQL = (
    "SELECT document.id AS document_version_id FROM contract_document_versions document "
    "JOIN media_assets asset ON asset.id=document.media_asset_id "
    "WHERE asset.storage_key=%s AND document.case_no=%s "
    "AND document.replaces_document_version_id=%s "
    "AND document.document_role='template_generated' "
    "AND asset.mime_type='application/pdf'"
)
_CASE_LOCK_SQL = "SELECT case_no FROM orders WHERE case_no=%s FOR UPDATE"
_PERSISTENCE_SOURCE_LOCK_SQL = (
    "SELECT document.document_scope,document.matching_plan_id,document.matching_segment_id,"
    "document.document_target_key,document.template_key,document.template_sha256,"
    "document.mapping_sha256,document.facts_snapshot_sha256,document.version_number "
    "FROM contract_document_versions document JOIN media_assets asset "
    "ON asset.id=document.media_asset_id "
    "WHERE document.case_no=%s AND document.id=%s "
    "AND document.document_role='template_generated' "
    "AND document.source_document_version_id IS NULL "
    f"AND asset.mime_type='{_XLSX_MEDIA_TYPE}' FOR UPDATE"
)
_CURRENT_TARGET_DOCUMENT_LOCK_SQL = (
    "SELECT id AS document_version_id FROM contract_document_versions "
    "WHERE case_no=%s AND document_scope=%s AND document_target_key=%s "
    "AND document_role='template_generated' "
    "ORDER BY version_number DESC,id DESC LIMIT 1 FOR UPDATE"
)
_CONTROLLED_UNSIGNED_PDF_SQL = (
    "SELECT opaque_object_id AS file_id,filename,content_type,size_bytes,content_sha256 "
    "FROM controlled_file_objects WHERE opaque_object_id=%s "
    "AND owner_type='contract_signing' AND purpose='unsigned_contract' "
    "AND subject_reference=%s AND object_key=%s FOR UPDATE"
)
_MEDIA_ASSET_INSERT_SQL = (
    "INSERT INTO media_assets "
    "(category,owner_type,owner_id,storage_provider,storage_key,original_filename,"
    "mime_type,file_size,sha256) VALUES "
    "('contract','contract_signing',%s,%s,%s,%s,%s,%s,%s)"
)
_DOCUMENT_INSERT_SQL = (
    "INSERT INTO contract_document_versions "
    "(case_no,document_scope,document_role,matching_plan_id,matching_segment_id,"
    "document_target_key,template_key,template_sha256,mapping_sha256,facts_snapshot_sha256,"
    "media_asset_id,version_number,replaces_document_version_id,created_by) VALUES "
    "(%s,%s,'template_generated',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_AUDIT_INSERT_SQL = (
    "INSERT INTO admin_audit_logs "
    "(admin_user_id,action,resource_type,resource_id,result_status,details_json) "
    "VALUES (%s,%s,%s,%s,%s,%s)"
)


__all__ = ["MySqlContractUnsignedPdfRepository"]
