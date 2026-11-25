"""Persist Scheduling date adjustments without replacing assignment or financial facts."""

import json
from datetime import date
from decimal import Decimal

from pymysql.err import IntegrityError

from domains.scheduling.assignment_plan import service_shift_may_overlap
from domains.scheduling.service_date_adjustment import ServiceDateAdjustment, ServiceDay
from infrastructure.mysql.matching_schedule_confirmation_repository import MySqlMatchingScheduleConfirmationRepository
from infrastructure.mysql.order_terms_read_model import lock_staff_mutexes, select_scheduling_aggregate
from infrastructure.mysql.scheduling_occupancy_facts import load_case_service_time, load_occupancy_snapshot
from subsystems.scheduling.service_date_adjustment import (
    ServiceDateAdjustmentFacts,
    ServiceDateAdjustmentPair,
    ServiceDateAdjustmentReceipt,
    service_day_payload,
)


class MySqlServiceDateAdjustmentRepository:
    def __init__(self, connection):
        self._connection = connection

    def load(self, case_no, *, lock=False):
        suffix = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT o.lifecycle_version,o.service_hours_per_day,COALESCE(a.aggregate_version,0) AS scheduling_version,"
                "a.effective_generation_id,o.service_days,o.start_date,o.actual_start_date "
                "FROM orders o LEFT JOIN scheduling_aggregates a ON a.case_no=o.case_no "
                "WHERE o.case_no=%s" + suffix, (case_no,),
            )
            order = cursor.fetchone()
            if order is None:
                raise ValueError("service_date_adjustment_case_not_found")
            cursor.execute(
                "SELECT id,version,scheduling_version FROM confirmed_service_date_versions WHERE case_no=%s AND is_current=1" + suffix,
                (case_no,),
            )
            confirmed_version = cursor.fetchone()
            generation_id = order["effective_generation_id"]
            staff_rows = _formal_staff(cursor, generation_id, suffix) if generation_id else ()
            formal = _formal_days(cursor, generation_id, suffix) if generation_id else ()
            if formal:
                receipts = _load_formal_receipts(cursor, case_no, confirmed_version, suffix)
                days = formal
                selectable, planned_owners = (), ()
            else:
                generation_id = None
                staff_rows = _planned_staff(cursor, case_no, suffix)
                days = _planned_days(cursor, confirmed_version["id"], staff_rows, suffix) if confirmed_version else ()
                receipts = _load_planned_receipts(cursor, case_no, confirmed_version, suffix)
                from infrastructure.mysql.service_date_confirmation_repository import MySqlServiceDateConfirmationRepository
                selectable = MySqlServiceDateConfirmationRepository._selectable_dates(order)
                planned_owners = tuple((day, owner) for day in selectable
                                       if (owner := _planned_owner(day, staff_rows)) is not None)
            pairs = _active_pairs(receipts, days)
            first_schedule_days = (
                _original_schedule(days, receipts, int(confirmed_version["version"]), int(confirmed_version["scheduling_version"]))
                if generation_id is None and confirmed_version and any(day.hours_override is not None for day in days)
                else ()
            )
        return ServiceDateAdjustmentFacts(
            case_no, int(order["lifecycle_version"] or 0), int(order["scheduling_version"]),
            int(confirmed_version["version"]) if confirmed_version else None,
            int(generation_id) if generation_id else None, Decimal(str(order["service_hours_per_day"] or 0)),
            days, tuple(dict.fromkeys((int(row["staff_id"]), str(row["name"])) for row in staff_rows)), pairs,
            int(order["service_days"]), selectable, planned_owners,
            first_schedule_days,
        )

    def lock_case_and_staff(self, case_no, staff_ids):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT case_no FROM orders WHERE case_no=%s FOR UPDATE", (case_no,))
            if cursor.fetchone() is None:
                raise ValueError("service_date_adjustment_case_not_found")
            aggregate = select_scheduling_aggregate(cursor, case_no, lock=True)
            generation_id = aggregate["effective_generation_id"]
            rows = (_formal_staff(cursor, generation_id, "")
                    if generation_id and _formal_days(cursor, generation_id, "")
                    else _planned_staff(cursor, case_no, ""))
            fresh_staff_ids = {int(row["staff_id"]) for row in rows}
            if not fresh_staff_ids.issubset(staff_ids):
                raise ValueError("scheduling_lock_set_stale")
            lock_staff_mutexes(cursor, staff_ids)

    def replay(self, key, fingerprint, *, lock=False):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,command_fingerprint,result_snapshot FROM service_date_adjustment_receipts "
                "WHERE idempotency_key=%s" + (" FOR UPDATE" if lock else ""), (key,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        if row["command_fingerprint"] != fingerprint:
            raise ValueError("service_date_adjustment_idempotency_conflict")
        snapshot = _parse_snapshot(row["result_snapshot"])
        return ServiceDateAdjustmentReceipt(int(row["id"]), snapshot["scheduling_version"], snapshot["confirmed_version"])

    def validate_availability(self, facts, change, *, lock):
        with self._connection.cursor() as cursor:
            _validate_formal_targets(cursor, facts.case_no, change.inserted, lock=lock)

    def save(self, preview, request, *, key, fingerprint, actor):
        facts, change = preview.facts, preview.change
        with self._connection.cursor() as cursor:
            if facts.generation_id is None:
                scheduling_version, confirmed_version = facts.scheduling_version, _write_confirmed(
                    cursor, preview, actor,
                )
                MySqlMatchingScheduleConfirmationRepository(self._connection).invalidate_current_snapshot(facts.case_no)
            else:
                _write_formal(cursor, facts.case_no, facts.generation_id, change, restore=request.reverse_receipt_id is not None)
                scheduling_version, confirmed_version = facts.scheduling_version + 1, facts.confirmed_version
                cursor.execute(
                    "UPDATE scheduling_aggregates SET aggregate_version=%s WHERE case_no=%s "
                    "AND aggregate_version=%s AND effective_generation_id=%s",
                    (scheduling_version, facts.case_no, facts.scheduling_version, facts.generation_id),
                )
                if cursor.rowcount != 1:
                    raise ValueError("service_date_adjustment_stale_version")
                from infrastructure.mysql.order_lifecycle_impact_writer import persist_order_scheduled_end_projection

                try:
                    persist_order_scheduled_end_projection(
                        cursor, case_no=facts.case_no,
                        actual_end_date=max(day.service_date for day in change.days),
                        expected_order_version=facts.order_version,
                    )
                except RuntimeError as error:
                    if str(error) == "order_version_conflict":
                        raise ValueError("service_date_adjustment_stale_version") from error
                    raise
            snapshot = {
                "removed": [service_day_payload(day) for day in change.removed],
                "inserted": [service_day_payload(day) for day in change.inserted],
                "scheduling_version": scheduling_version,
                "confirmed_version": confirmed_version,
            }
            try:
                cursor.execute(
                    "INSERT INTO service_date_adjustment_receipts (case_no,idempotency_key,command_fingerprint,"
                    "actor_id,reverse_receipt_id,result_snapshot) VALUES (%s,%s,%s,%s,%s,%s)",
                    (facts.case_no, key, fingerprint, actor, request.reverse_receipt_id, json.dumps(snapshot)),
                )
            except IntegrityError as error:
                if error.args[0] == 1062:
                    raise ValueError("service_date_adjustment_idempotency_conflict") from error
                raise
            return ServiceDateAdjustmentReceipt(int(cursor.lastrowid), scheduling_version, confirmed_version)


def _formal_days(cursor, generation_id, suffix):
    cursor.execute(
        "SELECT work_date AS service_date,staff_id,service_hours_override FROM staff_schedule "
        "WHERE generation_id=%s AND is_work_day=1 AND effective_marker=1 ORDER BY work_date" + suffix,
        (generation_id,),
    )
    return tuple(_service_day(row) for row in cursor.fetchall())


def load_payroll_service_dates(cursor, generation_id, assignments, service_days, *, lock):
    """Keep date-only adjustments separate from the assignment's financial basis."""
    original = load_unadjusted_service_dates(
        cursor, generation_id, tuple(int(row["id"]) for row in assignments), service_days, lock=lock,
    )
    if original:
        return _cancellation_floor_identities(cursor, generation_id, service_days, original, lock=lock)
    # Financial corrections own a new basis. Do not freeze it across non-neutral rebuilds.
    cursor.execute(
        "SELECT assignment_id,work_date FROM staff_schedule "
        "WHERE generation_id=%s AND effective_marker=1 AND is_work_day=1 "
        "ORDER BY assignment_id,work_date" + (" FOR UPDATE" if lock else ""), (generation_id,),
    )
    rows = tuple(cursor.fetchall())
    return _cancellation_floor_identities(cursor, generation_id, service_days, rows, lock=lock)


def load_unadjusted_service_dates(cursor, generation_id, assignment_ids, service_days, *, lock):
    """Read normal-day history and its one-to-one path to current assignments."""
    suffix = " FOR UPDATE" if lock else ""
    current_generation = generation_id
    identities = {assignment_id: assignment_id for assignment_id in assignment_ids}
    visited = set()
    while current_generation not in visited:
        visited.add(current_generation)
        cursor.execute(
            "SELECT assignment_id,work_date FROM staff_schedule "
            "WHERE generation_id=%s AND is_work_day=1 AND service_hours_override IS NULL "
            "ORDER BY assignment_id,work_date" + suffix, (current_generation,),
        )
        original = tuple(cursor.fetchall())
        if len(original) == service_days:
            current_by_source = {source: current for current, source in identities.items()}
            if all(int(row["assignment_id"]) in current_by_source for row in original):
                return tuple({"assignment_id": current_by_source[int(row["assignment_id"])],
                              "financial_assignment_identity": f"assignment:{int(row['assignment_id'])}",
                              "work_date": row["work_date"]} for row in original)
        cursor.execute(
            "SELECT lineage.new_assignment_id,old.id AS source_assignment_id,old.generation_id AS source_generation_id "
            "FROM scheduling_rebuild_lineage lineage "
            "JOIN scheduling_command_receipts receipt ON receipt.rebuild_event_id=lineage.rebuild_event_id "
            "JOIN case_staff_assignments current_assignment ON current_assignment.id=lineage.new_assignment_id "
            "JOIN case_staff_assignments old ON lineage.old_assignment_identity=CONCAT('assignment:',old.id) "
            "WHERE current_assignment.generation_id=%s AND old.case_no=current_assignment.case_no "
            "AND old.staff_id=current_assignment.staff_id AND receipt.command_family='orders_actual_start_rebuild' "
            "ORDER BY lineage.new_assignment_id,lineage.lineage_ordinal" + suffix, (current_generation,),
        )
        sources = tuple(cursor.fetchall())
        by_assignment = {int(row["new_assignment_id"]): int(row["source_assignment_id"]) for row in sources}
        source_generations = {int(row["source_generation_id"]) for row in sources}
        if (len(by_assignment) != len(sources) or len(set(by_assignment.values())) != len(sources)
                or len(source_generations) != 1
                or set(by_assignment) != set(identities.values())):
            break
        identities = {current: by_assignment[source] for current, source in identities.items()}
        current_generation = next(iter(source_generations))
    return ()


def _cancellation_floor_identities(cursor, generation_id, service_days, rows, *, lock):
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT lineage.new_assignment_id,old.id AS source_assignment_id,old.generation_id AS source_generation_id "
        "FROM scheduling_rebuild_lineage lineage "
        "JOIN scheduling_command_receipts receipt ON receipt.rebuild_event_id=lineage.rebuild_event_id "
        "JOIN case_staff_assignments current_assignment ON current_assignment.id=lineage.new_assignment_id "
        "JOIN case_staff_assignments old ON lineage.old_assignment_identity=CONCAT('assignment:',old.id) "
        "WHERE current_assignment.generation_id=%s AND old.case_no=current_assignment.case_no "
        "AND old.staff_id=current_assignment.staff_id AND receipt.command_family='orders_cancellation' "
        "ORDER BY lineage.new_assignment_id,lineage.lineage_ordinal" + suffix, (generation_id,),
    )
    lineage = tuple(cursor.fetchall())
    if not lineage:
        return rows
    parents = {int(row["new_assignment_id"]): int(row["source_assignment_id"]) for row in lineage}
    generations = {int(row["source_generation_id"]) for row in lineage}
    if len(parents) != len(lineage) or len(generations) != 1:
        raise ValueError("payroll_assignment_lineage_invalid")
    parent_generation = next(iter(generations))
    if parent_generation >= generation_id:
        raise ValueError("payroll_assignment_lineage_invalid")
    cursor.execute(
        "SELECT id,staff_id FROM case_staff_assignments WHERE generation_id=%s ORDER BY id" + suffix,
        (parent_generation,),
    )
    assignments = tuple(cursor.fetchall())
    basis = load_payroll_service_dates(cursor, parent_generation, assignments, service_days, lock=lock)
    identities = {int(row["assignment_id"]): row.get("financial_assignment_identity", f"assignment:{row['assignment_id']}")
                  for row in basis}
    return tuple(dict(row, financial_assignment_identity=identities.get(
        parents.get(int(row["assignment_id"])),
        f"assignment:{parents[int(row['assignment_id'])]}" if int(row["assignment_id"]) in parents
        else row.get("financial_assignment_identity", f"assignment:{row['assignment_id']}"),
    )) for row in rows)


