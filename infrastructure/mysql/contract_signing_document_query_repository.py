"""MySQL adapter for the bounded Contract Signing document download query."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from infrastructure.mysql.line_repository_support import optional_row
from subsystems.contract_signing.document_query import (
    ContractSigningDocument,
    ContractSigningDocumentDownload,
    ContractSigningStaffSegment,
    ContractSigningStatus,
)


_DOCUMENT_FOR_DOWNLOAD_SQL = """
SELECT document.case_no,
       document.id AS document_version_id,
       asset.storage_key,
       asset.sha256,
       asset.mime_type,
       asset.original_filename
  FROM contract_document_versions document
  JOIN media_assets asset ON asset.id = document.media_asset_id
 WHERE document.case_no = %s
   AND document.id = %s
"""

_ORDER_SQL = "SELECT contract_identity FROM orders WHERE case_no=%s"
_STAFF_SEGMENTS_SQL = (
    "SELECT segment.id AS segment_id,segment.staff_id, "
    "EXISTS(SELECT 1 FROM contract_signing_events event "
    "JOIN contract_document_versions document ON document.id=event.document_version_id "
    "WHERE event.matching_segment_id=segment.id AND event.event_type='sent' "
    "AND document.document_scope='staff_segment') AS sent, "
    "EXISTS(SELECT 1 FROM contract_signing_events event "
    "JOIN contract_document_versions document ON document.id=event.document_version_id "
    "WHERE event.matching_segment_id=segment.id AND event.event_type='signed_received' "
    "AND document.document_scope='staff_segment') AS signed_received "
    "FROM caregiver_matching_plan_segments segment "
    "JOIN caregiver_matching_plans plan ON plan.id=segment.plan_id "
    "WHERE plan.case_no=%s ORDER BY segment.segment_order,segment.id"
)
_COMMITMENT_SQL = "SELECT id FROM precontract_service_commitments WHERE case_no=%s"
_CLIENT_EVENTS_SQL = (
    "SELECT event.event_type FROM contract_signing_events event "
    "JOIN contract_document_versions document ON document.id=event.document_version_id "
    "WHERE event.case_no=%s AND document.document_scope='client_contract' ORDER BY event.id"
)
_DOCUMENTS_SQL = (
    "SELECT document.id,document.document_scope,document.document_role,"
    "document.document_target_key,document.version_number,document.template_key,"
    "document.template_sha256,document.mapping_sha256,asset.sha256 AS archive_sha256,"
    "asset.mime_type,asset.file_size FROM contract_document_versions document "
    "JOIN media_assets asset ON asset.id=document.media_asset_id "
    "WHERE document.case_no=%s ORDER BY document.id"
)


class MySqlContractSigningDocumentQueryRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def find_document_for_download(
        self, case_no: str, document_version_id: int
    ) -> ContractSigningDocumentDownload | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_DOCUMENT_FOR_DOWNLOAD_SQL, (case_no, document_version_id))
            row = optional_row(cursor.fetchone())
        return None if row is None else _document(row)

    def find_status(self, case_no: str) -> ContractSigningStatus | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_ORDER_SQL, (case_no,))
            order = optional_row(cursor.fetchone())
            if order is None:
                return None
            cursor.execute(_STAFF_SEGMENTS_SQL, (case_no,))
            staff_segments = tuple(_staff_segment(row) for row in (cursor.fetchall() or ()))
            cursor.execute(_COMMITMENT_SQL, (case_no,))
            commitment = optional_row(cursor.fetchone())
            cursor.execute(_CLIENT_EVENTS_SQL, (case_no,))
            client_events = tuple(
                _required_text(row, "event_type") for row in (cursor.fetchall() or ())
            )
            cursor.execute(_DOCUMENTS_SQL, (case_no,))
            documents = tuple(_status_document(row) for row in (cursor.fetchall() or ()))
        return ContractSigningStatus(
            case_no=case_no,
            staff_segments=staff_segments,
            commitment_id=None if commitment is None else _required_int(commitment, "id"),
            client_document_sent="sent" in client_events,
            client_signed_received="signed_received" in client_events,
            contract_identity=_optional_text(order, "contract_identity"),
            documents=documents,
        )


def _document(row: Mapping[str, object]) -> ContractSigningDocumentDownload:
    return ContractSigningDocumentDownload(
        case_no=_required_text(row, "case_no"),
        document_version_id=_required_int(row, "document_version_id"),
        storage_key=_required_text(row, "storage_key"),
        sha256=_required_text(row, "sha256"),
        mime_type=_required_text(row, "mime_type"),
        original_filename=_required_text(row, "original_filename"),
    )


def _staff_segment(row: Mapping[str, object]) -> ContractSigningStaffSegment:
    return ContractSigningStaffSegment(
        segment_id=_required_int(row, "segment_id"),
        staff_id=_required_int(row, "staff_id"),
        sent=bool(row.get("sent")),
        signed_received=bool(row.get("signed_received")),
    )


def _status_document(row: Mapping[str, object]) -> ContractSigningDocument:
    scope = _required_text(row, "document_scope")
    role = _required_text(row, "document_role")
    if scope not in {"staff_segment", "client_contract"}:
        raise ValueError("contract signing document scope is invalid")
    if role not in {"template_generated", "signed_return"}:
        raise ValueError("contract signing document role is invalid")
    return ContractSigningDocument(
        document_version_id=_required_int(row, "id"),
        scope=scope,
        role=role,
        target_key=_required_text(row, "document_target_key"),
        version_number=_required_int(row, "version_number"),
        template_key=_optional_text(row, "template_key"),
        template_sha256=_optional_text(row, "template_sha256"),
        mapping_sha256=_optional_text(row, "mapping_sha256"),
        archive_sha256=_required_text(row, "archive_sha256"),
        mime_type=_required_text(row, "mime_type"),
        file_size=_required_int(row, "file_size"),
    )


def _required_text(row: Mapping[str, object], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str):
        raise ValueError(f"contract signing document {field} is invalid")
    return value


def _optional_text(row: Mapping[str, object], field: str) -> str | None:
    value = row.get(field)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"contract signing document {field} is invalid")
    return value


def _required_int(row: Mapping[str, object], field: str) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"contract signing document {field} is invalid")
    return value


__all__ = ["MySqlContractSigningDocumentQueryRepository"]
