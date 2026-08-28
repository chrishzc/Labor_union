"""
File: test_case_anomaly_readback_adapter.py
Description: 驗證案件異常 MySQL adapter 只讀、精確綁定與未支援 fail-closed。
"""

from datetime import date, datetime, timezone

import pytest

from infrastructure.mysql.case_anomaly_readback_adapter import (
    MySqlCaseAnomalyReadbackAdapter,
)
from infrastructure.mysql.case_anomaly_readback_adapter import _process_reminder_partition
from subsystems.anomalies.case_anomaly_readback import CaseAnomalyReadbackStatus
from subsystems.anomalies.source_version import daily_root_source_version


AS_OF = date(2026, 8, 27)


class _Cursor:
    def __init__(self, rows_by_marker):
        self.rows_by_marker = rows_by_marker
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters):
        normalized = statement.lower()
        if any(keyword in normalized for keyword in ("insert", "update", "delete", "for update")):
            raise AssertionError("case anomaly readback must not write or lock")
        self.calls.append((normalized, parameters))

    def fetchall(self):
        statement, parameters = self.calls[-1]
        for marker, rows in self.rows_by_marker.items():
            if marker in statement:
                return rows
        return ()


class _Connection:
    def __init__(self, rows_by_marker):
        self.cursor_instance = _Cursor(rows_by_marker)

    def cursor(self):
        return self.cursor_instance


def _row(code, identity, version=2, fingerprint=None):
    return {
        "row_kind": "alert",
        "definition_code": code,
        "fingerprint": fingerprint or "a" * 64,
        "source_identity": identity,
        "source_version": version,
        "predicate_active": 1,
        "workflow_status": "open",
    }


def _freshness(code, owner_version, checkpoint_version=None, case_no="CASE-1"):
    if checkpoint_version is None:
        checkpoint_version = (
            daily_root_source_version(as_of=AS_OF, root_version=owner_version)
            if code != "SCHEDULE-006"
            else owner_version
        )
    if code == "SCHEDULE-006":
        return {
            "row_kind": "freshness",
            "owner_version": owner_version,
            "checkpoint_version": checkpoint_version,
            "consumer_identity": "scheduling-coverage-anomaly-projector-v1",
            "partition_identity": f"SCHEDULE-006:case:{case_no}:generation:4",
        }
    return {
        "row_kind": "freshness",
        "owner_version": owner_version,
        "checkpoint_version": checkpoint_version,
        "consumer_identity": "process-reminder-anomaly-source-v1",
        "partition_identity": _process_reminder_partition(code, case_no),
    }


def _snapshot(alerts, freshness):
    return tuple(alerts) + (freshness,)


def test_direct_client_alert_is_resolved_by_exact_case_identity():
    connection = _Connection({
        "union all": _snapshot(
            (
                _row(
                    "RECEIVABLE-001",
                    "CASE-1",
                    daily_root_source_version(as_of=AS_OF, root_version=1),
                ),
            ),
            _freshness("RECEIVABLE-001", 1),
        ),
    })
    adapter = MySqlCaseAnomalyReadbackAdapter(connection)

    result = adapter.resolve_case_anomalies(
        "CASE-1", ["RECEIVABLE-001"],
        as_of=AS_OF,
        read_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
    )

    assert result.status is CaseAnomalyReadbackStatus.COMPLETE
    assert result.resolved_alerts[0].source_identity == "CASE-1"
    assert len(connection.cursor_instance.calls) == 1
    assert connection.cursor_instance.calls[0][1] == (
        "RECEIVABLE-001",
        "CASE-1",
        "process-reminder-anomaly-source-v1",
        _process_reminder_partition("RECEIVABLE-001", "CASE-1"),
        "CASE-1",
    )


def test_schedule_coverage_uses_direct_case_identity_without_join_duplication():
    connection = _Connection({
        "union all": _snapshot(
            (_row("SCHEDULE-006", "case:CASE-1", 3),),
            _freshness("SCHEDULE-006", 3),
        ),
    })

    result = MySqlCaseAnomalyReadbackAdapter(connection).resolve_case_anomalies(
        "CASE-1", ["SCHEDULE-006"], as_of=AS_OF
    )

    assert result.status is CaseAnomalyReadbackStatus.COMPLETE
    statement = connection.cursor_instance.calls[0][0]
    assert "display_snapshot" not in statement
    assert " like " not in statement
    assert "join scheduling_generations" in statement
    assert connection.cursor_instance.calls[0][1] == ("CASE-1", "CASE-1")


def test_projector_missing_with_owner_root_is_unavailable():
    connection = _Connection({
        "union all": _snapshot(
            (),
            {**_freshness("CLIENTPAYABLE-001", 7), "checkpoint_version": None},
        ),
    })

    result = MySqlCaseAnomalyReadbackAdapter(connection).resolve_case_anomalies(
        "CASE-1", ["CLIENTPAYABLE-001"], as_of=AS_OF
    )

    assert result.status is CaseAnomalyReadbackStatus.UNAVAILABLE
    assert result.unresolved_definitions == (
        ("CLIENTPAYABLE-001", "projection_freshness_unproven"),
    )


