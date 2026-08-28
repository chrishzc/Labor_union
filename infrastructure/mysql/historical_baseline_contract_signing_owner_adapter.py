"""Read Contract Signing HCAT v2 roots through a caller-owned MySQL connection."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from domains.orders.historical_operational_baseline import (
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    HistoricalBaselineOwnerObservation,
    HistoricalBaselineOwnerRootDescriptor,
    HistoricalOrderIdentity,
)
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.contract_signing.external_signing_contracts import (
    ExternalCompletionReportScope,
    LegacyManualSigningEvidence,
)
from subsystems.orders.historical_baseline_owner_vector import (
    HistoricalBaselineOwnerObservationReadback,
)


_DESCRIPTORS = {
    item.root_identity_kind: item
    for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    if item.owner_domain == "contract_signing"
}
_SESSION_STATES = {
    "staff_reporting",
    "staff_reports_complete",
    "client_reported_final_pdf_pending",
    "completed",
}
_MANUAL_CONFIRMATION_METHODS = {"phone", "paper", "in_person", "verified_other"}
_HEX_DIGEST_LENGTH = 64
_MAX_BIGINT = 9_223_372_036_854_775_807


_SESSION_SQL = """
SELECT id AS session_db_id,external_signing_session_id,case_no,matching_plan_id,
       current_document_set_sha256,commitment_id,session_state,aggregate_version
FROM contract_external_signing_sessions
WHERE case_no=%s AND session_state<>'superseded'
ORDER BY id
"""

_STAFF_REPORT_SQL = """
SELECT segment.id AS segment_id,segment.plan_id AS segment_plan_id,
       segment.staff_id AS segment_staff_id,
       plan.case_no AS plan_case_no,plan.status AS plan_status,plan.is_active AS plan_is_active,
       report.id AS report_db_id,report.report_id,report.external_signing_session_id AS report_session_db_id,
       report.case_no AS report_case_no,report.report_scope,report.matching_segment_id AS report_segment_id,
       report.document_version_id,report.source_event_identity,report.resulting_status_version,
       report.expected_status_version AS report_expected_status_version,
       report.reporter_subject_type,report.reporter_subject_reference,
       report.source_kind,report.source_payload_sha256,report.manual_confirmation_method,
       report.manual_reason,report.manual_evidence_reference,report.manual_evidence_sha256,
       document.case_no AS document_case_no,document.document_scope,document.document_role,
       document.matching_plan_id AS document_plan_id,document.matching_segment_id AS document_segment_id,
       receipt.id AS receipt_db_id,receipt.receipt_id,
       receipt.external_signing_session_id AS receipt_session_db_id,receipt.command_type,
       receipt.expected_status_version AS receipt_expected_status_version,
       receipt.result_status_version,receipt.completion_report_id,receipt.outcome_state,receipt.preview_fingerprint,
       receipt.result_snapshot AS report_result_snapshot,
       current_document.id AS current_document_version_id,
       client_document.id AS current_client_document_version_id
FROM caregiver_matching_plan_segments segment
JOIN caregiver_matching_plans plan ON plan.id=segment.plan_id
LEFT JOIN contract_external_completion_reports report
  ON report.external_signing_session_id=%s AND report.report_scope='staff'
 AND report.matching_segment_id=segment.id
LEFT JOIN contract_document_versions document ON document.id=report.document_version_id
LEFT JOIN contract_external_signing_receipts receipt ON receipt.completion_report_id=report.id
LEFT JOIN contract_document_versions current_document
  ON current_document.case_no=plan.case_no
 AND current_document.matching_plan_id=plan.id
 AND current_document.matching_segment_id=segment.id
 AND current_document.document_scope='staff_segment'
 AND current_document.document_role='template_generated'
 AND NOT EXISTS (
   SELECT 1 FROM contract_document_versions newer
   WHERE newer.case_no=current_document.case_no
     AND newer.document_scope=current_document.document_scope
     AND newer.document_target_key=current_document.document_target_key
     AND newer.document_role='template_generated'
     AND newer.version_number>current_document.version_number
 )