def _validate_formal_targets(cursor, case_no, days, *, lock):
    staff_ids = tuple(sorted({day.staff_id for day in days if day.staff_id is not None}))
    current, _ = load_occupancy_snapshot(cursor, staff_ids, case_no, lock=lock)
    terms = load_case_service_time(cursor, case_no, lock=lock)
    for day in days:
        for item in current:
            if item.staff_id != day.staff_id or item.source_case_no == case_no or item.reservation_only:
                continue
            if day.hours_override is not None:
                blocked = item.all_day and item.occupancy_date <= day.service_date <= (item.block_end or date.max)
            else:
                blocked = service_shift_may_overlap(day.service_date, terms, item)
            if blocked:
                raise ValueError("service_date_adjustment_staff_availability_conflict")


def _formal_staff(cursor, generation_id, suffix):
    cursor.execute(
        "SELECT a.id AS assignment_id,a.staff_id,s.name FROM case_staff_assignments a JOIN staff s ON s.id=a.staff_id "
        "WHERE a.generation_id=%s AND a.status NOT IN ('cancelled','replaced') "
        "ORDER BY a.assignment_sequence,a.id" + suffix, (generation_id,),
    )
    return cursor.fetchall()


def _planned_staff(cursor, case_no, suffix):
    cursor.execute(
        "SELECT s.id AS staff_id,s.name,segment.assigned_start_date,segment.assigned_end_date "
        "FROM caregiver_matching_plan_segments segment JOIN caregiver_matching_plans p ON p.id=segment.plan_id "
        "JOIN staff s ON s.id=segment.staff_id WHERE p.case_no=%s AND p.is_active=1 "
        "ORDER BY segment.segment_order" + suffix, (case_no,),
    )
    rows = cursor.fetchall()
    if rows:
        return rows
    cursor.execute(
        "SELECT s.id AS staff_id,s.name,a.assigned_start_date,a.assigned_end_date "
        "FROM case_staff_assignments a JOIN staff s ON s.id=a.staff_id "
        "WHERE a.case_no=%s AND a.status NOT IN ('cancelled','replaced') ORDER BY a.id" + suffix, (case_no,),
    )
    return cursor.fetchall()


