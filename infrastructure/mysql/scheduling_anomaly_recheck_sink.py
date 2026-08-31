"""Compose Scheduling-owned recheck requests into the Anomalies queue."""

from __future__ import annotations

from domains.anomalies.current_issue import RecheckIntent, RecheckScope, build_owner_lock_key
from infrastructure.mysql.current_anomaly_issue_repository import MySqlCurrentIssueRepository
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.scheduling.current_anomaly_facts import (
    SCHEDULING_ANOMALY_OWNER_DOMAIN,
    SCHEDULING_ANOMALY_OWNER_ROOT_TYPE,
    SchedulingAnomalyRecheckRequest,
    SchedulingCurrentIssueCode,
    SchedulingOverlapRecheckRequest,
)


class MySqlSchedulingAnomalyRecheckSink:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._repository = MySqlCurrentIssueRepository(connection)

    def append_scheduling_recheck(self, request: SchedulingAnomalyRecheckRequest) -> None:
        scope = RecheckScope(
            SCHEDULING_ANOMALY_OWNER_DOMAIN,
            SCHEDULING_ANOMALY_OWNER_ROOT_TYPE,
            request.definition_code.value,
            request.subject_ids,
            tuple(
                build_owner_lock_key(
                    SCHEDULING_ANOMALY_OWNER_DOMAIN,
                    SCHEDULING_ANOMALY_OWNER_ROOT_TYPE,
                    root_id,
                )
                for root_id in request.owner_root_ids
            ),
        )
        fingerprint = fingerprint_payload(
            {
                "definition_code": request.definition_code.value,
                "subject_ids": request.subject_ids,
                "owner_version": request.owner_version,
                "owner_snapshot_token": request.owner_snapshot_token,
            }
        )
        self._repository.append_recheck_intent(
            RecheckIntent(
                request.intent_identity,
                scope,
                request.owner_version,
                fingerprint,
            )
        )

    def append_scheduling_overlap_rechecks(self, request: SchedulingOverlapRecheckRequest) -> None:
        pairs = set()
        with self._connection.cursor() as cursor:
            if request.affected_staff_ids:
                placeholders = ",".join("%s" for _ in request.affected_staff_ids)
                cursor.execute(_CURRENT_OVERLAP_PAIRS_SQL.format(placeholders=placeholders), request.affected_staff_ids)
                pairs.update((int(row["assignment_id_a"]), int(row["assignment_id_b"])) for row in cursor.fetchall())
            if request.affected_assignment_ids:
                placeholders = ",".join("%s" for _ in request.affected_assignment_ids)
                values = tuple(str(value) for value in request.affected_assignment_ids)
                cursor.execute(_EXISTING_OVERLAP_ISSUES_SQL.format(placeholders=placeholders), (*values, *values))
                for row in cursor.fetchall():
                    left, separator, right = str(row["subject_id"]).partition(":")
                    if separator and left.isdecimal() and right.isdecimal():
                        pairs.add((int(left), int(right)))
        for left, right in sorted(pairs):
            self.append_scheduling_recheck(
                SchedulingAnomalyRecheckRequest(
                    SchedulingCurrentIssueCode.ASSIGNMENT_OVERLAP,
                    (str(left) + ":" + str(right),),
                    ("assignment:" + str(left), "assignment:" + str(right)),
                    request.owner_version,
                    request.owner_snapshot_token,
                    request.intent_identity + ":" + str(left) + ":" + str(right),
                )
            )


_CURRENT_OVERLAP_PAIRS_SQL = (
    "SELECT a.id AS assignment_id_a,b.id AS assignment_id_b FROM case_staff_assignments a "
    "JOIN scheduling_generations ga ON ga.id=a.generation_id AND ga.status='effective' AND ga.effective_marker=1 "
    "JOIN scheduling_aggregates saa ON saa.case_no=a.case_no AND saa.effective_generation_id=ga.id "
    "JOIN case_staff_assignments b ON b.staff_id=a.staff_id AND b.id>a.id "
    "JOIN scheduling_generations gb ON gb.id=b.generation_id AND gb.status='effective' AND gb.effective_marker=1 "
    "JOIN scheduling_aggregates sab ON sab.case_no=b.case_no AND sab.effective_generation_id=gb.id "
    "WHERE a.staff_id IN ({placeholders}) AND a.status IN ('planned','active') AND b.status IN ('planned','active') "
    "AND a.assigned_start_date<=b.assigned_end_date AND b.assigned_start_date<=a.assigned_end_date ORDER BY a.id,b.id"
)
_EXISTING_OVERLAP_ISSUES_SQL = (
    "SELECT subject_id FROM current_anomaly_issues WHERE owner_domain='scheduling' "
    "AND owner_root_type='scheduling_current_fact' AND subject_type='SCHEDULE-003' AND ("
    "JSON_UNQUOTE(JSON_EXTRACT(subject_identity,'$.assignment_id_a')) IN ({placeholders}) OR "
    "JSON_UNQUOTE(JSON_EXTRACT(subject_identity,'$.assignment_id_b')) IN ({placeholders})) ORDER BY subject_id"
)


__all__ = ["MySqlSchedulingAnomalyRecheckSink"]
