"""Focused contract for the read-only Contract Signing HCAT owner adapter."""

from __future__ import annotations

import json

import pytest

from domains.orders.historical_operational_baseline import (
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    HistoricalOrderIdentity,
)
from infrastructure.mysql.historical_baseline_contract_signing_owner_adapter import (
    MySqlHistoricalBaselineContractSigningOwnerAdapter,
)
from shared_kernel.fingerprints import fingerprint_payload


IDENTITY = HistoricalOrderIdentity("order:CASE-1", "CASE-1")
STAFF = next(
    item for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    if item.root_identity_kind == "signed_staff_segment"
)
COMMITMENT = next(
    item for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    if item.root_identity_kind == "commitment"
)
CLIENT = next(
    item for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    if item.root_identity_kind == "client_signed_evidence"
)


class Cursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters):
        self.connection.calls.append((statement, parameters))
        if self.connection.error is not None:
            raise self.connection.error

    def fetchall(self):
        return self.connection.responses.pop(0)


class Connection:
    """Intentionally has no transaction lifecycle methods."""

    def __init__(self, responses, *, error=None):
        self.responses = list(responses)
        self.error = error
        self.calls = []

    def cursor(self):
        return Cursor(self)


def _document_set(segment_documents=((41, 241),), client_document_id=72):
    return fingerprint_payload(
        {
            "case_no": "CASE-1",
            "matching_plan_id": 21,
            "staff_documents": [list(item) for item in segment_documents],
            "client_document_id": client_document_id,
        }
    ).value


def _session(**changes):
    row = {
        "session_db_id": 11,
        "external_signing_session_id": "ces_" + "a" * 32,
        "case_no": "CASE-1",
        "matching_plan_id": 21,
        "current_document_set_sha256": _document_set(),
        "commitment_id": 31,
        "session_state": "completed",
        "aggregate_version": 3,
    }
    row.update(changes)
    return row


def _staff_row(segment_id=41, version=1, **changes):
    row = {
        "segment_id": segment_id,
        "segment_plan_id": 21,
        "segment_staff_id": 500 + segment_id,
        "plan_case_no": "CASE-1",
        "plan_status": "accepted",
        "plan_is_active": 1,
        "report_db_id": 100 + segment_id,
        "report_id": f"cer_{segment_id:032x}",
        "report_session_db_id": 11,
        "report_case_no": "CASE-1",
        "report_scope": "staff",
        "report_segment_id": segment_id,
        "document_version_id": 200 + segment_id,
        "source_event_identity": f"line-event:{segment_id}",
        "resulting_status_version": version,
        "report_expected_status_version": version - 1,
        "reporter_subject_type": "staff",
        "reporter_subject_reference": str(500 + segment_id),
        "document_case_no": "CASE-1",
        "document_scope": "staff_segment",
        "document_role": "template_generated",
        "document_plan_id": 21,
        "document_segment_id": segment_id,
        "receipt_db_id": 300 + segment_id,
        "receipt_id": f"cesr_{segment_id:032x}",
        "receipt_session_db_id": 11,
        "receipt_command": "record_staff_report",
        "receipt_expected_status_version": version - 1,
        "result_status_version": version,
        "completion_report_id": 100 + segment_id,
        "outcome_state": "recorded",
        "preview_fingerprint": None,
        "current_document_version_id": 200 + segment_id,
        "current_client_document_version_id": 72,
    }
    row.update(changes)
    return row


def _client_row(**changes):
    row = {
        "report_db_id": 71,
        "report_id": "cer_" + "c" * 32,
        "report_session_db_id": 11,
        "report_case_no": "CASE-1",
        "report_scope": "client",
        "matching_segment_id": None,
        "document_version_id": 72,
        "report_commitment_id": 31,
        "source_event_identity": "line-event:client",
        "report_status_version": 2,
        "report_expected_status_version": 1,
        "reporter_subject_type": "customer",
        "reporter_subject_reference": "301",
        "report_document_case_no": "CASE-1",
        "report_document_scope": "client_contract",
        "report_document_role": "template_generated",
        "report_document_plan_id": 21,
        "report_document_segment_id": None,
        "report_receipt_db_id": 73,
        "report_receipt_id": "cesr_" + "d" * 32,
        "report_receipt_session_db_id": 11,
        "report_receipt_command": "record_client_report",
        "report_receipt_expected_status_version": 1,
        "report_receipt_status_version": 2,
        "completion_report_id": 71,
        "report_outcome": "recorded",
        "report_preview_fingerprint": None,
        "final_document_db_id": 74,
        "final_document_id": "cfd_" + "e" * 32,
        "final_session_db_id": 11,
        "final_case_no": "CASE-1",
        "source_document_set_sha256": _document_set(),
        "controlled_file_object_id": 75,
        "version_number": 1,
        "contract_identity": "client-contract:" + "f" * 64,
        "final_content_type": "application/pdf",
        "final_size_bytes": 1024,
        "final_sha256": "1" * 64,
        "object_db_id": 75,
        "opaque_object_id": "cf_" + "2" * 32,
        "owner_type": "contract_signing",
        "subject_reference": "CASE-1",
        "purpose": "final_signed_contract",
        "object_content_type": "application/pdf",
        "object_size_bytes": 1024,
        "object_sha256": "1" * 64,
        "final_receipt_db_id": 76,
        "final_receipt_id": "cesr_" + "3" * 32,
        "final_receipt_session_db_id": 11,
        "final_receipt_command": "apply_final_signed_contract",
        "final_preview_fingerprint": "4" * 64,
        "final_receipt_expected_status_version": 2,
        "final_receipt_status_version": 3,
        "final_document_version_id": 74,
        "final_outcome": "completed",
        "plan_case_no": "CASE-1",
        "plan_status": "accepted",
        "plan_is_active": 1,
        "order_client_id": 301,
        "current_client_document_version_id": 72,
    }
    row.update(changes)
    return row


