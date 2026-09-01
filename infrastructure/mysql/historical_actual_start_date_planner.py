"""MySQL facts adapter for historical actual-start official-date rebuilding."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from hashlib import sha256

from pymysql.err import IntegrityError

from domains.orders.actual_start import calculate_service_dates
from domains.scheduling.generation import (
    AssignmentCandidate,
    BufferCandidate,
    SchedulingGenerationCandidate,
)
from infrastructure.mysql.scheduling_replacement_writer import (
    persist_scheduling_replacement,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.orders.terms_workflow import SchedulingReplacementCommand
from subsystems.orders.historical_actual_start_rebuild import (
    HistoricalActualStartPreparationError,
)

_POST_SERVICE_BUFFER_DAYS = 7


class MySqlHistoricalActualStartDatePlanner:
    def __init__(self, connection) -> None:
        self._connection = connection

    def calculate(
        self,
        case_no: str,
        actual_start_date: date,
        *,
        for_update: bool,
    ) -> tuple[date, ...]:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.service_type,o.service_days FROM orders o "
                "JOIN clients c ON c.id=o.client_id WHERE o.case_no=%s" + suffix,
                (case_no,),
            )
            order = cursor.fetchone()
            if order is None:
                raise HistoricalActualStartPreparationError(
                    "historical_actual_start_order_not_found"
                )
            cursor.execute(
                "SELECT holiday_date FROM holidays WHERE holiday_date >= %s "
                "ORDER BY holiday_date" + suffix,
                (actual_start_date,),
            )
            holiday_dates = tuple(row["holiday_date"] for row in cursor.fetchall())
        try:
            return calculate_service_dates(
                actual_start_date,
                int(order["service_days"]),
                _canonical_service_mode(str(order["service_type"])),
                holiday_dates,
            )
        except (TypeError, ValueError) as error:
            raise HistoricalActualStartPreparationError(
                "historical_actual_start_source_invalid"
            ) from error

    def prepare_source_generation(
        self,
        case_no: str,
        service_dates: tuple[date, ...],
        *,
        source_identity: str,
        actor: str,
        correlation_id: str,
    ) -> None:
        """Bridge generation-less historical assignment evidence into Scheduling once."""
        with self._connection.cursor() as cursor:
            aggregate = _locked_or_bootstrapped_aggregate(cursor, case_no)
            if _effective_generation_has_assignments(
                cursor,
                aggregate,
                for_update=True,
            ):
                return
            source_assignments, order = _source_assignment_and_order_facts(
                cursor, case_no, for_update=True
            )
            candidate = _bootstrap_candidate(
                case_no,
                aggregate,
                source_assignments,
                service_dates,
                _service_hours_per_day(order),
            )
            candidate = replace(
                candidate,
                cancelled_assignment_ids=_effective_generation_assignment_ids(
                    cursor, aggregate
                ),
            )
            policy = _case_payroll_policy(cursor, case_no, for_update=True)
            command_fingerprint = _bootstrap_fingerprint(
                source_identity,
                int(order["lifecycle_version"]),
                candidate,
            )
            try:
                result = persist_scheduling_replacement(
                    cursor,
                    SchedulingReplacementCommand(
                        candidate=candidate,
                        command_family="historical_actual_start_bootstrap",
                        expected_order_version=int(order["lifecycle_version"]),
                        command_fingerprint=command_fingerprint,
                        preview_fingerprint=command_fingerprint,
                        idempotency_key=IdempotencyKey(
                            _bootstrap_idempotency_key(source_identity)
                        ),
                        actor=ActorContext(actor),
                        reason="historical actual-start scheduling bootstrap",
                        correlation_id=CorrelationId(correlation_id),
                    ),
                )
            except IntegrityError as error:
                if _is_effective_staff_date_conflict(error):
                    raise HistoricalActualStartPreparationError(
                        "historical_actual_start_staff_schedule_conflict"
                    ) from error
                raise
            _persist_rate_snapshots(cursor, candidate, result, policy)

    def preview_source_generation(
        self,
        case_no: str,
        service_dates: tuple[date, ...],
        *,
        source_staff_ids: tuple[int, ...] = (),
    ) -> None:
        """Check bootstrap prerequisites without creating a generation or writing facts."""
        with self._connection.cursor() as cursor:
            aggregate = _read_or_empty_aggregate(cursor, case_no)
            if _effective_generation_has_assignments(cursor, aggregate, for_update=False):
                return
            if source_staff_ids:
                if len(source_staff_ids) != 1 or source_staff_ids[0] <= 0:
                    raise HistoricalActualStartPreparationError(
                        "historical_assignment_required_for_actual_start"
                    )
                if service_dates != tuple(sorted(set(service_dates))) or not service_dates:
                    raise HistoricalActualStartPreparationError(
                        "historical_service_dates_invalid"
                    )
                _order_context(cursor, case_no, for_update=False)
                _case_payroll_policy(cursor, case_no, for_update=False)
                return
            source_assignments, order, _policy = _source_generation_facts(
                cursor,
                case_no,
                for_update=False,
            )
            candidate = _bootstrap_candidate(
                case_no,
                aggregate,
                source_assignments,
                service_dates,
                _service_hours_per_day(order),
            )
            # Apply replaces conflicting current projections; Preview remains
            # read-only and reports the incoming historical source as valid.


def _locked_or_bootstrapped_aggregate(cursor, case_no):
    cursor.execute(
        "SELECT aggregate_version,generation_counter,effective_generation_id "
        "FROM scheduling_aggregates WHERE case_no=%s FOR UPDATE",
        (case_no,),
    )
    row = cursor.fetchone()
    if row is not None:
        return row
    cursor.execute(
        "INSERT INTO scheduling_aggregates "
        "(case_no,aggregate_version,generation_counter) VALUES (%s,0,0)",
        (case_no,),
    )
    return {
        "aggregate_version": 0,
        "generation_counter": 0,
        "effective_generation_id": None,
    }


def _read_or_empty_aggregate(cursor, case_no):
    cursor.execute(
        "SELECT aggregate_version,generation_counter,effective_generation_id "
        "FROM scheduling_aggregates WHERE case_no=%s",
        (case_no,),
    )
    return cursor.fetchone() or {
        "aggregate_version": 0,
        "generation_counter": 0,
        "effective_generation_id": None,
    }


def _effective_generation_has_assignments(cursor, aggregate, *, for_update: bool) -> bool:
    generation_id = aggregate["effective_generation_id"]
    if generation_id is None:
        return False
    suffix = " FOR UPDATE" if for_update else ""
    cursor.execute(
        "SELECT id FROM case_staff_assignments "
        "WHERE generation_id=%s AND status NOT IN ('cancelled','replaced') "
        "ORDER BY id LIMIT 1" + suffix,
        (generation_id,),
    )
    return cursor.fetchone() is not None


def _effective_generation_assignment_ids(cursor, aggregate) -> tuple[int, ...]:
    generation_id = aggregate["effective_generation_id"]
    if generation_id is None:
        return ()
    cursor.execute(
        "SELECT id FROM case_staff_assignments WHERE generation_id=%s "
        "AND status NOT IN ('cancelled','replaced') ORDER BY id FOR UPDATE",
        (generation_id,),
    )
    return tuple(int(row["id"]) for row in cursor.fetchall())


def _historical_assignments(cursor, case_no, *, for_update: bool):
    suffix = " FOR UPDATE" if for_update else ""
    cursor.execute(
        "SELECT id,staff_id,assignment_sequence,assigned_start_date,assigned_end_date "
        "FROM case_staff_assignments "
        "WHERE case_no=%s AND generation_id IS NULL AND status='completed' "
        "ORDER BY assignment_sequence,id" + suffix,
        (case_no,),
    )
    return tuple(cursor.fetchall())


def _order_context(cursor, case_no, *, for_update: bool):
    suffix = " FOR UPDATE" if for_update else ""
    cursor.execute(
        "SELECT lifecycle_version,service_hours_per_day FROM orders "
        "WHERE case_no=%s" + suffix,
        (case_no,),
    )
    row = cursor.fetchone()
    if row is None:
        raise HistoricalActualStartPreparationError("historical_actual_start_order_not_found")
    return row


def _case_payroll_policy(cursor, case_no, *, for_update: bool):
    suffix = " FOR UPDATE" if for_update else ""
    cursor.execute(
        "SELECT policy_version,policy_kind,hourly_rate_ntd,source_identity_status "
        "FROM case_payroll_rate_policy_snapshots WHERE case_no=%s" + suffix,
        (case_no,),
    )
    row = cursor.fetchone()
    if row is None:
        raise HistoricalActualStartPreparationError("payroll_case_policy_bootstrap_required")
    return row


def _source_generation_facts(cursor, case_no, *, for_update: bool):
    source_assignments, order = _source_assignment_and_order_facts(
        cursor, case_no, for_update=for_update
    )
    return (
        source_assignments,
        order,
        _case_payroll_policy(cursor, case_no, for_update=for_update),
    )


def _source_assignment_and_order_facts(cursor, case_no, *, for_update: bool):
    source_assignments = _historical_assignments(
        cursor, case_no, for_update=for_update
    )
    if not source_assignments:
        raise HistoricalActualStartPreparationError(
            "historical_assignment_required_for_actual_start"
        )
    return source_assignments, _order_context(cursor, case_no, for_update=for_update)


def _service_hours_per_day(order) -> int:
    try:
        return int(order["service_hours_per_day"])
    except (KeyError, TypeError, ValueError) as error:
        raise HistoricalActualStartPreparationError(
            "historical_actual_start_source_invalid"
        ) from error


def _bootstrap_candidate(
    case_no,
    aggregate,
    source_assignments,
    service_dates,
    service_hours_per_day,
):
    generation_number = int(aggregate["generation_counter"]) + 1
    allocations = _allocate_service_dates(source_assignments, service_dates)
    assignments = tuple(
        _bootstrap_assignment(
            case_no,
            generation_number,
            sequence,
            source,
            assigned_dates,
            service_hours_per_day,
        )
        for sequence, (source, assigned_dates) in enumerate(allocations, start=1)
    )
    return SchedulingGenerationCandidate(
        case_no=case_no,
        generation_number=generation_number,
        expected_aggregate_version=int(aggregate["aggregate_version"]),
        resulting_aggregate_version=int(aggregate["aggregate_version"]) + 1,
        cancelled_assignment_ids=(),
        assignments=assignments,
        buffers=tuple(_inactive_buffer(item) for item in assignments),
    )


def _allocate_service_dates(source_assignments, service_dates):
    if service_dates != tuple(sorted(set(service_dates))) or not service_dates:
        raise HistoricalActualStartPreparationError("historical_service_dates_invalid")
    if len(source_assignments) == 1:
        return ((source_assignments[0], service_dates),)
    claimed: set[date] = set()
    allocations = []
    for source in source_assignments:
        assigned_dates = tuple(
            value
            for value in service_dates
            if source["assigned_start_date"] <= value <= source["assigned_end_date"]
        )
        if not assigned_dates:
            raise HistoricalActualStartPreparationError("historical_assignment_service_dates_missing")
        if any(value in claimed for value in assigned_dates):
            raise HistoricalActualStartPreparationError("historical_assignment_service_dates_overlap")
        claimed.update(assigned_dates)
        allocations.append((source, assigned_dates))
    if claimed != set(service_dates):
        raise HistoricalActualStartPreparationError("historical_assignment_service_dates_incomplete")
    return tuple(allocations)


def _bootstrap_assignment(
    case_no,
    generation_number,
    sequence,
    source,
    service_dates,
    service_hours_per_day,
):
    return AssignmentCandidate(
        candidate_key=f"{case_no}:historical:g{generation_number}:a{sequence}",
        source_assignment_id=int(source["id"]),
        staff_id=int(source["staff_id"]),
        sequence=sequence,
        assigned_start_date=service_dates[0],
        assigned_end_date=service_dates[-1],
        service_dates=service_dates,
        actual_hours=len(service_dates) * service_hours_per_day,
    )


def _inactive_buffer(assignment):
    return BufferCandidate(
        candidate_key=f"{assignment.candidate_key}:buffer",
        staff_id=assignment.staff_id,
        dates=tuple(
            assignment.assigned_end_date + timedelta(days=offset)
            for offset in range(1, _POST_SERVICE_BUFFER_DAYS + 1)
        ),
        active=False,
    )


def _bootstrap_fingerprint(source_identity, order_version, candidate):
    return fingerprint_payload(
        {
            "source_identity": source_identity,
            "case_no": candidate.case_no,
            "order_version": order_version,
            "expected_scheduling_version": candidate.expected_aggregate_version,
            "generation_number": candidate.generation_number,
            "assignments": [
                {
                    "source_assignment_id": item.source_assignment_id,
                    "staff_id": item.staff_id,
                    "sequence": item.sequence,
                    "service_dates": [value.isoformat() for value in item.service_dates],
                }
                for item in candidate.assignments
            ],
        }
    )


def _bootstrap_idempotency_key(source_identity: str) -> str:
    digest = sha256(source_identity.encode("utf-8")).hexdigest()
    return f"historical-scheduling-bootstrap:{digest}"


def _persist_rate_snapshots(cursor, candidate, result, policy) -> None:
    rows = []
    for assignment in candidate.assignments:
        assignment_id = result.assignment_resolution.assignment_id_by_candidate_key[
            assignment.candidate_key
        ]
        rows.append(
            (
                assignment_id,
                policy["policy_version"],
                policy["policy_kind"],
                policy["hourly_rate_ntd"],
                policy["source_identity_status"],
            )
        )
    cursor.executemany(
        "INSERT INTO assignment_payroll_rate_snapshots "
        "(assignment_id,policy_version,policy_kind,hourly_rate_ntd,"
        "source_identity_status) VALUES (%s,%s,%s,%s,%s)",
        tuple(rows),
    )


def _canonical_service_mode(value: str) -> str:
    aliases = {
        "週休一日": "週休1日",
        "休周日": "週休1日",
        "週休二日": "週休2日",
        "周休二日": "週休2日",
    }
    return aliases.get(value.strip(), value.strip())


def _is_effective_staff_date_conflict(error: IntegrityError) -> bool:
    return (
        error.args
        and error.args[0] == 1062
        and "uq_staff_schedule_effective_date" in str(error)
    )


__all__ = ["MySqlHistoricalActualStartDatePlanner"]