LEFT JOIN contract_document_versions client_document
  ON client_document.case_no=plan.case_no
 AND client_document.matching_plan_id=plan.id
 AND client_document.document_scope='client_contract'
 AND client_document.document_role='template_generated'
 AND NOT EXISTS (
   SELECT 1 FROM contract_document_versions newer_client
   WHERE newer_client.case_no=client_document.case_no
     AND newer_client.document_scope=client_document.document_scope
     AND newer_client.document_target_key=client_document.document_target_key
     AND newer_client.document_role='template_generated'
     AND newer_client.version_number>client_document.version_number
 )
WHERE segment.plan_id=%s
ORDER BY segment.id,report.id,receipt.id
"""

_COMMITMENT_SQL = """
SELECT commitment.id AS commitment_id,commitment.case_no AS commitment_case_no,
       commitment.matching_plan_id AS commitment_plan_id,commitment.commitment_key,
       commitment.plan_snapshot_sha256
FROM precontract_service_commitments commitment
WHERE commitment.id=%s
"""

_CLIENT_EVIDENCE_SQL = """
SELECT report.id AS report_db_id,report.report_id,
       report.external_signing_session_id AS report_session_db_id,
       report.case_no AS report_case_no,report.report_scope,report.matching_segment_id,
       report.document_version_id,report.commitment_id AS report_commitment_id,
       report.source_event_identity,report.resulting_status_version AS report_status_version,
       report.expected_status_version AS report_expected_status_version,
       report.reporter_subject_type,report.reporter_subject_reference,
       report.source_kind,report.source_payload_sha256,report.manual_confirmation_method,
       report.manual_reason,report.manual_evidence_reference,report.manual_evidence_sha256,
       document.case_no AS report_document_case_no,
       document.document_scope AS report_document_scope,
       document.document_role AS report_document_role,
       document.matching_plan_id AS report_document_plan_id,
       document.matching_segment_id AS report_document_segment_id,
       report_receipt.id AS report_receipt_db_id,report_receipt.receipt_id AS report_receipt_id,
       report_receipt.external_signing_session_id AS report_receipt_session_db_id,
       report_receipt.command_type AS report_receipt_command,
       report_receipt.expected_status_version AS report_receipt_expected_status_version,
       report_receipt.result_status_version AS report_receipt_status_version,
       report_receipt.completion_report_id,report_receipt.outcome_state AS report_outcome,
       report_receipt.preview_fingerprint AS report_preview_fingerprint,
       report_receipt.result_snapshot AS report_result_snapshot,
       final.id AS final_document_db_id,final.final_document_id,
       final.external_signing_session_id AS final_session_db_id,final.case_no AS final_case_no,
       final.source_document_set_sha256,final.controlled_file_object_id,
       final.version_number,final.contract_identity,final.content_type AS final_content_type,
       final.size_bytes AS final_size_bytes,final.content_sha256 AS final_sha256,
       object.id AS object_db_id,object.opaque_object_id,object.owner_type,object.subject_reference,
       object.purpose,object.content_type AS object_content_type,
       object.size_bytes AS object_size_bytes,object.content_sha256 AS object_sha256,
       final_receipt.id AS final_receipt_db_id,final_receipt.receipt_id AS final_receipt_id,
       final_receipt.external_signing_session_id AS final_receipt_session_db_id,
       final_receipt.command_type AS final_receipt_command,
       final_receipt.preview_fingerprint AS final_preview_fingerprint,
       final_receipt.expected_status_version AS final_receipt_expected_status_version,
       final_receipt.result_status_version AS final_receipt_status_version,
       final_receipt.final_document_version_id,final_receipt.outcome_state AS final_outcome,
       plan.case_no AS plan_case_no,plan.status AS plan_status,plan.is_active AS plan_is_active,
       orders.client_id AS order_client_id,
       current_client_document.id AS current_client_document_version_id
FROM contract_external_completion_reports report
JOIN contract_external_signing_sessions session
  ON session.id=report.external_signing_session_id
JOIN caregiver_matching_plans plan ON plan.id=session.matching_plan_id
JOIN orders ON orders.case_no=session.case_no
JOIN contract_document_versions document ON document.id=report.document_version_id
JOIN contract_external_signing_receipts report_receipt
  ON report_receipt.completion_report_id=report.id
JOIN contract_final_document_versions final
  ON final.external_signing_session_id=report.external_signing_session_id
JOIN controlled_file_objects object ON object.id=final.controlled_file_object_id
JOIN contract_external_signing_receipts final_receipt
  ON final_receipt.final_document_version_id=final.id