def _legacy_row(scope="staff_segment", **changes):
    staff = scope == "staff_segment"
    command = (
        "record_manual_staff_contract_attestation"
        if staff else "record_manual_client_contract_attestation"
    )
    segment_id = 41 if staff else None
    payload = {
        "command": command,
        "confirmation_method": "paper",
        "reason": "歷史紙本簽回",
        "correlation_id": "corr-1",
    }
    result = {"document_version_id": 81, "signing_event_id": 82}
    row = {
        "event_id": 82,
        "event_case_no": "CASE-1",
        "document_version_id": 81,
        "event_plan_id": 21,
        "event_segment_id": segment_id,
        "event_type": "signed_received",
        "event_key": "manual-key-1",
        "actor": "operator-1",
        "payload": json.dumps(payload, ensure_ascii=False),
        "document_case_no": "CASE-1",
        "document_scope": scope,
        "document_role": "signed_return",
        "document_plan_id": 21,
        "document_segment_id": segment_id,
        "source_document_version_id": 80,
        "media_sha256": "5" * 64,
        "receipt_db_id": 83,
        "idempotency_key": "manual-key-1",
        "command_kind": command,
        "receipt_case_no": "CASE-1",
        "receipt_document_id": 81,
        "receipt_event_id": 82,
        "correlation_id": "corr-1",
        "result_snapshot": json.dumps(result),
    }
    row.update(changes)
    return row


def _read(descriptor, responses, *, for_update=False):
    connection = Connection(responses)
    result = MySqlHistoricalBaselineContractSigningOwnerAdapter(connection).read_owner_observations(
        IDENTITY, descriptor, for_update=for_update
    )
    return result, connection


def test_external_staff_reports_produce_one_exact_observation_per_segment_and_propagate_lock():
    result, connection = _read(
        STAFF,
        [[_session(current_document_set_sha256=_document_set(((41, 241), (42, 242))), aggregate_version=4)],
         [_staff_row(41, 1), _staff_row(42, 2)]],
        for_update=True,
    )

    assert [item.root_identity for item in result.observations] == [
        "contract_signing.staff_segment:CASE-1:41",
        "contract_signing.staff_segment:CASE-1:42",
    ]
    assert [item.source_version for item in result.observations] == [1, 2]
    assert all(item.terminal_result is True for item in result.observations)
    assert len(connection.calls) == 2
    assert all(statement.rstrip().endswith("FOR UPDATE") for statement, _ in connection.calls)
    assert connection.calls[0][1] == ("CASE-1",)
    assert connection.calls[1][1] == (11, 21)


def test_external_commitment_requires_complete_staff_lineage_and_uses_exact_latest_source():
    commitment = {
        "commitment_id": 31,
        "commitment_case_no": "CASE-1",
        "commitment_plan_id": 21,
        "commitment_key": "commitment:CASE-1:21",
        "plan_snapshot_sha256": "6" * 64,
    }
    result, _connection = _read(
        COMMITMENT,
        [[_session(current_document_set_sha256=_document_set(((41, 241), (42, 242))), aggregate_version=4)],
         [_staff_row(41, 1), _staff_row(42, 2)], [commitment]],
    )

    observation = result.observations[0]
    assert observation.root_identity == "contract_signing.commitment:CASE-1:31"
    assert observation.source_event_identity == "line-event:42"
    assert observation.source_version == 2
    assert observation.terminal_result is True


def test_external_client_evidence_requires_report_final_controlled_file_and_final_receipt():
    result, _connection = _read(CLIENT, [[_session()], [_staff_row()], [_client_row()]])

    observation = result.observations[0]
    assert observation.root_identity == (
        "contract_signing.client_signed_evidence:CASE-1:cfd_" + "e" * 32
    )
    assert observation.source_event_identity == "cesr_" + "3" * 32
    assert observation.source_version == 3
    assert observation.terminal_result is True