def _planned_days(cursor, confirmed_id, staff_rows, suffix):
    cursor.execute(
        "SELECT service_date,staff_id,service_hours_override FROM confirmed_service_date_days "
        "WHERE confirmed_version_id=%s ORDER BY ordinal" + suffix, (confirmed_id,),
    )
    result = []
    for row in cursor.fetchall():
        day = _service_day(row)
        if day.staff_id is None:
            day = ServiceDay(day.service_date, _planned_owner(day.service_date, staff_rows), day.hours_override)
        result.append(day)
    return tuple(result)


def _planned_owner(day, staff_rows):
    matching = {int(staff["staff_id"]) for staff in staff_rows
                if staff["assigned_start_date"] and staff["assigned_end_date"]
                and staff["assigned_start_date"] <= day <= staff["assigned_end_date"]}
    distinct = {int(staff["staff_id"]) for staff in staff_rows}
    owners = matching if len(matching) == 1 else distinct
    return next(iter(owners)) if len(owners) == 1 else None


def _service_day(row):
    return ServiceDay(row["service_date"], int(row["staff_id"]) if row["staff_id"] is not None else None,
                      row["service_hours_override"])


def _parse_snapshot(raw):
    return json.loads(raw) if isinstance(raw, (str, bytes)) else raw


def _snapshot_days(rows):
    return tuple(ServiceDay(date.fromisoformat(row["service_date"]), row["staff_id"], row["hours_override"]) for row in rows)