LEFT JOIN contract_document_versions current_client_document
  ON current_client_document.case_no=session.case_no
 AND current_client_document.matching_plan_id=session.matching_plan_id
 AND current_client_document.document_scope='client_contract'
 AND current_client_document.document_role='template_generated'
 AND NOT EXISTS (
   SELECT 1 FROM contract_document_versions newer_client
   WHERE newer_client.case_no=current_client_document.case_no
     AND newer_client.document_scope=current_client_document.document_scope
     AND newer_client.document_target_key=current_client_document.document_target_key
     AND newer_client.document_role='template_generated'
     AND newer_client.version_number>current_client_document.version_number
 )
WHERE report.external_signing_session_id=%s AND report.report_scope='client'
ORDER BY report.id,report_receipt.id,final.id,final_receipt.id
"""

_LEGACY_SQL = """
SELECT event.id AS event_id,event.case_no AS event_case_no,
       event.document_version_id,event.matching_plan_id AS event_plan_id,
       event.matching_segment_id AS event_segment_id,event.event_type,event.event_key,
       event.actor,event.payload,
       document.case_no AS document_case_no,document.document_scope,document.document_role,
       document.matching_plan_id AS document_plan_id,
       document.matching_segment_id AS document_segment_id,
       document.source_document_version_id,asset.sha256 AS media_sha256,
       receipt.id AS receipt_db_id,receipt.idempotency_key,receipt.command_kind,
       receipt.case_no AS receipt_case_no,receipt.document_version_id AS receipt_document_id,
       receipt.signing_event_id AS receipt_event_id,receipt.correlation_id,
       receipt.result_snapshot