def test_stale_checkpoint_with_owner_root_is_unavailable():
    connection = _Connection({
        "union all": _snapshot(
            (), _freshness("CLIENTPAYABLE-001", 7, checkpoint_version=6)
        ),
    })

    result = MySqlCaseAnomalyReadbackAdapter(connection).resolve_case_anomalies(
        "CASE-1", ["CLIENTPAYABLE-001"], as_of=AS_OF
    )

    assert result.status is CaseAnomalyReadbackStatus.UNAVAILABLE
    assert result.source_versions == ()


def test_stale_active_alert_is_unavailable_even_when_checkpoint_is_fresh():
    connection = _Connection({
        "union all": _snapshot(
            (_row("CLIENTPAYABLE-001", "CASE-1", 8),),
            _freshness("CLIENTPAYABLE-001", 7),
        ),
    })

    result = MySqlCaseAnomalyReadbackAdapter(connection).resolve_case_anomalies(
        "CASE-1", ["CLIENTPAYABLE-001"], as_of=AS_OF
    )

    assert result.status is CaseAnomalyReadbackStatus.UNAVAILABLE
    assert result.unresolved_definitions == (
        ("CLIENTPAYABLE-001", "projection_freshness_unproven"),
    )


def test_old_date_checkpoint_is_unavailable_even_when_numeric_value_exceeds_owner():
    old_checkpoint = daily_root_source_version(as_of=date(2026, 8, 26), root_version=7)
    connection = _Connection({
        "union all": _snapshot(
            (), _freshness("CLIENTPAYABLE-001", 7, checkpoint_version=old_checkpoint)
        ),
    })

    result = MySqlCaseAnomalyReadbackAdapter(connection).resolve_case_anomalies(
        "CASE-1", ["CLIENTPAYABLE-001"], as_of=AS_OF
    )

    assert result.status is CaseAnomalyReadbackStatus.UNAVAILABLE


def test_multiple_definitions_fail_closed_without_cross_statement_snapshot():
    connection = _Connection({})

    result = MySqlCaseAnomalyReadbackAdapter(connection).resolve_case_anomalies(
        "CASE-1", ["CLIENTPAYABLE-001", "SCHEDULE-006"], as_of=AS_OF
    )

    assert result.status is CaseAnomalyReadbackStatus.UNAVAILABLE
    assert result.unresolved_definitions == (
        ("CLIENTPAYABLE-001", "consistent_snapshot_required"),
        ("SCHEDULE-006", "consistent_snapshot_required"),
    )
    assert connection.cursor_instance.calls == []


def test_fresh_inactive_client_payable_is_complete_and_retains_evidence_versions():
    connection = _Connection({
        "union all": _snapshot(
            (), _freshness("CLIENTPAYABLE-001", 7)
        ),
    })

    result = MySqlCaseAnomalyReadbackAdapter(connection).resolve_case_anomalies(
        "CASE-1", ["CLIENTPAYABLE-001"], as_of=AS_OF
    )

    assert result.status is CaseAnomalyReadbackStatus.COMPLETE
    assert result.resolved_alerts == ()
    assert ("owner:CLIENTPAYABLE-001:CASE-1", 7) in result.source_versions
    expected = daily_root_source_version(as_of=AS_OF, root_version=7)
    assert any(
        identity.startswith("projector:") and version == expected
        for identity, version in result.source_versions
    )


def test_conflicting_active_alert_rows_are_unavailable():
    connection = _Connection({
        "union all": _snapshot((
            _row("CLIENTPAYABLE-001", "CASE-1", 2, "a" * 64),
            _row("CLIENTPAYABLE-001", "CASE-1", 2, "b" * 64),
        ), _freshness("CLIENTPAYABLE-001", 1)),
    })

    result = MySqlCaseAnomalyReadbackAdapter(connection).resolve_case_anomalies(
        "CASE-1", ["CLIENTPAYABLE-001"], as_of=AS_OF
    )

    assert result.status is CaseAnomalyReadbackStatus.UNAVAILABLE
    assert result.unresolved_definitions == (
        ("CLIENTPAYABLE-001", "conflicting_active_alert"),
    )


def test_unreliable_finance_batch_binding_is_unavailable_not_empty_success():
    connection = _Connection({})

    result = MySqlCaseAnomalyReadbackAdapter(connection).resolve_case_anomalies(
        "CASE-1", ["finance_import_manual_review"], as_of=AS_OF
    )

    assert result.status is CaseAnomalyReadbackStatus.UNAVAILABLE
    assert result.resolved_alerts == ()
    assert result.unresolved_definitions == (
        ("finance_import_manual_review", "finance_import_row_case_binding_unavailable"),
    )
    assert connection.cursor_instance.calls == []


def test_adapter_rejects_locking_mode_by_not_exposing_it():
    adapter = MySqlCaseAnomalyReadbackAdapter(_Connection({}))
    with pytest.raises(ValueError, match="read-only"):
        adapter.resolve_case_anomalies("CASE-1", ["SCHEDULE-006"], as_of=AS_OF, for_update=True)
