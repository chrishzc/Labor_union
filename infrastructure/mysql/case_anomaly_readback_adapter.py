"""
File: case_anomaly_readback_adapter.py
Description: 以 canonical MySQL roots 唯讀解析單一案件的異常綁定。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timezone
from typing import Any

from shared_kernel.validation import require_canonical_text
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.anomalies.case_anomaly_readback import (
    CaseAnomalyAlert,
    CaseAnomalyDefinitionRead,
    CaseAnomalyReadback,
    CaseAnomalyReadbackService,
    CaseAnomalyReadbackStatus,
    SUPPORTED_CANCELLATION_DEFINITIONS,
)
from subsystems.anomalies.source_version import daily_root_source_version


_CASE_NUMBER_MAXIMUM_LENGTH = 50

_DIRECT_CASE_CODES = frozenset({
    "RECEIVABLE-001",
    "RETURN-001",
    "CLIENTPAYABLE-001",
})
_FRESHNESS_PROVEN_DEFINITIONS = _DIRECT_CASE_CODES | {"SCHEDULE-006"}
_PROCESS_REMINDER_CONSUMER = "process-reminder-anomaly-source-v1"
_SCHEDULE_COVERAGE_CONSUMER = "scheduling-coverage-anomaly-projector-v1"


class MySqlCaseAnomalyReadbackAdapter:
    """Read current alerts through exact owner-root joins; never writes or locks."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def resolve_case_anomalies(
        self,
        case_no,
        requested_definitions,
        *,
        as_of: date,
        read_at=None,
        for_update: bool = False,
    ) -> CaseAnomalyReadback:
        if for_update:
            raise ValueError("case anomaly readback adapter is read-only")
        if type(as_of) is not date:
            raise TypeError("as_of must be a business date")
        if isinstance(requested_definitions, (str, bytes)):
            raise TypeError("requested definitions must be an iterable of codes")
        codes = tuple(sorted(set(requested_definitions)))
        if len(codes) > 1:
            # Each definition read is one consistent MySQL statement.  Until a
            # caller supplies a shared snapshot/UoW, never combine statements.
            return _unavailable_batch_readback(codes, case_no, read_at)
        return CaseAnomalyReadbackService(self).resolve_case_anomalies(
            case_no, codes, as_of=as_of, read_at=read_at
        )

    def read_definition(
        self,
        case_no: str,
        definition_code: str,
        *,
        as_of: date,
        for_update: bool = False,
    ) -> CaseAnomalyDefinitionRead:
        require_canonical_text(case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)
        require_canonical_text(definition_code, "definition code", 191)
        if type(as_of) is not date:
            raise TypeError("as_of must be a business date")
        if for_update:
            raise ValueError("case anomaly readback adapter is read-only")
        if definition_code == "finance_import_manual_review":
            return _unresolved(definition_code, "finance_import_row_case_binding_unavailable")
        if definition_code not in _FRESHNESS_PROVEN_DEFINITIONS:
            return _unresolved(definition_code, "projection_freshness_unproven")
        statement, params = _query_for(definition_code, case_no)
        if statement is None:
            return _unresolved(definition_code, "definition_case_resolver_unavailable")
        with self._connection.cursor() as cursor:
            cursor.execute(statement, params)
            rows = _mapping_rows(cursor.fetchall())
        alerts, freshness = _split_snapshot_rows(
            rows, definition_code, case_no=case_no, as_of=as_of
        )
        if freshness is None:
            return _unresolved(definition_code, "projection_freshness_unproven")
        if len({item.fingerprint for item in alerts}) != len(alerts):
            return _unresolved(definition_code, "duplicate_active_alert")
        if len({item.source_identity for item in alerts}) != len(alerts):
            return _unresolved(definition_code, "conflicting_active_alert")
        checkpoint_version = freshness["checkpoint_version"]
        if any(item.source_version != checkpoint_version for item in alerts):
            return _unresolved(definition_code, "projection_freshness_unproven")
        versions = [
            (f"owner:{definition_code}:{case_no}", freshness["owner_version"]),
            (
                f"projector:{freshness['consumer_identity']}:{freshness['partition_identity']}",
                checkpoint_version,
            ),
        ]
        versions.extend((item.source_identity, item.source_version) for item in alerts)
        return CaseAnomalyDefinitionRead(definition_code, alerts, tuple(sorted(set(versions))))


