"""Focused owner-lineage regression for M3 -> LINE materialization."""
import json

from infrastructure.mysql.line_matching_coordination_delivery_projection import (
    MySqlLineMatchingCoordinationDeliveryProjection,
)


class _Cursor:
    def __init__(self, calls, description):
        self.calls = calls
        self.description = description
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters=()):
        self.calls.append((statement, parameters))
        if "FROM matching_schedule_recipient_snapshots r" in statement:
            self.row = {
                "snapshot_id": 219,
                "recipient_line_user_id": "U-client-219",
                "snapshot_fingerprint": "f" * 64,
                "plan_id": 17,
            }
        elif "FROM line_identity_role_bindings" in statement:
            self.row = {"binding_status": "bound", "aggregate_version": 3}
        elif "FROM line_configuration_current" in statement:
            self.row = {'configuration_kind': 'message_templates', 'revision': 7, 'definition_snapshot': json.dumps({
                'templates': [{'id': 'LU96-M3-ZERO-POOL-CARD-V1', 'message_type': 'text', 'content': self.description, 'variables': []}],
            })}
        else:
            self.row = None

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, description):
        self.calls = []
        self.description = description

    def cursor(self):
        return _Cursor(self.calls, self.description)


def _project(selector='assignment.client_snapshot', description='請確認這次服務條件。'):
    connection = _Connection(description)
    command = type("Command", (), {"case_no": "CASE-219"})()
    receipt = type("Receipt", (), {"decision_event_id": "decision:219"})()
    payload = MySqlLineMatchingCoordinationDeliveryProjection(connection).project(
        command,
        receipt,
        "match-219:notify:customer",
        {
            "recipient_selector": selector,
            "result_state": "accepted",
        },
    )
    return connection, payload


def test_manually_confirmed_draft_owner_snapshot_materializes_m3_line_payload():
    connection, payload = _project()
    assert payload["recipient_snapshot"] == {
        "snapshot_id": "219",
        "snapshot_fingerprint": "f" * 64,
        "recipient_type": "user",
        "recipient_identity": "U-client-219",
    }
    assert payload["binding"] == {"active": True, "revision": 3}
    assert payload["configuration"] == {"active": True, "revision": 7}
    recipient_sql = connection.calls[0][0]
    assert "s.status='sent' OR (s.status='draft' AND" in recipient_sql
    assert "matching_schedule_confirmation_events" in recipient_sql
    assert "NOT IN ('confirmed','manually_confirmed')" in recipient_sql


def test_sent_snapshot_remains_authoritative_without_confirmation_gate():
    connection, _ = _project()
    recipient_sql = connection.calls[0][0]
    sent_index = recipient_sql.index("s.status='sent'")
    draft_index = recipient_sql.index("s.status='draft'")
    confirmation_index = recipient_sql.index("matching_schedule_confirmation_events")
    assert sent_index < draft_index < confirmation_index
    assert "s.status='sent' OR (s.status='draft' AND" in recipient_sql


def test_draft_snapshot_is_fail_closed_behind_confirmation_gate():
    connection, _ = _project()
    recipient_sql = connection.calls[0][0]
    assert "s.status='draft' AND NOT EXISTS (" in recipient_sql
    assert "COALESCE(gate_e.confirmation_value,'pending')" in recipient_sql
    assert "NOT IN ('confirmed','manually_confirmed')" in recipient_sql


def test_retired_zero_pool_projection_never_reads_configuration_or_creates_a_token():
    import pytest
    from types import SimpleNamespace
    from subsystems.line.matching_coordination_delivery import MatchingCoordinationDeliveryError
    def forbidden():
        pytest.fail("retired projection must not read recipients or configuration")
    adapter = MySqlLineMatchingCoordinationDeliveryProjection(SimpleNamespace(cursor=forbidden))
    with pytest.raises(MatchingCoordinationDeliveryError) as error:
        adapter.project(SimpleNamespace(case_no="CASE-96"), None, "old-zero", {"recipient_selector":"matching.request.participants"})
    assert error.value.code == "matching_zero_pool_notification_retired"