def _load_receipts(cursor, case_no, suffix):
    cursor.execute(
        "SELECT id,reverse_receipt_id,result_snapshot FROM service_date_adjustment_receipts "
        "WHERE case_no=%s ORDER BY id" + suffix, (case_no,),
    )
    return tuple(cursor.fetchall())


def _load_formal_receipts(cursor, case_no, current_confirmation, suffix):
    cursor.execute(
        "SELECT receipt.resulting_scheduling_version FROM scheduling_command_receipts receipt "
        "JOIN order_actual_start_apply_receipts actual_receipt "
        "ON actual_receipt.scheduling_command_receipt_id=receipt.id AND actual_receipt.case_no=receipt.case_no "
        "WHERE receipt.case_no=%s AND receipt.command_family='orders_actual_start_rebuild' "
        "AND JSON_CONTAINS_PATH(actual_receipt.result_snapshot,'one','$.service_date_adjustment_reset')=1 "
        "ORDER BY receipt.resulting_scheduling_version DESC LIMIT 1" + suffix, (case_no,),
    )
    rebuild_barrier = cursor.fetchone()
    receipts = _load_receipts(cursor, case_no, suffix)
    if not receipts:
        return ()
    # A planned receipt shares the exact Scheduling version of the confirmation
    # it created. Preserve only planned receipts still carried by the current
    # confirmation. This also applies after a reset followed by first scheduling.
    cursor.execute(
        "SELECT version,scheduling_version FROM confirmed_service_date_versions "
        "WHERE case_no=%s" + suffix, (case_no,),
    )
    confirmation_versions = {row["version"]: row["scheduling_version"] for row in cursor.fetchall()}
    active_planned = {row["id"] for row in _planned_receipt_chain(receipts, current_confirmation)}
    active = []
    for row in receipts:
        snapshot = _parse_snapshot(row["result_snapshot"])
        if snapshot["scheduling_version"] == confirmation_versions.get(snapshot["confirmed_version"]):
            if row["id"] in active_planned:
                active.append(row)
            continue
        if (rebuild_barrier is None
                or snapshot["scheduling_version"] > rebuild_barrier["resulting_scheduling_version"]):
            active.append(row)
    return tuple(active)