FROM contract_signing_events event
JOIN contract_document_versions document ON document.id=event.document_version_id
JOIN media_assets asset ON asset.id=document.media_asset_id
LEFT JOIN contract_signing_command_receipts receipt ON receipt.signing_event_id=event.id
WHERE event.case_no=%s AND event.event_type='signed_received'
ORDER BY event.id,receipt.id
"""


class MySqlHistoricalBaselineContractSigningOwnerAdapter:
    """Read only; transaction lifecycle and lock ownership remain with the caller."""

    owner_domain = "contract_signing"

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def read_owner_observations(
        self,
        identity: HistoricalOrderIdentity,
        descriptor: HistoricalBaselineOwnerRootDescriptor,
        *,
        for_update: bool = False,
    ) -> HistoricalBaselineOwnerObservationReadback:
        if not isinstance(identity, HistoricalOrderIdentity):
            raise TypeError("historical baseline Contract Signing identity is invalid")
        expected = (
            _DESCRIPTORS.get(descriptor.root_identity_kind)
            if isinstance(descriptor, HistoricalBaselineOwnerRootDescriptor)
            else None
        )
        if expected is None or descriptor.canonical_tuple != expected.canonical_tuple:
            raise ValueError("historical_baseline_contract_signing_descriptor_unsupported")
        if not isinstance(for_update, bool):
            raise TypeError("historical baseline Contract Signing read mode is invalid")

        try:
            sessions = self._rows(_SESSION_SQL, (identity.case_no,), for_update)
            session, error = _current_session(sessions, identity.case_no)
            if error is not None:
                observations = (_unavailable(descriptor, identity, error),)
            elif session is not None:
                observations = self._read_external(identity, descriptor, session, for_update)
            else:
                observations = self._read_legacy(identity, descriptor, for_update)
        except Exception:
            observations = (
                _unavailable(
                    descriptor,
                    identity,
                    f"contract_signing_{descriptor.root_identity_kind}_read_failed",
                ),
            )
        return HistoricalBaselineOwnerObservationReadback(identity, tuple(observations))

    def _read_external(self, identity, descriptor, session, for_update):
        kind = descriptor.root_identity_kind
        if kind == "signed_staff_segment":
            return self._external_staff(identity, descriptor, session, for_update)
        if kind == "commitment":
            return self._external_commitment(identity, descriptor, session, for_update)
        return self._external_client_evidence(identity, descriptor, session, for_update)

    def _external_staff(self, identity, descriptor, session, for_update):
        rows = self._rows(
            _STAFF_REPORT_SQL,
            (session["session_db_id"], session["matching_plan_id"]),
            for_update,
        )
        legacy = (
            self._rows(_LEGACY_SQL, (identity.case_no,), for_update)
            if any(row.get("source_kind") == "manual_attested" for row in rows)
            else ()
        )
        return _staff_observations(identity, descriptor, session, rows, legacy)

    def _external_commitment(self, identity, descriptor, session, for_update):
        staff = self._external_staff(
            identity, _DESCRIPTORS["signed_staff_segment"], session, for_update
        )
        if not staff or any(not item.available or item.terminal_result is not True for item in staff):
            return (_unavailable(descriptor, identity, "contract_signing_commitment_staff_lineage_incomplete"),)
        commitment_id = _positive_int(session.get("commitment_id"))
        if commitment_id is None:
            return (_unavailable(descriptor, identity, "contract_signing_commitment_missing"),)
        rows = self._rows(_COMMITMENT_SQL, (commitment_id,), for_update)
        if len(rows) != 1:
            return (_unavailable(descriptor, identity, "contract_signing_commitment_ambiguous"),)
        row = rows[0]
        if (
            _positive_int(row.get("commitment_id")) != commitment_id
            or row.get("commitment_case_no") != identity.case_no
            or row.get("commitment_plan_id") != session.get("matching_plan_id")
            or not _text(row.get("commitment_key"))
            or not _digest(row.get("plan_snapshot_sha256"))
        ):
            return (_unavailable(descriptor, identity, "contract_signing_commitment_lineage_invalid"),)
        source = max(staff, key=lambda item: (item.source_version, item.source_event_identity))
        return (
            _available(
                descriptor,
                identity,
                f"contract_signing.commitment:{identity.case_no}:{commitment_id}",
                source.source_event_identity,
                source.source_version,
            ),
        )

    def _external_client_evidence(self, identity, descriptor, session, for_update):
        staff = self._external_staff(
            identity, _DESCRIPTORS["signed_staff_segment"], session, for_update
        )
        if not staff or any(not item.available or item.terminal_result is not True for item in staff):
            return (_unavailable(descriptor, identity, "contract_signing_client_signed_evidence_staff_lineage_incomplete"),)
        rows = self._rows(_CLIENT_EVIDENCE_SQL, (session["session_db_id"],), for_update)
        legacy = (
            self._rows(_LEGACY_SQL, (identity.case_no,), for_update)
            if any(row.get("source_kind") == "manual_attested" for row in rows)
            else ()
        )
        if len(rows) != 1:
            code = "contract_signing_client_signed_evidence_missing" if not rows else "contract_signing_client_signed_evidence_ambiguous"
            return (_unavailable(descriptor, identity, code),)
        row = rows[0]
        error = _validate_client_evidence(identity.case_no, session, row, legacy)
        if error is not None:
            return (_unavailable(descriptor, identity, error),)
        return (
            _available(
                descriptor,
                identity,
                f"contract_signing.client_signed_evidence:{identity.case_no}:{row['final_document_id']}",
                str(row["final_receipt_id"]),
                int(row["final_receipt_status_version"]),
            ),
        )

    def _read_legacy(self, identity, descriptor, for_update):
        rows = self._rows(_LEGACY_SQL, (identity.case_no,), for_update)
        error = _validate_legacy_manual(rows, identity.case_no, descriptor.root_identity_kind)
        if error is not None:
            return (_unavailable(descriptor, identity, error),)
        # Legacy receipts did not persist the Preview fingerprint.  Validating
        # their document/event/receipt tuple therefore cannot promote it to an
        # HCAT terminal observation or authorize a repair mutation.
        return (
            _unavailable(
                descriptor,
                identity,
                "contract_signing_legacy_manual_preview_fingerprint_unavailable",
            ),
        )

    def _rows(self, statement: str, parameters: tuple[Any, ...], for_update: bool):
        with self._connection.cursor() as cursor:
            cursor.execute(statement + (" FOR UPDATE" if for_update else ""), parameters)
            rows = tuple(cursor.fetchall() or ())
        if any(not isinstance(row, Mapping) for row in rows):
            raise TypeError("historical baseline Contract Signing row is invalid")
        return rows


def _current_session(rows, case_no):
    if not rows:
        return None, None
    if len(rows) != 1:
        return None, "contract_signing_external_session_ambiguous"
    row = rows[0]
    if (
        _positive_int(row.get("session_db_id")) is None
        or not _opaque_identity(row.get("external_signing_session_id"), "ces_")
        or row.get("case_no") != case_no
        or _positive_int(row.get("matching_plan_id")) is None
        or not _digest(row.get("current_document_set_sha256"))
        or row.get("session_state") not in _SESSION_STATES
        or _nonnegative_int(row.get("aggregate_version")) is None
        or (row.get("commitment_id") is not None and _positive_int(row.get("commitment_id")) is None)
    ):
        return None, "contract_signing_external_session_malformed"
    return row, None


def _staff_observations(identity, descriptor, session, rows, legacy_rows):
    if not rows:
        return (_unavailable(descriptor, identity, "contract_signing_staff_segments_missing"),)
    if session.get("session_state") == "staff_reporting":
        return (_unavailable(descriptor, identity, "contract_signing_staff_segment_session_incomplete"),)
    observations = []
    seen_segments = set()
    seen_sources = set()
    seen_versions = set()
    document_by_segment = {}
    client_document_ids = set()
    for row in rows:
        segment_id = _positive_int(row.get("segment_id"))
        report_id = _positive_int(row.get("report_db_id"))
        receipt_id = _positive_int(row.get("receipt_db_id"))
        staff_id = _positive_int(row.get("segment_staff_id"))
        if segment_id is None or staff_id is None:
            return (_unavailable(descriptor, identity, "contract_signing_staff_segment_malformed"),)
        if segment_id in seen_segments:
            return (_unavailable(descriptor, identity, "contract_signing_staff_segment_evidence_ambiguous"),)
        seen_segments.add(segment_id)
        if report_id is None or receipt_id is None:
            return (_unavailable(descriptor, identity, "contract_signing_staff_segment_evidence_missing"),)
        if (
            row.get("segment_plan_id") != session.get("matching_plan_id")
            or row.get("plan_case_no") != identity.case_no
            or row.get("plan_status") != "accepted"
            or row.get("plan_is_active") != 1
            or row.get("report_session_db_id") != session.get("session_db_id")
            or row.get("report_case_no") != identity.case_no
            or row.get("report_scope") != "staff"
            or row.get("report_segment_id") != segment_id
            or row.get("reporter_subject_type") != "staff"
            or row.get("reporter_subject_reference") != str(staff_id)
            or row.get("document_case_no") != identity.case_no
            or row.get("document_scope") != "staff_segment"
            or row.get("document_role") != "template_generated"
            or row.get("document_plan_id") != session.get("matching_plan_id")
            or row.get("document_segment_id") != segment_id
            or row.get("document_version_id") != row.get("current_document_version_id")
            or row.get("receipt_session_db_id") != session.get("session_db_id")
            or row.get("receipt_command") != "record_staff_report"
            or row.get("completion_report_id") != report_id
            or row.get("outcome_state") != "recorded"
            or row.get("preview_fingerprint") is not None
            or _nonnegative_int(row.get("resulting_status_version")) is None
            or row.get("report_expected_status_version") != row.get("resulting_status_version") - 1
            or row.get("receipt_expected_status_version") != row.get("report_expected_status_version")
            or row.get("result_status_version") != row.get("resulting_status_version")
            or not _text(row.get("source_event_identity"))
            or not _opaque_identity(row.get("report_id"), "cer_")
            or not _opaque_identity(row.get("receipt_id"), "cesr_")
            or _validate_recovery_report(
                identity.case_no,
                session,
                row,
                legacy_rows,
                ExternalCompletionReportScope.STAFF,
                segment_id,
            )
        ):
            return (_unavailable(descriptor, identity, "contract_signing_staff_segment_lineage_invalid"),)
        source_tuple = (row["source_event_identity"], row["resulting_status_version"])
        if source_tuple[0] in seen_sources or source_tuple[1] in seen_versions:
            return (_unavailable(descriptor, identity, "contract_signing_staff_segment_source_ambiguous"),)
        seen_sources.add(source_tuple[0])
        seen_versions.add(source_tuple[1])
        document_by_segment[segment_id] = row["current_document_version_id"]
        client_document_ids.add(row.get("current_client_document_version_id"))
        observations.append(
            _available(
                descriptor,
                identity,
                f"contract_signing.staff_segment:{identity.case_no}:{segment_id}",
                str(row["source_event_identity"]),
                int(row["resulting_status_version"]),
            )
        )
    expected_versions = set(range(1, len(observations) + 1))
    expected_aggregate = {
        "staff_reports_complete": len(observations),
        "client_reported_final_pdf_pending": len(observations) + 1,
        "completed": len(observations) + 2,
    }.get(session.get("session_state"))
    if seen_versions != expected_versions or session.get("aggregate_version") != expected_aggregate:
        return (_unavailable(descriptor, identity, "contract_signing_staff_segment_status_version_drift"),)
    if len(client_document_ids) != 1 or _positive_int(next(iter(client_document_ids))) is None:
        return (_unavailable(descriptor, identity, "contract_signing_document_set_incomplete"),)
    document_set = fingerprint_payload(
        {
            "case_no": identity.case_no,
            "matching_plan_id": session["matching_plan_id"],
            "staff_documents": [
                [segment_id, document_by_segment[segment_id]]
                for segment_id in sorted(document_by_segment)
            ],
            "client_document_id": next(iter(client_document_ids)),
        }
    ).value
    if document_set != session.get("current_document_set_sha256"):
        return (_unavailable(descriptor, identity, "contract_signing_document_set_stale"),)
    return tuple(observations)


def _validate_client_evidence(case_no, session, row, legacy_rows):
    session_id = session.get("session_db_id")
    commitment_id = session.get("commitment_id")
    if (
        session.get("session_state") != "completed"
        or _positive_int(commitment_id) is None
        or _positive_int(row.get("report_db_id")) is None
        or row.get("report_session_db_id") != session_id
        or row.get("report_case_no") != case_no
        or row.get("report_scope") != "client"
        or row.get("matching_segment_id") is not None
        or row.get("report_commitment_id") != commitment_id
        or row.get("reporter_subject_type") != "customer"
        or row.get("reporter_subject_reference") != str(row.get("order_client_id"))
        or not _text(row.get("source_event_identity"))
        or not _opaque_identity(row.get("report_id"), "cer_")
        or row.get("report_document_case_no") != case_no
        or row.get("report_document_scope") != "client_contract"
        or row.get("report_document_role") != "template_generated"
        or row.get("report_document_plan_id") != session.get("matching_plan_id")
        or row.get("report_document_segment_id") is not None
        or row.get("document_version_id") != row.get("current_client_document_version_id")
        or row.get("plan_case_no") != case_no
        or row.get("plan_status") != "accepted"
        or row.get("plan_is_active") != 1
        or _positive_int(row.get("order_client_id")) is None
        or row.get("report_receipt_session_db_id") != session_id
        or row.get("report_receipt_command") != "record_client_report"
        or row.get("completion_report_id") != row.get("report_db_id")
        or row.get("report_outcome") != "recorded"
        or row.get("report_preview_fingerprint") is not None
        or row.get("report_receipt_expected_status_version") != row.get("report_expected_status_version")
        or row.get("report_receipt_status_version") != row.get("report_status_version")
        or _nonnegative_int(row.get("report_status_version")) is None
        or row.get("report_expected_status_version") != row.get("report_status_version") - 1
        or row.get("final_session_db_id") != session_id
        or row.get("final_case_no") != case_no
        or row.get("source_document_set_sha256") != session.get("current_document_set_sha256")
        or row.get("owner_type") != "contract_signing"
        or row.get("subject_reference") != case_no
        or row.get("purpose") != "final_signed_contract"
        or row.get("final_content_type") != "application/pdf"
        or row.get("object_content_type") != "application/pdf"
        or row.get("final_size_bytes") != row.get("object_size_bytes")
        or _positive_int(row.get("final_size_bytes")) is None
        or row.get("final_sha256") != row.get("object_sha256")
        or not _digest(row.get("final_sha256"))
        or row.get("controlled_file_object_id") != row.get("object_db_id")
        or _positive_int(row.get("version_number")) is None
        or not _opaque_identity(row.get("final_document_id"), "cfd_")
        or not _text(row.get("contract_identity"))
        or not _opaque_identity(row.get("opaque_object_id"), "cf_")
        or row.get("final_receipt_session_db_id") != session_id
        or row.get("final_receipt_command") != "apply_final_signed_contract"
        or row.get("final_document_version_id") != row.get("final_document_db_id")
        or row.get("final_outcome") != "completed"
        or not _digest(row.get("final_preview_fingerprint"))
        or _nonnegative_int(row.get("final_receipt_status_version")) is None
        or row.get("final_receipt_status_version") != session.get("aggregate_version")
        or row.get("final_receipt_expected_status_version") != row.get("report_status_version")
        or row.get("final_receipt_status_version") != row.get("report_status_version") + 1
        or not _opaque_identity(row.get("report_receipt_id"), "cesr_")
        or not _opaque_identity(row.get("final_receipt_id"), "cesr_")
        or _validate_recovery_report(
            case_no,
            session,
            row,
            legacy_rows,
            ExternalCompletionReportScope.CLIENT,
            None,
        )
    ):
        return "contract_signing_client_signed_evidence_lineage_invalid"
    return None


def _validate_recovery_report(case_no, session, row, legacy_rows, scope, segment_id):
    source_kind = row.get("source_kind")
    if source_kind == "verified_line":
        return None
    if source_kind != "manual_attested":
        return "contract_signing_recovery_source_kind_invalid"
    snapshot = _json_object(row.get("report_result_snapshot"))
    recovery = snapshot.get("recovery") if isinstance(snapshot, Mapping) else None
    current = recovery.get("current") if isinstance(recovery, Mapping) else None
    legacy = recovery.get("legacy") if isinstance(recovery, Mapping) else None
    if (
        not isinstance(recovery, Mapping)
        or recovery.get("kind") != "contract_legacy_manual_recovery.v1"
        or not _digest(recovery.get("preview_fingerprint"))
        or recovery.get("scope") != scope.value
        or recovery.get("matching_segment_id") != segment_id
        or recovery.get("confirmation_method") != row.get("manual_confirmation_method")
        or recovery.get("reason") != row.get("manual_reason")
        or not isinstance(current, Mapping)
        or current.get("session_id") != session.get("external_signing_session_id")
        or current.get("matching_plan_id") != session.get("matching_plan_id")
        or current.get("document_version_id") != row.get("document_version_id")
        or current.get("document_set_sha256") != session.get("current_document_set_sha256")
        or current.get("target_subject_reference") != row.get("reporter_subject_reference")
        or not isinstance(legacy, Mapping)
        or legacy.get("case_no") != case_no
        or legacy.get("scope") != scope.value
        or legacy.get("matching_plan_id") != session.get("matching_plan_id")
        or legacy.get("matching_segment_id") != segment_id
        or row.get("manual_evidence_sha256") != legacy.get("media_sha256")
    ):
        return "contract_signing_recovery_snapshot_lineage_invalid"
    if scope is ExternalCompletionReportScope.CLIENT:
        if current.get("commitment_id") != session.get("commitment_id"):
            return "contract_signing_recovery_snapshot_lineage_invalid"
    elif current.get("commitment_id") not in (None, session.get("commitment_id")):
        return "contract_signing_recovery_snapshot_lineage_invalid"
    matches = tuple(
        legacy_row
        for legacy_row in legacy_rows
        if legacy_row.get("event_id") == legacy.get("signing_event_id")
        and legacy_row.get("receipt_db_id") == legacy.get("command_receipt_id")
        and legacy_row.get("document_version_id")
        == legacy.get("legacy_document_version_id")
    )
    if len(matches) != 1:
        return "contract_signing_recovery_legacy_lineage_missing"
    legacy_row = matches[0]
    if row.get("manual_evidence_reference") != (
        f"legacy-contract-media:{legacy_row.get('document_version_id')}"
    ):
        return "contract_signing_recovery_legacy_evidence_reference_invalid"
    kind = (
        "signed_staff_segment"
        if scope is ExternalCompletionReportScope.STAFF
        else "client_signed_evidence"
    )
    legacy_error = _validate_legacy_manual((legacy_row,), case_no, kind)
    if legacy_error is not None:
        return legacy_error
    try:
        evidence = LegacyManualSigningEvidence(
            case_no=case_no,
            scope=scope,
            matching_plan_id=int(legacy_row["event_plan_id"]),
            matching_segment_id=legacy_row.get("event_segment_id"),
            legacy_document_version_id=int(legacy_row["document_version_id"]),
            source_document_version_id=int(legacy_row["source_document_version_id"]),
            signing_event_id=int(legacy_row["event_id"]),
            command_receipt_id=int(legacy_row["receipt_db_id"]),
            event_key=str(legacy_row["event_key"]),
            command_kind=str(legacy_row["command_kind"]),
            media_sha256=str(legacy_row["media_sha256"]),
            actor_ref=str(legacy_row["actor"]),
            correlation_id=str(legacy_row["correlation_id"]),
        )
    except (TypeError, ValueError, KeyError):
        return "contract_signing_recovery_legacy_lineage_invalid"
    if (
        evidence.canonical_payload != dict(legacy)
        or row.get("source_event_identity") != evidence.source_event_identity
        or row.get("source_payload_sha256") != evidence.canonical_tuple_sha256
    ):
        return "contract_signing_recovery_legacy_lineage_invalid"
    return None


def _validate_legacy_manual(rows, case_no, kind):
    if not rows:
        return f"contract_signing_{kind}_legacy_evidence_missing"
    if any(
        row.get("document_scope") not in {"staff_segment", "client_contract"}
        for row in rows
    ):
        return f"contract_signing_{kind}_legacy_evidence_malformed"
    relevant = []
    expected_scope = (
        "client_contract" if kind == "client_signed_evidence" else "staff_segment"
    )
    expected_command = (
        "record_manual_client_contract_attestation"
        if kind == "client_signed_evidence"
        else "record_manual_staff_contract_attestation"
    )
    for row in rows:
        if row.get("document_scope") != expected_scope:
            continue
        relevant.append(row)
        payload = _json_object(row.get("payload"))
        result = _json_object(row.get("result_snapshot"))
        if (
            row.get("event_case_no") != case_no
            or row.get("document_case_no") != case_no
            or row.get("receipt_case_no") != case_no
            or row.get("event_type") != "signed_received"
            or row.get("document_role") != "signed_return"
            or _positive_int(row.get("source_document_version_id")) is None
            or not _digest(row.get("media_sha256"))
            or row.get("event_plan_id") != row.get("document_plan_id")
            or row.get("event_segment_id") != row.get("document_segment_id")
            or row.get("receipt_document_id") != row.get("document_version_id")
            or row.get("receipt_event_id") != row.get("event_id")
            or row.get("idempotency_key") != row.get("event_key")
            or row.get("command_kind") != expected_command
            or payload is None
            or payload.get("command") != expected_command
            or payload.get("confirmation_method") not in _MANUAL_CONFIRMATION_METHODS
            or not _text(payload.get("reason"))
            or not _text(payload.get("correlation_id"))
            or payload.get("correlation_id") != row.get("correlation_id")
            or not _text(row.get("actor"))
            or result is None
            or result.get("document_version_id") != row.get("document_version_id")
            or result.get("signing_event_id") != row.get("event_id")
        ):
            return f"contract_signing_{kind}_legacy_evidence_malformed"
    if not relevant:
        return f"contract_signing_{kind}_legacy_manual_evidence_missing"
    event_ids = [row.get("event_id") for row in relevant]
    if len(event_ids) != len(set(event_ids)):
        return f"contract_signing_{kind}_legacy_evidence_ambiguous"
    return None


def _json_object(value):
    try:
        decoded = json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return decoded if isinstance(decoded, Mapping) else None


def _positive_int(value):
    return value if type(value) is int and 0 < value <= _MAX_BIGINT else None


def _nonnegative_int(value):
    return value if type(value) is int and 0 <= value <= _MAX_BIGINT else None


def _text(value):
    return isinstance(value, str) and value == value.strip() and bool(value)


def _digest(value):
    return _text(value) and len(value) == _HEX_DIGEST_LENGTH and all(
        character in "0123456789abcdef" for character in value
    )


def _opaque_identity(value, prefix):
    suffix = value[len(prefix):] if isinstance(value, str) and value.startswith(prefix) else ""
    return len(suffix) == 32 and all(character in "0123456789abcdef" for character in suffix)


def _available(descriptor, identity, root_identity, source_event_identity, source_version):
    return HistoricalBaselineOwnerObservation(
        descriptor,
        root_identity,
        source_event_identity,
        source_version,
        True,
        None,
        identity.case_no,
    )


def _unavailable(descriptor, identity, code):
    return HistoricalBaselineOwnerObservation.unavailable(
        descriptor, code=code, case_no=identity.case_no
    )


HistoricalBaselineContractSigningOwnerAdapter = MySqlHistoricalBaselineContractSigningOwnerAdapter


__all__ = [
    "HistoricalBaselineContractSigningOwnerAdapter",
    "MySqlHistoricalBaselineContractSigningOwnerAdapter",
]
