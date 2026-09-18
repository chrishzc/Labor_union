"""Issue #311: notification timeline explains missing current rule/configuration."""

from infrastructure.mysql.line_notification_repository import MySqlLineNotificationRepository


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _sql, _params):
        return None

    def fetchall(self):
        return self._rows


class _Connection:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _Cursor(self._rows)


def _source_row(*, reason_code=None, decision_status=None):
    return {
        "source_event_id": 311,
        "event_code": "service_time_checkpoint",
        "occurred_at_utc": "2026-09-18 02:00:00",
        "historical_silent": False,
        "rule_id": None,
        "decision_status": decision_status,
        "reason_code": reason_code,
        "recipient_type": None,
        "recipient_identity": "",
        "occurrence_number": None,
        "intent_status": None,
        "scheduled_at_utc": None,
        "delivery_task_id": None,
        "processing_status": None,
    }


def _repository(row, snapshots):
    repository = MySqlLineNotificationRepository(_Connection((row,)))
    lookups = []

    def current_configuration(kind):
        lookups.append(kind)
        return snapshots.get(kind)

    repository._current_configuration = current_configuration
    return repository, lookups


def test_timeline_reports_rule_not_configured_for_source_without_matching_current_rule():
    repository, lookups = _repository(
        _source_row(),
        {
            "notification_rules": (
                7,
                {
                    "rules": [
                        {
                            "id": "other-rule",
                            "event_code": "deposit_confirmed",
                        }
                    ]
                },
            ),
            "message_templates": (8, {"templates": []}),
        },
    )

    records = repository.list_case_timeline("CASE-311")

    assert records[0]["decision_status"] is None
    assert records[0]["reason_code"] == "rule_not_configured"
    assert lookups == ["notification_rules", "message_templates"]


def test_timeline_does_not_mislabel_source_when_matching_rule_is_current():
    repository, _lookups = _repository(
        _source_row(),
        {
            "notification_rules": (
                7,
                {
                    "rules": [
                        {
                            "id": "service-day-log-reminder",
                            "event_code": "service_time_checkpoint",
                        }
                    ]
                },
            ),
            "message_templates": (8, {"templates": []}),
        },
    )

    records = repository.list_case_timeline("CASE-311")

    assert records[0]["reason_code"] is None


def test_timeline_reports_configuration_unavailable_without_versioned_snapshots():
    repository, _lookups = _repository(
        _source_row(),
        {
            "notification_rules": None,
            "message_templates": None,
        },
    )

    records = repository.list_case_timeline("CASE-311")

    assert records[0]["reason_code"] == "notification_configuration_unavailable"


def test_timeline_preserves_persisted_decision_reason():
    repository, _lookups = _repository(
        _source_row(reason_code="rule_shadow_mode", decision_status="suppressed"),
        {
            "notification_rules": (7, {"rules": []}),
            "message_templates": (8, {"templates": []}),
        },
    )

    records = repository.list_case_timeline("CASE-311")

    assert records[0]["reason_code"] == "rule_shadow_mode"