def _load_planned_receipts(cursor, case_no, current, suffix):
    if current is None:
        return ()
    return _planned_receipt_chain(_load_receipts(cursor, case_no, suffix), current)


def _planned_receipt_chain(receipts, current):
    if current is None:
        return ()
    by_version = {}
    for row in receipts:
        snapshot = _parse_snapshot(row["result_snapshot"])
        if snapshot["scheduling_version"] == current["scheduling_version"]:
            by_version.setdefault(snapshot["confirmed_version"], row)
    version = int(current["version"])
    chain = []
    while version in by_version:
        chain.append(by_version[version])
        version -= 1
    return tuple(reversed(chain))


def _active_pairs(receipts, days):
    pairs = {}
    pairing_by_day = {}
    displaced = {}
    for row in receipts:
        receipt_id = int(row["id"])
        snapshot = _parse_snapshot(row["result_snapshot"])
        removed, inserted = _snapshot_days(snapshot["removed"]), _snapshot_days(snapshot["inserted"])
        for day in removed:
            previous = pairing_by_day.pop(day.service_date, None)
            if previous is not None:
                displaced.setdefault(receipt_id, {})[day.service_date] = previous
        if row["reverse_receipt_id"] is not None:
            pairing_by_day.update(displaced.get(row["reverse_receipt_id"], {}))
        else:
            pairs[receipt_id] = ServiceDateAdjustmentPair(
                receipt_id, ServiceDateAdjustment(removed, inserted, (), Decimal(0)),
            )
            pairing_by_day.update((day.service_date, receipt_id) for day in inserted)
    current = {day.service_date: day for day in days}
    return tuple(pair for key, pair in pairs.items()
                 if all(pairing_by_day.get(day.service_date) == key and current.get(day.service_date) == day
                        for day in pair.change.inserted))