@pytest.mark.parametrize(
    ("descriptor", "rows", "code"),
    [
        (STAFF, [_staff_row(report_case_no="CASE-X")], "contract_signing_staff_segment_lineage_invalid"),
        (STAFF, [_staff_row(), _staff_row()], "contract_signing_staff_segment_evidence_ambiguous"),
        (CLIENT, [_client_row(final_sha256="bad")], "contract_signing_client_signed_evidence_lineage_invalid"),
        (CLIENT, [_client_row(), _client_row(final_document_db_id=99)], "contract_signing_client_signed_evidence_ambiguous"),
    ],
)
def test_external_cross_case_malformed_and_ambiguous_evidence_fail_closed(descriptor, rows, code):
    responses = [[_session()], rows]
    if descriptor is CLIENT:
        responses.insert(1, [_staff_row()])
    result, _connection = _read(descriptor, responses)

    assert result.observations[0].available is False
    assert result.observations[0].unavailable_code == code


def test_current_external_session_takes_precedence_and_never_queries_legacy_evidence():
    result, connection = _read(STAFF, [[_session()], []])

    assert result.observations[0].unavailable_code == "contract_signing_staff_segments_missing"
    assert len(connection.calls) == 2
    assert all("contract_signing_events" not in statement for statement, _ in connection.calls)


def test_staff_and_client_reporter_subjects_must_match_exact_owner_identity():
    result, _connection = _read(
        STAFF,
        [[_session()], [_staff_row(reporter_subject_reference="999")]],
    )
    assert result.observations[0].unavailable_code == (
        "contract_signing_staff_segment_lineage_invalid"
    )

    result, _connection = _read(
        CLIENT,
        [[_session()], [_staff_row()], [_client_row(reporter_subject_type="staff")]],
    )
    assert result.observations[0].unavailable_code == (
        "contract_signing_client_signed_evidence_lineage_invalid"
    )


def test_report_document_must_be_the_session_current_document_set_member():
    result, _connection = _read(
        STAFF,
        [[_session()], [_staff_row(document_version_id=999)]],
    )
    assert result.observations[0].unavailable_code == (
        "contract_signing_staff_segment_lineage_invalid"
    )

    result, _connection = _read(
        STAFF,
        [[_session(current_document_set_sha256="9" * 64)], [_staff_row()]],
    )
    assert result.observations[0].unavailable_code == "contract_signing_document_set_stale"


@pytest.mark.parametrize("version", [0, 2, 99])
def test_staff_report_status_versions_must_match_the_closed_transition_chain(version):
    result, _connection = _read(
        STAFF,
        [[_session()], [_staff_row(version=version)]],
    )
    assert result.observations[0].unavailable_code == (
        "contract_signing_staff_segment_status_version_drift"
    )


@pytest.mark.parametrize(
    ("status", "active"),
    [("rejected", 1), ("superseded", 0), ("accepted", 0)],
)
def test_client_evidence_requires_current_accepted_active_matching_plan(status, active):
    result, _connection = _read(
        CLIENT,
        [[_session()], [_staff_row()], [_client_row(plan_status=status, plan_is_active=active)]],
    )
    assert result.observations[0].unavailable_code == (
        "contract_signing_client_signed_evidence_lineage_invalid"
    )


def test_ambiguous_or_cross_case_current_session_fails_closed_without_legacy_fallback():
    result, connection = _read(STAFF, [[_session(), _session(session_db_id=12)]])
    assert result.observations[0].unavailable_code == "contract_signing_external_session_ambiguous"
    assert len(connection.calls) == 1

    result, connection = _read(STAFF, [[_session(case_no="CASE-X")]])
    assert result.observations[0].unavailable_code == "contract_signing_external_session_malformed"
    assert len(connection.calls) == 1


@pytest.mark.parametrize(
    ("descriptor", "scope"),
    [(STAFF, "staff_segment"), (COMMITMENT, "staff_segment"), (CLIENT, "client_contract")],
)
def test_valid_legacy_manual_tuple_stays_typed_unavailable_without_persisted_preview_fingerprint(
    descriptor, scope
):
    result, connection = _read(descriptor, [[], [_legacy_row(scope)]], for_update=True)

    observation = result.observations[0]
    assert observation.available is False
    assert observation.unavailable_code == (
        "contract_signing_legacy_manual_preview_fingerprint_unavailable"
    )
    assert all(statement.rstrip().endswith("FOR UPDATE") for statement, _ in connection.calls)


def test_plain_or_malformed_legacy_signed_received_cannot_be_promoted():
    row = _legacy_row(payload=json.dumps({"command": "record_staff_signed_return"}))
    result, _connection = _read(STAFF, [[], [row]])

    assert result.observations[0].unavailable_code == (
        "contract_signing_signed_staff_segment_legacy_evidence_malformed"
    )


def test_descriptor_boundary_and_read_failures_are_typed_and_connection_is_borrowed():
    with pytest.raises(ValueError, match="historical_baseline_contract_signing_descriptor_unsupported"):
        MySqlHistoricalBaselineContractSigningOwnerAdapter(Connection([])).read_owner_observations(
            IDENTITY,
            next(item for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2 if item.owner_domain == "orders"),
        )

    connection = Connection([], error=RuntimeError("database unavailable"))
    result = MySqlHistoricalBaselineContractSigningOwnerAdapter(connection).read_owner_observations(
        IDENTITY, STAFF
    )
    assert result.observations[0].unavailable_code == "contract_signing_signed_staff_segment_read_failed"
