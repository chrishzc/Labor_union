"""MySQL owner handoff for post-service official date correction."""

from __future__ import annotations

from domains.scheduling.assignment_plan import first_shift_conflict
from domains.scheduling.generation import AssignmentIdentityResolution
from domains.staff_payables.overpayment_recovery import PayrollCorrectionRecoverySource
from infrastructure.mysql.scheduling_occupancy_facts import load_case_service_time, load_occupancy_snapshot

import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


from infrastructure.mysql.order_terms_read_model import (
    load_locked_facts,
    load_preview_facts,
    lock_staff_mutexes,
    preflight_staff_ids,
    select_order,
    select_scheduling_aggregate,
)
from infrastructure.mysql.payroll_terms_writer import (
    persist_actual_start_rate_snapshot_carry, persist_payroll_rate_snapshots, persist_payroll_terms_impact,
)
from infrastructure.mysql.scheduling_replacement_writer import persist_scheduling_replacement
from infrastructure.mysql.staff_payout_repository import query_staff_funding_portions
from infrastructure.mysql.staff_overpayment_recovery_repository import MySqlStaffOverpaymentRecoveryRepository
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.orders.official_service_date_correction_workflow import (
    AttributionFundingFacts,
    AttributionFundingSource,
    OfficialAssignmentDates,
    OfficialDateFacts,
    OfficialDateHistoryRecord,
    OfficialDateOccupancyConflict,
    OfficialDateReceipt,
    OfficialDateSelection,
    MonetaryBlocker,
)
from subsystems.orders.terms_workflow import PayrollImpactPersistenceCommand
from subsystems.staff_payables.overpayment_recovery import (
    StaffOverpaymentRecoveryCreationApplication, StaffOverpaymentRecoveryCreationRequest,
)


_FAMILY = "orders_official_service_date_correction"


class MySqlOfficialServiceDateCorrectionRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load(self, case_no: str, *, lock: bool = False, include_special_pay: bool = False) -> OfficialDateFacts:
        suffix = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            order = select_order(cursor, case_no, lock=lock)
            aggregate = select_scheduling_aggregate(cursor, case_no, lock=lock)
            if lock:
                staff_ids = preflight_staff_ids(cursor, case_no)
                lock_staff_mutexes(cursor, staff_ids)
            generation_id = aggregate["effective_generation_id"]
            if generation_id is None:
                raise ValueError("official_date_effective_generation_required")
            cursor.execute(
                "SELECT id,generation_number FROM scheduling_generations "
                "WHERE id=%s AND case_no=%s AND status='effective' AND effective_marker=1" + suffix,
                (generation_id, case_no),
            )
            generation = cursor.fetchone()
            if generation is None:
                raise ValueError("official_date_effective_generation_conflict")
            cursor.execute(
                "SELECT a.id,a.staff_id,a.assignment_sequence,a.status,a.floor_fee_allocated,"
                "s.name AS staff_name FROM case_staff_assignments a "
                "JOIN staff s ON s.id=a.staff_id WHERE a.generation_id=%s "
                "AND a.status NOT IN ('cancelled','replaced') ORDER BY a.id" + suffix,
                (generation_id,),
            )
            rows = tuple(cursor.fetchall())
            if not rows:
                raise ValueError("official_date_completed_assignment_required")
            special_pay_column = ",is_double_pay" if include_special_pay else ""
            cursor.execute(
                f"SELECT assignment_id,staff_id,work_date,is_work_day{special_pay_column} "
                "FROM staff_schedule WHERE generation_id=%s AND effective_marker=1 "
                "ORDER BY work_date,assignment_id" + suffix,
                (generation_id,),
            )
            schedule = tuple(cursor.fetchall())
            by_assignment = {int(row["id"]): [] for row in rows}
            double_pay_by_assignment = {int(row["id"]): [] for row in rows}
            for day in schedule:
                assignment_id = int(day["assignment_id"])
                if assignment_id not in by_assignment or not bool(day["is_work_day"]):
                    raise ValueError("official_date_schedule_ownership_invalid")
                by_assignment[assignment_id].append(day["work_date"])
                if day.get("is_double_pay"):
                    double_pay_by_assignment[assignment_id].append(day["work_date"])
            if any(not dates for dates in by_assignment.values()):
                raise ValueError("official_date_schedule_incomplete")
            assignments = tuple(OfficialAssignmentDates(
                int(row["id"]), int(row["staff_id"]), int(row["assignment_sequence"]),
                str(row["status"]), tuple(by_assignment[int(row["id"])]), str(row["staff_name"]),
                tuple(double_pay_by_assignment[int(row["id"])]),
            ) for row in rows)
            cursor.execute("SELECT actual_end_date FROM orders WHERE case_no=%s" + suffix, (case_no,))
            actual_end_date = cursor.fetchone()["actual_end_date"]
            ids = tuple(by_assignment)
            placeholders = ",".join("%s" for _ in ids)
            cursor.execute(
                "SELECT COUNT(*) AS total FROM assignment_payroll_rate_snapshots "
                f"WHERE assignment_id IN ({placeholders})" + suffix, ids,
            )
            complete_source_rates = int(cursor.fetchone()["total"]) == len(ids)
            cursor.execute(
                "SELECT COUNT(*) AS total FROM payroll_adjustment_allocations "
                f"WHERE assignment_id IN ({placeholders})" + suffix, ids,
            )
            adjustments = int(cursor.fetchone()["total"])
            cursor.execute(
                "SELECT COUNT(*) AS total FROM client_obligations "
                "WHERE case_no=%s AND obligation_type='subsidy_return'" + suffix,
                (case_no,),
            )
            subsidy_returns = int(cursor.fetchone()["total"])
            cursor.execute(
                "SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s" + suffix,
                (case_no,),
            )
            finance = cursor.fetchone()
            cursor.execute(
                "SELECT aggregate_version FROM payroll_case_accounts WHERE case_no=%s" + suffix,
                (case_no,),
            )
            payroll = cursor.fetchone()
        # Completed service has no active buffer under Scheduling lifecycle rules.
        # A stale persistence marker is neither service occupancy nor monetary impact.
        blocker_facts: tuple[tuple[MonetaryBlocker, bool | int], ...] = (
            ("payroll_adjustments", adjustments),
            ("subsidy_return", subsidy_returns),
            ("source_rate_snapshot_missing_or_ambiguous", not complete_source_rates),
            ("floor_fee", any(int(row["floor_fee_allocated"] or 0) for row in rows)),
        )
        monetary_blockers = tuple(code for code, present in blocker_facts if present)
        return OfficialDateFacts(
            case_no=case_no,
            order_version=int(order["lifecycle_version"]),
            order_status=str(order["status"]),
            actual_start_date=order["actual_start_date"],
            actual_end_date=actual_end_date,
            service_data_locked=bool(order["service_data_locked"]),
            service_days=int(order["service_days"]),
            hours_per_day=float(order["service_hours_per_day"]),
            scheduling_version=int(aggregate["aggregate_version"]),
            generation_id=int(generation_id),
            generation_number=int(generation["generation_number"]),
            assignments=assignments,
            monetary_change_blocker=bool(monetary_blockers),
            client_finance_version=int(finance["aggregate_version"]) if finance else None,
            payroll_version=int(payroll["aggregate_version"]) if payroll else None,
            monetary_blockers=monetary_blockers,
        )

    def load_attribution(self, case_no: str, change, *, lock: bool):
        return self._load_attribution_facts(case_no, change, lock=lock)

    def load_funding_review(self, case_no: str, *, lock: bool):
        return self._load_attribution_facts(case_no, None, lock=lock)

    def _load_attribution_facts(self, case_no, change, *, lock):
        suffix = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            pending = self._funding_pending(cursor, case_no)
            if change is None and pending is None:
                return None
            staff_ids = set(preflight_staff_ids(cursor, case_no))
            if change is not None:
                staff_ids.update(change.target_staff_ids)
            if pending:
                staff_ids.update(pending[1])
            staff_ids = tuple(sorted(staff_ids))
            if lock:
                def lock_payables(locked_cursor):
                    placeholders = ",".join("%s" for _ in staff_ids)
                    locked_cursor.execute(
                        f"SELECT staff_id FROM staff_payable_accounts WHERE staff_id IN ({placeholders}) "
                        "ORDER BY staff_id FOR UPDATE", staff_ids,
                    )
                    locked_cursor.fetchall()
                terms = load_locked_facts(cursor, case_no, staff_ids, lock_payables)
                if not set(preflight_staff_ids(cursor, case_no)).issubset(staff_ids):
                    raise ValueError("official_date_version_conflict")
                pending = self._funding_pending(cursor, case_no, lock=True)
                if pending and not set(pending[1]).issubset(staff_ids):
                    raise ValueError("official_date_version_conflict")
                if change is None and pending is None:
                    return None
            else:
                terms = load_preview_facts(cursor, case_no)
            facts = self.load(case_no, lock=lock, include_special_pay=True)
            if change is not None:
                current_owners = {item.assignment_id: item.staff_id for item in facts.assignments}
                required_active = {move.staff_id for move in change.moves if (
                    current_owners.get(move.source_assignment_id) != move.staff_id
                    or move.source_assignment_id != move.target_assignment_id
                    or move.source_date != move.replacement_date
                )}
                if not change.moves and (
                    current_owners.get(change.source_assignment_id) != change.staff_id
                    or (change.replacement_dates and change.replacement_dates != change.service_dates)
                ):
                    required_active.add(change.staff_id)
                for staff_id in sorted(required_active):
                    cursor.execute(
                        "SELECT s.status, COALESCE(l.lifecycle_state,'active') AS lifecycle_state "
                        "FROM staff s LEFT JOIN staff_lifecycle_states l ON l.staff_id=s.id "
                        "WHERE s.id=%s" + suffix, (staff_id,),
                    )
                    person = cursor.fetchone()
                    if person is None or person["status"] != "active":
                        raise ValueError("service_attribution_staff_required")
                    if person["lifecycle_state"] == "retired":
                        raise ValueError("service_attribution_retired_staff_blocked")
            affected = set(pending[1]) if pending else set()
            if change is not None:
                affected.update(change.target_staff_ids)
                affected.update(a.staff_id for a in facts.assignments if a.assignment_id in change.source_assignment_ids)
            affected_ids = tuple(sorted(affected))
            affected_slots = ",".join("%s" for _ in affected_ids)
            cursor.execute(
                "SELECT c.obligation_identity,o.staff_id,c.computed_ntd,c.effective_ntd,c.amount_mode FROM payroll_amount_controls c "
                "JOIN staff_obligations o ON o.obligation_identity=c.obligation_identity "
                f"WHERE o.case_no=%s AND o.status<>'cancelled' AND o.staff_id IN ({affected_slots}) "
                "ORDER BY c.obligation_identity" + suffix,
                (case_no, *affected_ids),
            )
            controls = tuple(cursor.fetchall())
            manual_amounts = tuple((str(row["obligation_identity"]), int(row["staff_id"]),
                                    int(row["computed_ntd"]), int(row["effective_ntd"])) for row in controls
                                   if row["amount_mode"] == "manual")
            placeholders = ",".join("%s" for _ in staff_ids)
            cursor.execute(
                f"SELECT staff_id,aggregate_version FROM staff_payable_accounts WHERE staff_id IN ({placeholders}) "
                "ORDER BY staff_id" + suffix, staff_ids,
            )
            payable_versions = tuple((int(row["staff_id"]), int(row["aggregate_version"])) for row in cursor.fetchall())
            funding, paid_roots = [], set()
            previous_recoveries = self._funding_recoveries(cursor, case_no) if pending or change else {}
            for root in terms.payroll.existing_obligations if terms.payroll is not None else ():
                if root.staff_id not in affected or root.obligation_kind.value != "service_pay":
                    continue
                portions = query_staff_funding_portions(cursor, root.obligation_identity, lock=lock,
                    settled_total=root.paid_net_amount.amount)
                if root.payout_history_exists:
                    paid_roots.add(root.obligation_identity)
                if portions:
                    for part in portions:
                        recovered = previous_recoveries.get((root.obligation_identity, part.funding_kind), 0)
                        funding.append(AttributionFundingSource(root.obligation_identity, root.staff_id,
                            root.source_assignment_id, part.funding_kind,
                            part.amount_ntd - recovered, part.settled_ntd, part.due_date, recovered))
                else:
                    funding.append(AttributionFundingSource(root.obligation_identity, root.staff_id,
                        root.source_assignment_id, "unsplit",
                        root.contractual_amount.amount, root.paid_net_amount.amount, root.due_date))
        return facts, terms, payable_versions, manual_amounts, AttributionFundingFacts(tuple(funding),
            pending[1] if pending else (), pending[0] if pending else None,
            tuple(str(row["obligation_identity"]) for row in controls if row["obligation_identity"] in paid_roots))

    def _funding_pending(self, cursor, case_no, *, lock=False):
        cursor.execute("SELECT id, facts_snapshot FROM order_lifecycle_state_events WHERE case_no=%s AND "
            "trigger_event IN ('official_service_attribution_corrected','official_service_attribution_funding_confirmed') "
            "AND JSON_CONTAINS_PATH(facts_snapshot,'one','$.funding_review') ORDER BY id DESC LIMIT 1"
            + (" FOR UPDATE" if lock else ""), (case_no,))
        row = cursor.fetchone()
        if row:
            review = json.loads(row["facts_snapshot"])["funding_review"]
            if review["state"] == "pending":
                return int(row["id"]), tuple(review["staff_ids"])
        return None

    def _funding_recoveries(self, cursor, case_no):
        cursor.execute("SELECT facts_snapshot FROM order_lifecycle_state_events WHERE case_no=%s "
                       "AND trigger_event='official_service_attribution_funding_confirmed' ORDER BY id", (case_no,))
        result = {}
        for row in cursor.fetchall():
            for identity, kind, amount in json.loads(row["facts_snapshot"])["recoveries"]:
                result[(identity, kind)] = result.get((identity, kind), 0) + amount
        return result

    def validate_availability(self, candidate, *, lock: bool) -> None:
        staff_ids = tuple(sorted({item.staff_id for item in candidate.assignments}))
        with self._connection.cursor() as cursor:
            occupied, _ = load_occupancy_snapshot(cursor, staff_ids, candidate.case_no, lock=lock)
            service_time = load_case_service_time(cursor, candidate.case_no, lock=lock)
            conflict = first_shift_conflict(candidate.case_no, service_time, candidate.assignments, occupied)
            if conflict:
                cursor.execute("SELECT name FROM staff WHERE id=%s", (conflict.staff_id,))
                row = cursor.fetchone()
                raise OfficialDateOccupancyConflict(row["name"] if row else str(conflict.staff_id), conflict.occupancy_date)

    def load_history(self, case_no: str) -> tuple[OfficialDateHistoryRecord, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT e.id,e.actor,e.created_at,e.facts_snapshot,"
                "l.lifecycle_event_id AS completion_event_id "
                "FROM order_lifecycle_state_events e "
                "LEFT JOIN order_service_data_locks l "
                "ON l.case_no=e.case_no AND l.lifecycle_event_id=e.id "
                "WHERE e.case_no=%s AND (l.lifecycle_event_id IS NOT NULL "
                "OR e.trigger_event='official_service_date_corrected') ORDER BY e.id",
                (case_no,),
            )
            rows = tuple(cursor.fetchall())
        records = []
        for row in rows:
            snapshot = json.loads(row["facts_snapshot"])
            original = row["completion_event_id"] is not None
            facts = snapshot.get("authoritative_facts", {}) if original else snapshot
            before = () if original else tuple(sorted({
                date.fromisoformat(day) for dates in facts["before"].values() for day in dates
            }))
            after = tuple(date.fromisoformat(day) for day in facts.get("official_service_dates", [])) if original else tuple(sorted({
                date.fromisoformat(day) for dates in facts["after"].values() for day in dates
            }))
            instant = snapshot.get("completion_instant") if original else None
            records.append(OfficialDateHistoryRecord(
                event_id=int(row["id"]),
                event_type="original_completion" if original else "service_date_corrected",
                recorded_at=row["created_at"].replace(tzinfo=timezone.utc),
                actor=str(row["actor"]), before_dates=before, after_dates=after,
                reason=None if original else snapshot.get("reason"),
                completion_instant=datetime.fromisoformat(instant) if instant else None,
            ))
        return tuple(records)

    def replay(self, key: str, command_fingerprint: str, *, lock: bool = False) -> OfficialDateReceipt | None:
        return self._replay(key, command_fingerprint, (_FAMILY,), lock=lock)

    def replay_attribution(self, key: str, command_fingerprint: str, *, lock: bool = False) -> OfficialDateReceipt | None:
        return self._replay(key, command_fingerprint, (
            "orders_service_attribution", "orders_completed_service_attribution",
        ), lock=lock)

    def _replay(self, key, command_fingerprint, families, *, lock):
        suffix = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT command_family,command_fingerprint,preview_fingerprint,case_no,"
                "resulting_scheduling_version,resulting_generation_id FROM scheduling_command_receipts "
                "WHERE idempotency_key=%s" + suffix, (key,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            if row["command_family"] not in families or row["command_fingerprint"] != command_fingerprint:
                raise ValueError("official_date_idempotency_mismatch")
            cursor.execute(
                "SELECT expected_version,facts_snapshot FROM order_lifecycle_state_events "
                "WHERE case_no=%s AND idempotency_key=%s" + suffix,
                (row["case_no"], key),
            )
            event = cursor.fetchone()
            if event is None:
                raise RuntimeError("official_date_receipt_incomplete")
            cursor.execute(
                "SELECT assignment_id,work_date FROM staff_schedule "
                "WHERE generation_id=%s AND is_work_day=1 ORDER BY assignment_id,work_date" + suffix,
                (row["resulting_generation_id"],),
            )
            dates = {}
            for item in cursor.fetchall():
                dates.setdefault(int(item["assignment_id"]), []).append(item["work_date"])
        return OfficialDateReceipt(
            str(row["case_no"]), int(event["expected_version"]) + 1,
            int(row["resulting_scheduling_version"]), int(row["resulting_generation_id"]),
            tuple(OfficialDateSelection(identity, tuple(values)) for identity, values in dates.items()),
            PreviewFingerprint(str(row["preview_fingerprint"])),
            bool(json.loads(event["facts_snapshot"]).get("funding_review")),
        )

    def replay_funding_review(self, case_no: str, key: str, digest: str, *, lock: bool = False):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT trigger_event,facts_snapshot FROM order_lifecycle_state_events "
                           "WHERE case_no=%s AND idempotency_key=%s" + (" FOR UPDATE" if lock else ""), (case_no, key))
            row = cursor.fetchone()
            if not row:
                return False
            if (row["trigger_event"] != "official_service_attribution_funding_confirmed"
                    or json.loads(row["facts_snapshot"])["command_fingerprint"] != digest):
                raise ValueError("official_date_idempotency_mismatch")
            return True

    def persist_funding_review(self, review, *, actor, key, correlation, digest):
        facts = review.facts
        reason = review.evidence
        recoveries = []
        recovery_identities = {}
        with self._connection.cursor() as cursor:
            resolution = AssignmentIdentityResolution({str(item.assignment_id): item.assignment_id
                                                      for item in facts.assignments})
            persist_payroll_terms_impact(cursor, PayrollImpactPersistenceCommand(
                review.payroll, resolution, key, actor, reason, correlation, review.accounting.pending_event_id,
                reuse_existing_assignments=True,
                replace_unpaid_amount_controls=tuple(item[0] for item in review.manual_amounts),
                installment_staff_ids=frozenset(),
            ))
            recovery_owner = StaffOverpaymentRecoveryCreationApplication(
                MySqlStaffOverpaymentRecoveryRepository(self._connection))
            for item in review.plan:
                cursor.executemany(
                    "INSERT INTO staff_obligation_installments(obligation_identity,funding_kind,amount_ntd,due_date) "
                    "VALUES(%s,%s,%s,%s) ON DUPLICATE KEY UPDATE amount_ntd=VALUES(amount_ntd),due_date=VALUES(due_date)",
                    tuple((item.identity, part.funding_kind, part.amount, part.due_date) for part in item.installments),
                )
                for kind, amount in item.recovery:
                    recovery_digest = fingerprint_payload({"case": facts.case_no,
                        "event": review.accounting.pending_event_id, "obligation": item.identity, "kind": kind}).value
                    recovery = recovery_owner.create_from_payroll_correction(StaffOverpaymentRecoveryCreationRequest(
                        PayrollCorrectionRecoverySource("service-funding:" + recovery_digest, facts.case_no, item.identity,
                            item.staff_id, MoneyNTD(amount)),
                        IdempotencyKey("service-funding-recovery:" + recovery_digest), actor, reason, correlation,
                        evidence_reference=f"schedule-funding:{review.accounting.pending_event_id}:{kind}",
                    ))
                    recoveries.append((item.identity, kind, amount))
                    recovery_identities[recovery.recovery_identity] = {"obligation_identity": item.identity,
                                                                       "funding_kind": kind}
            snapshot = {
                "funding_review": {"state": "confirmed", "pending_event_id": review.accounting.pending_event_id},
                "command_fingerprint": digest, "preview_fingerprint": review.fingerprint.value,
                "generation_id": facts.generation_id, "evidence": review.evidence, "recoveries": recoveries,
                "recovery_identities": recovery_identities,
                "original_funding": [(part.identity, part.staff_id, part.kind, part.amount, part.settled,
                                      part.due_date.isoformat() if part.due_date else None)
                                     for part in review.accounting.sources],
                "installments": [(item.identity, item.staff_id, part.funding_kind, part.amount,
                                  part.due_date.isoformat() if part.due_date else None)
                                 for item in review.plan for part in item.installments],
                "approved_funding": [(item.identity, item.staff_id, *part)
                                     for item in review.plan for part in item.revised],
            }
            cursor.execute(
                "INSERT INTO order_lifecycle_state_events "
                "(case_no,trigger_event,before_status,after_status,actor,business_date,expected_version,idempotency_key,facts_snapshot) "
                "VALUES (%s,'official_service_attribution_funding_confirmed',%s,%s,%s,%s,%s,%s,%s)",
                (facts.case_no, facts.order_status, facts.order_status, actor.actor_id,
                 datetime.now(ZoneInfo("Asia/Taipei")).date(), facts.order_version, key.value, json.dumps(snapshot, ensure_ascii=False)),
            )

    def persist_attribution(self, command, preview) -> OfficialDateReceipt:
        facts = preview.facts
        with self._connection.cursor() as cursor:
            result = persist_scheduling_replacement(cursor, command)
            payroll = PayrollImpactPersistenceCommand(
                preview.payroll, result.assignment_resolution, command.idempotency_key,
                command.actor, command.reason, command.correlation_id, result.rebuild_event_id,
                special_pay_events=preview.payroll.special_pay_events,
                replace_unpaid_amount_controls=tuple(item[0] for item in preview.manual_amounts),
                installment_staff_ids=frozenset(row[0] for row in preview.funding),
            )
            if preview.funding_review_staff:
                persist_payroll_rate_snapshots(cursor, payroll)
            else:
                persist_payroll_terms_impact(cursor, payroll)
            before = {str(a.assignment_id): [d.isoformat() for d in a.service_dates] for a in facts.assignments}
            after = {str(result.assignment_resolution.assignment_id_by_candidate_key[a.candidate_key]):
                     [d.isoformat() for d in a.service_dates] for a in command.candidate.assignments}
            dates_changed = {d for dates in before.values() for d in dates} != {d for dates in after.values() for d in dates}
            end = max(d for a in command.candidate.assignments for d in a.service_dates) if dates_changed else facts.actual_end_date
            start = min(d for a in command.candidate.assignments for d in a.service_dates) if dates_changed else facts.actual_start_date
            cursor.execute(
                "INSERT INTO order_lifecycle_state_events "
                "(case_no,trigger_event,before_status,after_status,actor,business_date,"
                "expected_version,idempotency_key,facts_snapshot) "
                "VALUES (%s,'official_service_attribution_corrected',%s,%s,%s,%s,%s,%s,%s)",
                (facts.case_no, facts.order_status, facts.order_status, command.actor.actor_id,
                 datetime.now(ZoneInfo("Asia/Taipei")).date(), facts.order_version,
                 command.idempotency_key.value, json.dumps({
                     "previous_generation_id": facts.generation_id,
                     "successor_generation_id": result.generation_id,
                     "scheduling_receipt_id": result.scheduling_receipt_id,
                     "before": before, "after": after,
                     "reason": command.reason, "evidence": preview.evidence,
                     **({"funding_review": {"state": "pending", "staff_ids": preview.funding_review_staff,
                         "obligation_ids": preview.funding_review_roots}} if preview.funding_review_staff else {}),
                 }, ensure_ascii=False)),
            )
            cursor.execute(
                "UPDATE orders SET actual_start_date=%s,actual_end_date=%s,lifecycle_version=lifecycle_version+1 "
                "WHERE case_no=%s AND lifecycle_version=%s AND status=%s",
                (start, end, facts.case_no, facts.order_version, facts.order_status),
            )
            if cursor.rowcount != 1:
                raise ValueError("official_date_version_conflict")
        return OfficialDateReceipt(
            facts.case_no, facts.order_version + 1, result.scheduling_version, result.generation_id,
            tuple(OfficialDateSelection(
                result.assignment_resolution.assignment_id_by_candidate_key[assignment.candidate_key],
                assignment.service_dates,
            ) for assignment in command.candidate.assignments), preview.fingerprint, bool(preview.funding_review_staff),
        )

    def replace_and_record(self, command, preview) -> OfficialDateReceipt:
        with self._connection.cursor() as cursor:
            result = persist_scheduling_replacement(cursor, command)
            persist_actual_start_rate_snapshot_carry(cursor, command, result)
            effective_dates = tuple(OfficialDateSelection(
                result.assignment_resolution.assignment_id_by_candidate_key[assignment.candidate_key],
                assignment.service_dates,
            ) for assignment in command.candidate.assignments)
            new_end = max(day for item in effective_dates for day in item.service_dates)
            cursor.execute(
                "INSERT INTO order_lifecycle_state_events "
                "(case_no,trigger_event,before_status,after_status,actor,business_date,"
                "expected_version,idempotency_key,facts_snapshot) "
                "VALUES (%s,'official_service_date_corrected',%s,%s,%s,%s,%s,%s,%s)",
                (
                    command.candidate.case_no, preview.facts.order_status,
                    preview.facts.order_status, command.actor.actor_id,
                    datetime.now(ZoneInfo("Asia/Taipei")).date(),
                    preview.facts.order_version, command.idempotency_key.value,
                    json.dumps({
                        "previous_generation_id": preview.facts.generation_id,
                        "successor_generation_id": result.generation_id,
                        "scheduling_receipt_id": result.scheduling_receipt_id,
                        "before": {str(a.assignment_id): [d.isoformat() for d in a.service_dates] for a in preview.facts.assignments},
                        "after": {str(a.assignment_id): [d.isoformat() for d in a.service_dates] for a in preview.selections},
                        "reason": command.reason,
                        "finance_impact": "no_op",
                        "payroll_impact": "no_op",
                    }, ensure_ascii=False, sort_keys=True),
                ),
            )
            cursor.execute(
                "UPDATE orders SET actual_end_date=%s,lifecycle_version=%s "
                "WHERE case_no=%s AND lifecycle_version=%s AND status='訂單完成'",
                (
                    new_end, preview.facts.order_version + 1,
                    command.candidate.case_no, preview.facts.order_version,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("official_date_version_conflict")
        return OfficialDateReceipt(
            command.candidate.case_no, preview.facts.order_version + 1,
            result.scheduling_version, result.generation_id, effective_dates,
            preview.fingerprint,
        )