def _original_schedule(days, receipts, confirmed_version, scheduling_version):
    original = {day.service_date: day for day in days}
    snapshots_by_version = {}
    for row in receipts:
        snapshot = _parse_snapshot(row["result_snapshot"])
        if snapshot["scheduling_version"] == scheduling_version:
            snapshots_by_version[snapshot["confirmed_version"]] = snapshot
    if confirmed_version not in snapshots_by_version:
        raise ValueError("service_date_adjustment_stale_first_schedule")
    while confirmed_version in snapshots_by_version:
        snapshot = snapshots_by_version[confirmed_version]
        for day in _snapshot_days(snapshot["inserted"]):
            if original.get(day.service_date) != day:
                raise ValueError("service_date_adjustment_stale_first_schedule")
            del original[day.service_date]
        for day in _snapshot_days(snapshot["removed"]):
            if day.service_date in original:
                raise ValueError("service_date_adjustment_stale_first_schedule")
            original[day.service_date] = day
        confirmed_version -= 1
    return tuple(original[key] for key in sorted(original))


def load_first_schedule_dates(cursor, case_no, *, lock):
    """Read the unchanged execution basis and its current planned date adjustments."""
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT v.id,v.version,v.scheduling_version FROM confirmed_service_date_versions v WHERE v.case_no=%s AND v.is_current=1 "
        "AND EXISTS (SELECT 1 FROM confirmed_service_date_days day WHERE day.confirmed_version_id=v.id "
        "AND day.service_hours_override IS NOT NULL)" + suffix, (case_no,),
    )
    current = cursor.fetchone()
    if not current:
        return (), ()
    staff = _planned_staff(cursor, case_no, suffix)
    days = _planned_days(cursor, current["id"], staff, suffix)
    receipts = _load_planned_receipts(cursor, case_no, current, suffix)
    return _original_schedule(days, receipts, int(current["version"]), int(current["scheduling_version"])), days


def carry_first_schedule_dates(cursor, case_no, generation_id, days):
    current = _formal_days(cursor, generation_id, " FOR UPDATE")
    before, after = ({day.service_date: day for day in part} for part in (current, days))
    if any(day.staff_id is None for day in days):
        after = {key: day if day.staff_id is not None else before.get(key, day) for key, day in after.items()}
    removed = tuple(day for key, day in before.items() if day != after.get(key))
    inserted = tuple(day for key, day in after.items() if day != before.get(key))
    _validate_formal_targets(cursor, case_no, inserted, lock=True)
    _write_formal(cursor, case_no, generation_id, ServiceDateAdjustment(removed, inserted, (), Decimal(0)), restore=False)


