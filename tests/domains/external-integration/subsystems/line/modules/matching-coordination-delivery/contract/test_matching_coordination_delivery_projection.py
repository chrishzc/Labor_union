"""Focused owner-lineage regression for M3 -> LINE materialization."""

from infrastructure.mysql.line_matching_coordination_delivery_projection import (
    MySqlLineMatchingCoordinationDeliveryProjection,
)


class _Cursor:
    def __init__(self, calls):
        self.calls = calls
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters=()):
        self.calls.append((statement, parameters))
        if "FROM matching_schedule_recipient_snapshots r" in statement:
            self.row = (
                {
                    "snapshot_id": 219,
                    "recipient_line_user_id": "U-client-219",
                    "snapshot_fingerprint": "f" * 64,
                    "plan_id": 17,
                }
                if "s.status IN ('sent','draft')" in statement
                and "matching_schedule_confirmation_events" in statement
                and "NOT IN ('confirmed','manually_confirmed')" in statement
                else None
            )
        elif "FROM line_identity_role_bindings" in statement:
            self.row = {"binding_status": "bound", "aggregate_version": 3}
        elif "FROM line_configuration_current" in statement:
            self.row = {"revision": 7}
        else:
            self.row = None

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self):
        self.calls = []

    def cursor(self):
        return _Cursor(self.calls)


def test_manually_confirmed_draft_owner_snapshot_materializes_m3_line_payload():
    connection = _Connection()
    command = type("Command", (), {"case_no": "CASE-219"})()
    receipt = type("Receipt", (), {"decision_event_id": "decision:219"})()

    payload = MySqlLineMatchingCoordinationDeliveryProjection(connection).project(
        command,
        receipt,
        "match-219:notify:customer",
        {
            "recipient_selector": "assignment.client_snapshot",
            "result_state": "accepted",
        },
    )

    assert payload["recipient_snapshot"] == {
        "snapshot_id": "219",
        "snapshot_fingerprint": "f" * 64,
        "recipient_type": "user",
        "recipient_identity": "U-client-219",
    }
    assert payload["binding"] == {"active": True, "revision": 3}
    assert payload["configuration"] == {"active": True, "revision": 7}
    recipient_sql = connection.calls[0][0]
    assert "s.status IN ('sent','draft')" in recipient_sql
    assert "matching_schedule_confirmation_events" in recipient_sql
    assert "NOT IN ('confirmed','manually_confirmed')" in recipient_sql