def _unavailable_batch_readback(
    codes: tuple[str, ...], case_no: str, read_at: datetime | None
) -> CaseAnomalyReadback:
    require_canonical_text(case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)
    for code in codes:
        require_canonical_text(code, "definition code", 191)
    unresolved = tuple(
        (
            code,
            "consistent_snapshot_required"
            if code in SUPPORTED_CANCELLATION_DEFINITIONS
            else "definition_not_in_cancellation_readback",
        )
        for code in codes
    )
    timestamp = read_at or datetime.now(timezone.utc)
    return CaseAnomalyReadback(
        case_no=case_no,
        resolved_alerts=(),
        unresolved_definitions=unresolved,
        status=CaseAnomalyReadbackStatus.UNAVAILABLE,
        source_versions=(),
        read_at=timestamp,
    )


def _query_for(definition_code: str, case_no: str) -> tuple[str | None, tuple[Any, ...]]:
    if definition_code in _DIRECT_CASE_CODES:
        partition = _process_reminder_partition(definition_code, case_no)
        return _DIRECT_READBACK_SQL, (
            definition_code,
            case_no,
            _PROCESS_REMINDER_CONSUMER,
            partition,
            case_no,
        )
    if definition_code == "SCHEDULE-006":
        return _SCHEDULE_READBACK_SQL, (case_no, case_no)
    return None, ()


def _split_snapshot_rows(
    rows: tuple[Mapping[str, Any], ...],
    definition_code: str,
    *,
    case_no: str,
    as_of: date,
) -> tuple[tuple[CaseAnomalyAlert, ...], dict[str, Any] | None]:
    alert_rows = tuple(row for row in rows if row.get("row_kind") == "alert")
    freshness_rows = tuple(row for row in rows if row.get("row_kind") == "freshness")
    if any(row.get("row_kind") not in {"alert", "freshness"} for row in rows):
        return (), None
    try:
        alerts = tuple(_alert(row, definition_code) for row in alert_rows)
        freshness = _freshness(
            freshness_rows, definition_code, case_no=case_no, as_of=as_of
        )
    except (TypeError, ValueError):
        return (), None
    return alerts, freshness


def _process_reminder_partition(definition_code: str, case_no: str) -> str:
    digest = fingerprint_payload(
        {"code": definition_code, "fingerprint_values": {"case_no": case_no}}
    ).value
    return f"process-reminder:{definition_code}:{digest}"


def _freshness(
    rows: tuple[Mapping[str, Any], ...],
    definition_code: str,
    *,
    case_no: str,
    as_of: date,
) -> dict[str, Any] | None:
    if len(rows) != 1:
        return None
    row = rows[0]
    owner_version = _nonnegative(row.get("owner_version"), "owner version")
    checkpoint_version = row.get("checkpoint_version")
    if checkpoint_version is None:
        return None
    checkpoint_version = _nonnegative(checkpoint_version, "checkpoint version")
    consumer = _text(row, "consumer_identity")
    partition = _text(row, "partition_identity")
    if definition_code in _DIRECT_CASE_CODES:
        expected_partition = _process_reminder_partition(definition_code, case_no)
        if consumer != _PROCESS_REMINDER_CONSUMER or partition != expected_partition:
            return None
        expected_version = daily_root_source_version(as_of=as_of, root_version=owner_version)
        if checkpoint_version != expected_version:
            return None
    else:
        expected_prefix = f"SCHEDULE-006:case:{case_no}:generation:"
        if consumer != _SCHEDULE_COVERAGE_CONSUMER or not partition.startswith(expected_prefix):
            return None
        if checkpoint_version != owner_version:
            return None
    return {
        "owner_version": owner_version,
        "checkpoint_version": checkpoint_version,
        "consumer_identity": consumer,
        "partition_identity": partition,
    }