def _write_confirmed(cursor, preview, actor):
    facts, change = preview.facts, preview.change
    cursor.execute(
        "UPDATE confirmed_service_date_versions SET is_current=NULL,invalidated_at_utc=UTC_TIMESTAMP(6) "
        "WHERE case_no=%s AND is_current=1", (facts.case_no,),
    )
    cursor.execute("SELECT COALESCE(MAX(version),0) AS version FROM confirmed_service_date_versions WHERE case_no=%s",
                   (facts.case_no,))
    next_version = int(cursor.fetchone()["version"]) + 1
    cursor.execute(
        "INSERT INTO confirmed_service_date_versions (case_no,version,order_version,scheduling_version,"
        "service_day_count,service_date_fingerprint,is_current,confirmed_by_actor_id) VALUES (%s,%s,%s,%s,%s,%s,1,%s)",
        (facts.case_no, next_version, facts.order_version, facts.scheduling_version, len(change.days), preview.fingerprint, actor),
    )
    confirmed_id = cursor.lastrowid
    cursor.executemany(
        "INSERT INTO confirmed_service_date_days (confirmed_version_id,ordinal,service_date,staff_id,service_hours_override) "
        "VALUES (%s,%s,%s,%s,%s)",
        [(confirmed_id, ordinal, day.service_date, day.staff_id, day.hours_override)
         for ordinal, day in enumerate(change.days, start=1)],
    )
    return next_version


def _write_formal(cursor, case_no, generation_id, change, *, restore):
    staff = _formal_staff(cursor, generation_id, " FOR UPDATE")
    by_staff = {int(row["staff_id"]): int(row["assignment_id"]) for row in reversed(staff)}
    if any(day.staff_id not in by_staff for day in change.inserted):
        raise ValueError("service_date_adjustment_staff_ownership_conflict")
    for day in change.removed:
        cursor.execute(
            "UPDATE staff_schedule SET effective_marker=NULL WHERE generation_id=%s AND work_date=%s "
            "AND is_work_day=1 AND effective_marker=1 AND staff_id=%s AND service_hours_override <=> %s",
            (generation_id, day.service_date, day.staff_id, day.hours_override),
        )
        if cursor.rowcount != 1:
            raise ValueError("service_date_adjustment_stale_source")
        cursor.execute(
            "DELETE FROM scheduling_effective_occupancy WHERE generation_id=%s AND staff_id=%s AND occupancy_date=%s "
            "AND occupancy_type='assignment_interval'", (generation_id, day.staff_id, day.service_date),
        )
    for day in change.inserted:
        assignment_id = by_staff[day.staff_id]
        cursor.execute(
            "UPDATE staff_schedule SET effective_marker=NULL WHERE generation_id=%s AND work_date=%s "
            "AND is_work_day=0 AND effective_marker=1", (generation_id, day.service_date),
        )
        schedule_id = None
        if restore:
            cursor.execute(
                "SELECT id,assignment_id FROM staff_schedule WHERE generation_id=%s AND work_date=%s AND staff_id=%s "
                "AND service_hours_override <=> %s AND is_work_day=1 AND effective_marker IS NULL "
                "ORDER BY id DESC LIMIT 1 FOR UPDATE", (generation_id, day.service_date, day.staff_id, day.hours_override),
            )
            previous = cursor.fetchone()
            if previous is not None:
                schedule_id, assignment_id = previous["id"], previous["assignment_id"]
        if schedule_id is None:
            cursor.execute(
                "INSERT INTO staff_schedule (case_no,staff_id,work_date,assignment_id,generation_id,"
                "is_work_day,is_double_pay,effective_marker,service_hours_override) VALUES (%s,%s,%s,%s,%s,1,0,1,%s)",
                (case_no, day.staff_id, day.service_date, assignment_id, generation_id, day.hours_override),
            )
        else:
            cursor.execute("UPDATE staff_schedule SET effective_marker=1 WHERE id=%s", (schedule_id,))
        cursor.execute(
            "INSERT INTO scheduling_effective_occupancy (staff_id,occupancy_date,generation_id,assignment_id,"
            "occupancy_type) VALUES (%s,%s,%s,%s,'assignment_interval') "
            "ON DUPLICATE KEY UPDATE assignment_id=VALUES(assignment_id)",
            (day.staff_id, day.service_date, generation_id, assignment_id),
        )
