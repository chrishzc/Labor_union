"""
File: test_line_binding_anomaly_predicate_guard.py
Description: 驗證 LINE 綁定異常只由 canonical binding root 完整成立後解除。
"""

from datetime import date

from infrastructure.mysql import process_reminder_anomaly_source as mysql_source
from infrastructure.mysql.process_reminder_anomaly_source import (
    consume_process_reminder_anomaly_sources,
)
from subsystems.anomalies.process_reminder_anomaly_source import (
    build_client_missing_line_requests,
    build_staff_missing_line_requests,
)

_AS_OF = date(2026, 8, 27)


def _active(request) -> bool:
    return request.desired.active


def _client_row(**overrides):
    return {
        "case_no": "CASE-LINE-C",
        "client_id": 17,
        "line_user_id": "U-client",
        "binding_line_user_id": "U-client",
        "binding_status": "bound",
        "binding_subject_type": "customer",
        "binding_subject_reference": "17",
        "binding_version": 3,
        **overrides,
    }


def _staff_row(**overrides):
    return {
        "case_no": "CASE-LINE-S",
        "staff_id": 29,
        "staff_line_user_id": "U-staff",
        "binding_line_user_id": "U-staff",
        "binding_status": "bound",
        "binding_subject_type": "staff",
        "binding_subject_reference": "29",
        "binding_version": 4,
        **overrides,
    }


def test_client_alert_only_clears_for_matching_bound_customer_root():
    valid = build_client_missing_line_requests([_client_row()], as_of=_AS_OF)[0]
    assert _active(valid) is False

    invalid_rows = (
        _client_row(line_user_id=None),
        _client_row(binding_line_user_id=None),
        _client_row(binding_status="pending_review"),
        _client_row(binding_status="revocation_pending"),
        _client_row(binding_subject_type="staff"),
        _client_row(binding_subject_reference="18"),
        _client_row(binding_line_user_id="U-other"),
        _client_row(line_user_id=" ", binding_line_user_id=" "),
        _client_row(line_user_id=" U-client ", binding_line_user_id=" U-client "),
        _client_row(client_id=None),
    )
    assert all(
        _active(build_client_missing_line_requests([row], as_of=_AS_OF)[0])
        for row in invalid_rows
    )


def test_staff_alert_only_clears_for_matching_bound_staff_root():
    valid = build_staff_missing_line_requests([_staff_row()], as_of=_AS_OF)[0]
    assert _active(valid) is False

    invalid_rows = (
        _staff_row(staff_line_user_id=None),
        _staff_row(binding_line_user_id=None),
        _staff_row(binding_status="revoked"),
        _staff_row(binding_status="revocation_pending"),
        _staff_row(binding_subject_type="customer"),
        _staff_row(binding_subject_reference="30"),
        _staff_row(binding_line_user_id="U-other"),
    )
    assert all(
        _active(build_staff_missing_line_requests([row], as_of=_AS_OF)[0])
        for row in invalid_rows
    )


def test_unassigned_staff_does_not_create_missing_binding_predicate():
    request = build_staff_missing_line_requests(
        [_staff_row(staff_id=None, staff_line_user_id=None, binding_line_user_id=None)],
        as_of=_AS_OF,
    )[0]
    assert _active(request) is False


def test_mysql_queries_load_canonical_binding_evidence():
    for sql in (mysql_source._CLIENT_LINE_SQL, mysql_source._STAFF_LINE_SQL):
        assert "LEFT JOIN line_identity_bindings b" in sql
        assert "b.binding_status" in sql
        assert "b.subject_type AS binding_subject_type" in sql
        assert "b.subject_reference AS binding_subject_reference" in sql
        assert "b.aggregate_version AS binding_version" in sql
    assert "LEFT JOIN clients c" in mysql_source._CLIENT_LINE_SQL
    assert "ON c.id = o.client_id AND c.case_no = o.case_no" in mysql_source._CLIENT_LINE_SQL


def test_mysql_scan_failure_rolls_back_without_legacy_fallback():
    class FailingCursor:
        def __enter__(self):
            return self

        def __exit__(self, exception_type, exception, traceback):
            return False

        def execute(self, _sql):
            raise RuntimeError("synthetic query failure")

    class FailingConnection:
        def __init__(self):
            self.begins = 0
            self.commits = 0
            self.rollbacks = 0

        def begin(self):
            self.begins += 1

        def cursor(self):
            return FailingCursor()

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

    connection = FailingConnection()
    result = consume_process_reminder_anomaly_sources(
        connection,
        as_of=_AS_OF,
        unit_of_work_factory=lambda: None,
    )

    assert result.succeeded is False
    assert result.error is not None
    assert result.error.code == "transaction_failed"
    assert (connection.begins, connection.commits, connection.rollbacks) == (0, 0, 0)