def _unresolved(code: str, reason: str) -> CaseAnomalyDefinitionRead:
    return CaseAnomalyDefinitionRead(code, unresolved_reason=reason)


def _mapping_rows(rows: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(rows, (tuple, list)) or any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("case anomaly read rows must be mappings")
    return tuple(rows)


def _alert(row: Mapping[str, Any], expected_code: str) -> CaseAnomalyAlert:
    if str(row.get("definition_code")) != expected_code:
        raise ValueError("case anomaly definition identity mismatch")
    predicate_active = row.get("predicate_active")
    if predicate_active not in (1, True):
        raise ValueError("case anomaly read returned inactive alert")
    return CaseAnomalyAlert(
        definition_code=expected_code,
        fingerprint=_text(row, "fingerprint"),
        source_identity=_text(row, "source_identity"),
        source_version=_nonnegative(row.get("source_version"), "source version"),
        workflow_status=_text(row, "workflow_status"),
    )


def _text(row: Mapping[str, Any], field: str) -> str:
    return require_canonical_text(row.get(field), field, 191)


def _nonnegative(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} is invalid")
    return value


_ALERT_COLUMNS = (
    "a.fingerprint,a.definition_code,a.source_identity,a.source_version,"
    "a.predicate_active,a.workflow_status"
)

_DIRECT_READBACK_SQL = (
    "SELECT 'alert' AS row_kind," + _ALERT_COLUMNS + ","
    "NULL AS owner_version,NULL AS checkpoint_version,NULL AS consumer_identity,"
    "NULL AS partition_identity "
    "FROM anomaly_current_alerts a "
    "WHERE a.definition_code=%s AND a.source_identity=%s AND a.predicate_active=1 "
    "UNION ALL "
    "SELECT 'freshness' AS row_kind,NULL,NULL,NULL,NULL,NULL,NULL,"
    "account.aggregate_version AS owner_version,checkpoint.source_version AS checkpoint_version,"
    "checkpoint.consumer_identity,checkpoint.partition_identity "
    "FROM client_finance_accounts account "
    "LEFT JOIN anomaly_consumer_checkpoints checkpoint "
    "ON checkpoint.consumer_identity=%s AND checkpoint.partition_identity=%s "
    "WHERE account.case_no=%s"
)
_SCHEDULE_READBACK_SQL = (
    "SELECT 'alert' AS row_kind," + _ALERT_COLUMNS + ","
    "NULL AS owner_version,NULL AS checkpoint_version,NULL AS consumer_identity,"
    "NULL AS partition_identity "
    "FROM anomaly_current_alerts a "
    "WHERE a.definition_code='SCHEDULE-006' "
    "AND a.source_identity=CONCAT('case:',%s) AND a.predicate_active=1 "
    "UNION ALL "
    "SELECT 'freshness' AS row_kind,NULL,NULL,NULL,NULL,NULL,NULL,"
    "aggregate.aggregate_version AS owner_version,checkpoint.source_version AS checkpoint_version,"
    "'scheduling-coverage-anomaly-projector-v1' AS consumer_identity,"
    "CONCAT('SCHEDULE-006:case:',aggregate.case_no,':generation:',generation.generation_number) "
    "AS partition_identity "
    "FROM scheduling_aggregates aggregate "
    "LEFT JOIN scheduling_generations generation "
    "ON generation.id=aggregate.effective_generation_id AND generation.case_no=aggregate.case_no "
    "LEFT JOIN anomaly_consumer_checkpoints checkpoint "
    "ON checkpoint.consumer_identity='scheduling-coverage-anomaly-projector-v1' "
    "AND checkpoint.partition_identity=CONCAT("
    "'SCHEDULE-006:case:',aggregate.case_no,':generation:',"
    "generation.generation_number) "
    "WHERE aggregate.case_no=%s"
)
__all__ = ["MySqlCaseAnomalyReadbackAdapter"]
