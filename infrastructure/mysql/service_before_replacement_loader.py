"""
File: service_before_replacement_loader.py
Description: 以同一借用連線組合服務前換人的 Scheduling、Matching、Contract Signing 與 LINE 根事實。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from domains.scheduling.service_before_replacement import (
    AuthoritativeActualServiceProof,
    CandidatePoolReuseProof,
    ReplacementRootIdentity,
    ReplacementRootKind,
    ReplacementScenario,
    ServiceBeforeReplacementFacts,
    SuccessorRoundFact,
)
from infrastructure.mysql.matching_coordination_facts_adapter import (
    MatchingCoordinationFactsAdapterError,
)
from shared_kernel.clock import BusinessClock, SystemBusinessClock, TAIPEI_TIME_ZONE
from shared_kernel.fingerprints import fingerprint_payload


class ServiceBeforeReplacementSourceUnavailable(RuntimeError):
    """A canonical owner source is missing, partial, ambiguous, or stale."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class MySqlServiceBeforeReplacementLoader:
    """Read composite owner facts without owning connection or transaction lifecycle."""

    def __init__(self, connection: Any, matching_facts: Any, clock: BusinessClock | None = None) -> None:
        self._connection = connection
        self._matching_facts = matching_facts
        self._clock = clock or SystemBusinessClock()

    def load_facts(self, request: object, *, for_update: bool) -> ServiceBeforeReplacementFacts:
        try:
            case_no, scenario = _request_identity(request)
            base, schedules = self._scheduling_base(case_no, for_update=for_update)
            successor = (
                self._successor_round(case_no, base=base, for_update=for_update)
                if scenario is ReplacementScenario.R07
                else None
            )
            prior = self._r07_prior(case_no, base, for_update) if successor is not None else base
            roots = self._scenario_roots(case_no, scenario, base, schedules, for_update=for_update)
            actual_dates = self._started_service_dates(base, schedules)
            proof = AuthoritativeActualServiceProof(
                case_no=case_no,
                service_dates=actual_dates,
                source_identity=f"scheduling.official-service:{case_no}:generation:{base['generation_id']}",
                source_version=_required_int(base, "aggregate_version"),
            )
            reuse = self._candidate_reuse(case_no, base, for_update=for_update)
            reason = getattr(request, "reason", None) or "service_before_replacement"
            evidence = getattr(request, "evidence", None) or ()
            if not isinstance(evidence, (tuple, list)):
                raise TypeError("replacement evidence is malformed")
            return ServiceBeforeReplacementFacts(
                case_no=case_no,
                scenario=scenario,
                actual_service_dates=actual_dates,
                prior_generation_identity=(
                    str(prior["prior_generation_identity"])
                    if successor is not None
                    else f"scheduling-generation:{case_no}:{base['generation_id']}:{base['generation_number']}"
                ),
                prior_event_identity=str(prior["prior_event_identity"]),
                generation_version=_required_int(
                    prior, "expected_generation_version"
                    if successor is not None else "generation_number"
                ),
                event_version=_required_int(
                    prior, "expected_event_version" if successor is not None else "event_version"
                ),
                current_roots=roots,
                candidate_pool_reuse=reuse,
                actual_service_proof_available=True,
                actual_service_proof=proof,
                aggregate_version=_required_int(
                    prior, "expected_aggregate_version" if successor is not None else "aggregate_version"
                ),
                prior_aggregate_identity=f"scheduling-aggregate:{case_no}",
                replacement_reason=str(reason),
                reason_evidence=tuple(evidence),
                successor_round=successor,
                candidate_pool_round_identity=None if reuse is None else reuse.round_identity,
                candidate_identity=None if reuse is None else reuse.candidate_identity,
            )
        except ServiceBeforeReplacementSourceUnavailable:
            raise
        except (AttributeError, IndexError, KeyError, OverflowError, TypeError, ValueError) as error:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_source_malformed") from error

    def load_matching_source(self, request: object, *, for_update: bool) -> Mapping[str, Any]:
        try:
            case_no, _scenario = _request_identity(request)
            projection = self._matching_facts.load_sources(case_no, for_update=for_update)
            snapshot = projection.matching_criteria_snapshot
            package = projection.matching_package
            if package is None:
                raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_parent_package_unavailable")
            source_versions = _matching_source_payload(projection.source_versions)
            snapshot_versions = getattr(snapshot, "source_versions", None)
            if snapshot_versions is not None and tuple(_matching_source_payload(snapshot_versions)) != source_versions:
                raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_source_version_drift")
            criteria_digest = fingerprint_payload(
                {
                    "case_no": case_no,
                    "criteria": snapshot.criteria,
                    "criteria_version": _required_int(snapshot, "criteria_version"),
                    "source_versions": tuple(
                        (
                            item["source_kind"], item["source_id"], item["version"], item["fingerprint"]
                        )
                        for item in source_versions
                    ),
                }
            ).value
            snapshot_digest = getattr(snapshot.fingerprint, "value", snapshot.fingerprint)
            if snapshot_versions is not None and snapshot_digest != criteria_digest:
                raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_criteria_digest_drift")
            event = self._one(
                "SELECT event.event_id,event.case_no,event.event_type,event.resulting_version,"
                "event.criteria_snapshot_id,event.package_lineage_id,event.event_payload,event.source_version_tuple,"
                "criteria.id AS expected_snapshot_row_id,criteria.snapshot_id AS expected_snapshot_id,"
                "package.id AS expected_package_row_id,package.package_id AS expected_package_id,"
                "package.package_snapshot,package.source_version_tuple AS package_source_version_tuple,"
                "criteria.source_version_tuple AS criteria_source_version_tuple "
                "FROM matching_coordination_events event "
                "JOIN matching_coordination_package_lineage package ON package.id=event.package_lineage_id "
                "JOIN matching_coordination_criteria_snapshots criteria ON criteria.id=event.criteria_snapshot_id "
                "WHERE event.case_no=%s AND criteria.snapshot_id=%s AND package.package_id=%s "
                "ORDER BY event.id DESC LIMIT 1",
                (case_no, snapshot.snapshot_id, package.package_id),
                for_update,
            )
            if event is None:
                raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_source_event_unavailable")
            _validate_matching_event_binding(event, case_no, snapshot, package)
            event_sources = _matching_source_payload(event.get("source_version_tuple"))
            package_sources = _matching_source_payload(event.get("package_source_version_tuple"))
            criteria_sources = _matching_source_payload(event.get("criteria_source_version_tuple"))
            if event_sources != source_versions or package_sources != source_versions or criteria_sources != source_versions:
                raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_source_version_drift")
            required_dates = tuple(projection.orders_service_dates.current_dates)
            if any(type(value) is not date for value in required_dates) or required_dates != tuple(sorted(set(required_dates))):
                raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_service_dates_malformed")
            return {
                "snapshot_id": snapshot.snapshot_id,
                "case_no": case_no,
                "criteria_version": snapshot.criteria_version,
                "criteria": snapshot.criteria,
                "source_versions": source_versions,
                "criteria_digest": criteria_digest,
                "parent_package": package,
                "source_event_identity": str(event["event_id"]),
                "required_service_dates": required_dates,
                "reuse_package": package if package.candidate_results else None,
            }
        except ServiceBeforeReplacementSourceUnavailable:
            raise
        except MatchingCoordinationFactsAdapterError as error:
            raise ServiceBeforeReplacementSourceUnavailable(
                f"replacement_matching_{error.source_kind}_{error.reason}"
            ) from error
        except Exception as error:
            raise ServiceBeforeReplacementSourceUnavailable(
                "replacement_matching_sources_unavailable"
            ) from error

    def _scheduling_base(self, case_no: str, *, for_update: bool):
        base = self._one(
            "SELECT orders.case_no,orders.service_start_time,orders.service_days,"
            "aggregate.aggregate_version,aggregate.case_no AS aggregate_case_no,"
            "aggregate.generation_counter,generation.id AS generation_id,generation.generation_number,"
            "generation.case_no AS generation_case_no,generation.status,generation.effective_marker,"
            "rebuild.id AS rebuild_event_id,rebuild.case_no AS rebuild_case_no,"
            "rebuild.new_generation_id,rebuild.previous_generation_id,"
            "rebuild.expected_scheduling_version,rebuild.resulting_scheduling_version,"
            "latest.replacement_event_identity AS latest_replacement_identity,"
            "latest.replacement_generation_id AS latest_replacement_generation_id,"
            "latest.resulting_aggregate_version AS latest_replacement_aggregate_version,"
            "latest.resulting_generation_version AS latest_replacement_generation_version,"
            "latest.resulting_event_version AS latest_replacement_version "
            "FROM orders "
            "JOIN scheduling_aggregates aggregate ON aggregate.case_no=orders.case_no "
            "JOIN scheduling_generations generation ON generation.id=aggregate.effective_generation_id "
            "LEFT JOIN scheduling_rebuild_events rebuild ON rebuild.new_generation_id=generation.id "
            "LEFT JOIN scheduling_service_before_replacement_events latest "
            "ON latest.id=(SELECT MAX(e.id) FROM scheduling_service_before_replacement_events e WHERE e.case_no=orders.case_no) "
            "WHERE orders.case_no=%s",
            (case_no,),
            for_update,
        )
        if base is None:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_scheduling_root_unavailable")
        if (
            base.get("case_no") != case_no
            or base.get("aggregate_case_no") != case_no
            or base.get("generation_case_no") != case_no
            or base.get("status") != "effective"
            or base.get("effective_marker") != 1
        ):
            raise ServiceBeforeReplacementSourceUnavailable("replacement_effective_generation_unavailable")
        generation_id = _required_positive_int(base, "generation_id")
        generation_number = _required_positive_int(base, "generation_number")
        aggregate_version = _required_nonnegative_int(base, "aggregate_version")
        generation_counter = _required_nonnegative_int(base, "generation_counter")
        latest_identity_value = base.get("latest_replacement_identity")
        if latest_identity_value is not None:
            latest_identity = _required_text(base, "latest_replacement_identity")
            if (
                generation_counter != generation_number
                or _required_positive_int(base, "latest_replacement_generation_id") != generation_id
                or _required_int(base, "latest_replacement_generation_version") != generation_number
                or _required_int(base, "latest_replacement_aggregate_version") != aggregate_version
            ):
                raise ServiceBeforeReplacementSourceUnavailable("replacement_prior_event_generation_drift")
            base = dict(base)
            base["prior_event_identity"] = latest_identity
            base["event_version"] = _required_int(base, "latest_replacement_version")
            schedules = self._scheduling_rows(case_no, generation_id, for_update=for_update)
            return base, schedules
        if base.get("rebuild_event_id") is None:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_prior_event_unavailable")
        rebuild_event_id = _required_positive_int(base, "rebuild_event_id")
        rebuild_expected_version = _required_nonnegative_int(
            base, "expected_scheduling_version"
        )
        rebuild_resulting_version = _required_nonnegative_int(
            base, "resulting_scheduling_version"
        )
        previous_generation_id = base.get("previous_generation_id")
        previous_generation_valid = (
            previous_generation_id is None
            if generation_number == 1
            else isinstance(previous_generation_id, int)
            and not isinstance(previous_generation_id, bool)
            and previous_generation_id > 0
            and previous_generation_id != generation_id
        )
        if (
            generation_counter != generation_number
            or base.get("rebuild_case_no") != case_no
            or _required_positive_int(base, "new_generation_id") != generation_id
            or not previous_generation_valid
            or rebuild_expected_version + 1 != rebuild_resulting_version
            or rebuild_resulting_version != aggregate_version
        ):
            raise ServiceBeforeReplacementSourceUnavailable(
                "replacement_rebuild_predecessor_binding_drift"
            )
        base = dict(base)
        base["prior_event_identity"] = f"scheduling-rebuild-event:{case_no}:{rebuild_event_id}"
        base["event_version"] = _required_int(base, "resulting_scheduling_version")
        schedules = self._scheduling_rows(case_no, generation_id, for_update=for_update)
        return base, schedules

    def _scheduling_rows(self, case_no: str, generation_id: int, *, for_update: bool):
        schedules = self._all(
            "SELECT assignment.id AS assignment_id,assignment.staff_id,assignment.assignment_sequence,"
            "assignment.status AS assignment_status,schedule.id AS schedule_id,schedule.work_date,"
            "schedule.is_work_day,schedule.effective_marker "
            "FROM case_staff_assignments assignment JOIN staff_schedule schedule "
            "ON schedule.assignment_id=assignment.id AND schedule.generation_id=assignment.generation_id "
            "WHERE assignment.case_no=%s AND assignment.generation_id=%s "
            "ORDER BY assignment.assignment_sequence,assignment.id,schedule.work_date,schedule.id",
            (case_no, generation_id),
            for_update,
        )
        return schedules

    def _started_service_dates(self, base: Mapping[str, Any], schedules: tuple[Mapping[str, Any], ...]) -> tuple[date, ...]:
        start_time = base.get("service_start_time")
        now = self._clock.now()
        if not isinstance(now, datetime) or now.tzinfo is None or start_time is None or not hasattr(start_time, "hour"):
            raise ServiceBeforeReplacementSourceUnavailable("replacement_business_clock_proof_unavailable")
        now = now.astimezone(TAIPEI_TIME_ZONE)
        values: set[date] = set()
        for row in schedules:
            if not isinstance(row, Mapping) or any(key not in row for key in (
                "assignment_id", "staff_id", "assignment_sequence", "assignment_status",
                "schedule_id", "work_date", "is_work_day", "effective_marker",
            )):
                raise ServiceBeforeReplacementSourceUnavailable("replacement_official_schedule_malformed")
            _required_positive_int(row, "assignment_id")
            _required_positive_int(row, "staff_id")
            _required_positive_int(row, "assignment_sequence")
            _required_positive_int(row, "schedule_id")
            work_date = row.get("work_date")
            if type(work_date) is not date or row.get("effective_marker") not in (1, None) or row.get("is_work_day") not in (1, 0):
                raise ServiceBeforeReplacementSourceUnavailable("replacement_official_schedule_malformed")
            if row.get("effective_marker") != 1 or row.get("is_work_day") != 1:
                continue
            moment = datetime.combine(work_date, start_time).replace(tzinfo=TAIPEI_TIME_ZONE)
            if moment <= now:
                values.add(work_date)
        return tuple(sorted(values))

    def _scenario_roots(self, case_no, scenario, base, schedules, *, for_update):
        if scenario is ReplacementScenario.R01:
            pool, entries, events = self._pool(case_no, for_update)
            relevant_ids = tuple(
                int(row["id"])
                for row in entries
                if row.get("active_marker") == 1 and row.get("status") in {"active", "selected"}
            )
            if not relevant_ids:
                raise ServiceBeforeReplacementSourceUnavailable("replacement_candidate_pool_current_set_empty")
            return (
                _root(ReplacementRootKind.CANDIDATE_BINDING, case_no, "matching.candidate-pool", (pool, entries, tuple(e for e in events if e.get("event_type") == "candidates_added"))),
                _root(ReplacementRootKind.WILLINGNESS, case_no, "matching.willingness", _latest_per(events, "candidate_id", "willingness_changed", relevant_ids)),
            )
        if scenario is ReplacementScenario.R02:
            plan, segments = self._plan(case_no, for_update)
            service_dates = self._orders_service_dates(case_no, for_update)
            _validate_segment_coverage(segments, service_dates)
            reply = self._matching_reply(case_no, plan, segments, service_dates, for_update)
            recipients = self._recipients(
                case_no, int(plan["id"]), segments, service_dates,
                require_confirmed=True, for_update=for_update,
            )
            return (
                _root(ReplacementRootKind.MATCHING_PLAN, case_no, "matching.plan", (plan,)),
                _root(ReplacementRootKind.MATCHING_SEGMENT, case_no, "matching.segments", segments),
                _root(ReplacementRootKind.MATCHING_REPLY, case_no, "matching.customer-decision", (reply,)),
                _root(ReplacementRootKind.RECIPIENT_CONFIRMATION, case_no, "matching.recipient-confirmation", recipients),
            )
        if scenario is ReplacementScenario.R03:
            plan, segments = self._plan(case_no, for_update)
            service_dates = self._orders_service_dates(case_no, for_update)
            _validate_segment_coverage(segments, service_dates)
            recipients = self._recipients(
                case_no, int(plan["id"]), segments, service_dates,
                require_confirmed=False, for_update=for_update,
            )
            return (
                _root(ReplacementRootKind.WAITING_LOCK, case_no, "scheduling.waiting-lock", self._waiting_lock(int(plan["id"]), segments, service_dates, for_update)),
                _root(ReplacementRootKind.COMMITMENT, case_no, "scheduling.commitment", self._commitment(case_no, int(plan["id"]), segments, service_dates, for_update)),
                _root(ReplacementRootKind.SIGNBACK, case_no, "contract-signing.signback", self._signback(case_no, int(plan["id"]), segments, for_update)),
                _root(ReplacementRootKind.RECIPIENT_BINDING, case_no, "scheduling.recipient-binding", self._recipient_bindings(recipients, for_update)),
            )
        if scenario is ReplacementScenario.R04:
            if not schedules:
                raise ServiceBeforeReplacementSourceUnavailable("replacement_official_schedule_unavailable")
            assignments = tuple({int(row["assignment_id"]): (int(row["assignment_id"]), int(row["staff_id"]), int(row["assignment_sequence"]), row["assignment_status"]) for row in schedules}.values())
            official = tuple(row for row in schedules if row.get("effective_marker") == 1 and row.get("is_work_day") == 1)
            if not official:
                raise ServiceBeforeReplacementSourceUnavailable("replacement_official_schedule_unavailable")
            return (
                _root(ReplacementRootKind.EFFECTIVE_GENERATION, case_no, "scheduling.effective-generation", (base,)),
                _root(ReplacementRootKind.ASSIGNMENT, case_no, "scheduling.assignment-set", assignments),
                _root(ReplacementRootKind.OFFICIAL_SCHEDULE, case_no, "scheduling.official-schedule-set", official),
            )
        successor = self._successor_round(case_no, for_update=for_update)
        if successor is None:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_successor_round_unavailable")
        return (_root(ReplacementRootKind.SUCCESSOR_ROUND, case_no, "matching.successor-round", (successor.canonical_tuple,)),)

    def _pool(self, case_no, for_update):
        pool = self._one("SELECT id,case_no FROM caregiver_candidate_contact_pools WHERE case_no=%s", (case_no,), for_update)
        if pool is None or pool.get("case_no") != case_no:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_candidate_pool_unavailable")
        _required_positive_int(pool, "id")
        entries = self._all("SELECT id,pool_id,staff_id,status,active_marker FROM caregiver_candidate_contact_entries WHERE pool_id=%s ORDER BY id", (pool["id"],), for_update)
        events = self._all("SELECT id,pool_id,candidate_id,event_type,event_key,payload FROM caregiver_candidate_contact_events WHERE pool_id=%s ORDER BY id", (pool["id"],), for_update)
        added = tuple(row for row in events if row.get("event_type") == "candidates_added")
        if not entries or not added:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_candidate_pool_partial")
        added_ids = []
        for row in entries:
            if (
                _required_positive_int(row, "id") <= 0
                or _required_positive_int(row, "pool_id") != _required_positive_int(pool, "id")
                or _required_positive_int(row, "staff_id") <= 0
                or row.get("status") not in {"active", "selected", "withdrawn"}
                or row.get("active_marker") not in (1, None)
            ):
                raise ServiceBeforeReplacementSourceUnavailable("replacement_candidate_pool_partial")
        for event in added:
            if _required_positive_int(event, "id") <= 0 or _required_positive_int(event, "pool_id") != _required_positive_int(pool, "id"):
                raise ServiceBeforeReplacementSourceUnavailable("replacement_candidate_pool_partial")
            payload = _json_object(event.get("payload"))
            values = payload.get("candidate_ids", ())
            if not isinstance(values, list):
                raise ServiceBeforeReplacementSourceUnavailable("replacement_candidate_pool_set_drift")
            added_ids.extend(values)
        if (
            len(added_ids) != len(set(added_ids))
            or tuple(sorted(added_ids)) != tuple(sorted(int(row["id"]) for row in entries))
        ):
            raise ServiceBeforeReplacementSourceUnavailable("replacement_candidate_pool_set_drift")
        return pool, entries, events

    def _plan(self, case_no, for_update):
        rows = self._all("SELECT id,case_no,version,status,is_active,start_date,end_date FROM caregiver_matching_plans WHERE case_no=%s AND status='accepted' AND is_active=1 ORDER BY version DESC", (case_no,), for_update)
        if len(rows) != 1:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_plan_unavailable")
        plan = rows[0]
        if (
            plan.get("case_no") != case_no
            or _required_positive_int(plan, "id") <= 0
            or _required_positive_int(plan, "version") <= 0
            or plan.get("status") != "accepted"
            or plan.get("is_active") != 1
            or type(plan.get("start_date")) is not date
            or type(plan.get("end_date")) is not date
            or plan["start_date"] > plan["end_date"]
        ):
            raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_plan_malformed")
        segments = self._all("SELECT id,plan_id,segment_order,staff_id,assigned_start_date,assigned_end_date FROM caregiver_matching_plan_segments WHERE plan_id=%s ORDER BY segment_order,id", (plan["id"],), for_update)
        if not 1 <= len(segments) <= 4 or tuple(int(row["segment_order"]) for row in segments) != tuple(range(1, len(segments) + 1)):
            raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_segments_incomplete")
        staff_ids = []
        for row in segments:
            if (
                row.get("plan_id") != plan["id"]
                or _required_positive_int(row, "id") <= 0
                or _required_positive_int(row, "segment_order") <= 0
                or _required_positive_int(row, "staff_id") <= 0
                or type(row.get("assigned_start_date")) is not date
                or type(row.get("assigned_end_date")) is not date
                or row["assigned_start_date"] > row["assigned_end_date"]
            ):
                raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_segments_malformed")
            staff_ids.append(row["staff_id"])
        if len(staff_ids) != len(set(staff_ids)):
            raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_segments_staff_drift")
        return plan, segments

    def _matching_reply(self, case_no, plan, segments, service_dates, for_update):
        projection = self._matching_facts.load_sources(case_no, for_update=for_update)
        snapshot = projection.matching_criteria_snapshot
        package = projection.matching_package
        if package is None:
            raise ServiceBeforeReplacementSourceUnavailable(
                "replacement_matching_reply_package_unavailable"
            )
        current_sources = _matching_source_payload(projection.source_versions)
        row = self._one("SELECT event.event_id,event.case_no,event.event_type,event.resulting_version,event.criteria_snapshot_id,event.package_lineage_id,event.event_payload,event.source_version_tuple,package.id AS expected_package_row_id,package.package_id AS package_id,package.package_id AS expected_package_id,package.package_snapshot,package.package_version,package.source_version_tuple AS package_source_version_tuple,criteria.id AS expected_snapshot_row_id,criteria.snapshot_id AS expected_snapshot_id,criteria.source_version_tuple AS criteria_source_version_tuple FROM matching_coordination_events event JOIN matching_coordination_package_lineage package ON package.id=event.package_lineage_id JOIN matching_coordination_criteria_snapshots criteria ON criteria.id=event.criteria_snapshot_id WHERE event.case_no=%s AND event.event_type='customer_decision' ORDER BY event.id DESC LIMIT 1", (case_no,), for_update)
        if row is None:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_reply_unavailable")
        _validate_matching_event_binding(
            row, case_no, snapshot, package, allowed_event_types=("customer_decision",)
        )
        _required_positive_int(row, "package_version")
        if any(
            _matching_source_payload(row.get(key)) != current_sources
            for key in (
                "source_version_tuple",
                "package_source_version_tuple",
                "criteria_source_version_tuple",
            )
        ):
            raise ServiceBeforeReplacementSourceUnavailable(
                "replacement_matching_reply_source_version_drift"
            )
        payload = _json_object(row.get("event_payload"))
        package_payload = _json_object(row.get("package_snapshot"))
        _validate_plan_bound_payload(payload, package_payload, case_no, plan, segments, service_dates, "matching_reply")
        _validate_exact_plan_segments(payload, case_no, plan, segments, service_dates, "matching_reply")
        return row

    def _orders_service_dates(self, case_no, for_update):
        current = self._one(
            "SELECT orders.case_no,orders.service_days,version.id AS confirmed_version_id,"
            "version.service_day_count FROM orders JOIN confirmed_service_date_versions version "
            "ON version.case_no=orders.case_no AND version.is_current=1 WHERE orders.case_no=%s",
            (case_no,), for_update,
        )
        if current is None or current.get("case_no") != case_no:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_orders_service_days_unavailable")
        expected_count = _required_positive_int(current, "service_days")
        if _required_positive_int(current, "service_day_count") != expected_count:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_orders_service_days_drift")
        version_id = _required_positive_int(current, "confirmed_version_id")
        rows = self._all(
            "SELECT service_date FROM confirmed_service_date_days WHERE confirmed_version_id=%s ORDER BY ordinal",
            (version_id,), for_update,
        )
        dates = tuple(row.get("service_date") for row in rows)
        if len(dates) != expected_count or any(type(value) is not date for value in dates) or dates != tuple(sorted(set(dates))):
            raise ServiceBeforeReplacementSourceUnavailable("replacement_orders_service_days_malformed")
        return dates

    def _recipients(self, case_no, plan_id, segments, service_dates, *, require_confirmed, for_update):
        snapshot = self._one("SELECT id,case_no,plan_id,snapshot_fingerprint,confirmed_version_id,status FROM matching_schedule_snapshots WHERE case_no=%s AND plan_id=%s AND current_marker=1", (case_no, plan_id), for_update)
        if snapshot is None:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_recipient_snapshot_unavailable")
        if snapshot.get("case_no") != case_no or _required_positive_int(snapshot, "plan_id") != plan_id or snapshot.get("status") not in {"draft", "sent"}:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_recipient_snapshot_binding_drift")
        orders_version = self._one(
            "SELECT id FROM confirmed_service_date_versions WHERE case_no=%s AND is_current=1",
            (case_no,), for_update,
        )
        if orders_version is None or _required_positive_int(orders_version, "id") != _required_positive_int(snapshot, "confirmed_version_id"):
            raise ServiceBeforeReplacementSourceUnavailable("replacement_recipient_service_dates_drift")
        rows = self._all("SELECT recipient.id,recipient.audience_type,recipient.recipient_key,recipient.segment_id,recipient.recipient_line_user_id,recipient.payload_snapshot,recipient.payload_fingerprint,parent.case_no,parent.plan_id,parent.confirmed_version_id,segment.staff_id,segment.assigned_start_date,segment.assigned_end_date,orders.client_id,event.id AS confirmation_event_id,event.confirmation_value FROM matching_schedule_recipient_snapshots recipient JOIN matching_schedule_snapshots parent ON parent.id=recipient.parent_snapshot_id JOIN orders ON orders.case_no=parent.case_no LEFT JOIN caregiver_matching_plan_segments segment ON segment.id=recipient.segment_id LEFT JOIN matching_schedule_confirmation_events event ON event.id=(SELECT MAX(latest.id) FROM matching_schedule_confirmation_events latest WHERE latest.recipient_snapshot_id=recipient.id) WHERE recipient.parent_snapshot_id=%s ORDER BY recipient.id", (snapshot["id"],), for_update)
        if len(rows) != len(segments) + 1:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_recipient_cardinality_drift")
        customer_count = 0
        segment_ids = set()
        for row in rows:
            if row.get("case_no") != case_no or row.get("plan_id") != plan_id or row.get("confirmed_version_id") != snapshot.get("confirmed_version_id"):
                raise ServiceBeforeReplacementSourceUnavailable("replacement_recipient_binding_drift")
            _required_positive_int(row, "id")
            _required_text(row, "recipient_key")
            payload = _json_object(row.get("payload_snapshot"))
            audience = row.get("audience_type")
            if audience == "customer":
                customer_count += 1
                if row.get("segment_id") is not None or row.get("recipient_line_user_id") is None:
                    raise ServiceBeforeReplacementSourceUnavailable("replacement_recipient_binding_drift")
                _validate_plan_bound_payload(payload, {}, case_no, {"id": plan_id}, segments, service_dates, "recipient")
            elif audience == "caregiver":
                segment = next((item for item in segments if item.get("id") == row.get("segment_id")), None)
                if segment is None or row.get("segment_id") in segment_ids or row.get("staff_id") != segment.get("staff_id") or row.get("recipient_line_user_id") is None:
                    raise ServiceBeforeReplacementSourceUnavailable("replacement_recipient_binding_drift")
                segment_ids.add(row["segment_id"])
                _validate_plan_bound_payload(payload, {}, case_no, {"id": plan_id}, (segment,), service_dates, "recipient")
            else:
                raise ServiceBeforeReplacementSourceUnavailable("replacement_recipient_binding_drift")
        if require_confirmed and any(row.get("confirmation_value") not in {"confirmed", "manually_confirmed"} for row in rows):
            raise ServiceBeforeReplacementSourceUnavailable("replacement_recipient_confirmation_incomplete")
        if customer_count != 1 or segment_ids != {item["id"] for item in segments}:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_recipient_cardinality_drift")
        return (snapshot, *rows)

    def _waiting_lock(self, plan_id, segments, service_dates, for_update):
        lock = self._one("SELECT id,plan_id,status,is_active FROM caregiver_availability_locks WHERE plan_id=%s AND status='active' AND is_active=1", (plan_id,), for_update)
        if lock is None:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_waiting_lock_unavailable")
        days = self._all("SELECT id,lock_id,segment_id,staff_id,lock_date,active_marker FROM caregiver_availability_lock_days WHERE lock_id=%s ORDER BY lock_date,segment_id,id", (lock["id"],), for_update)
        events = self._all("SELECT id,lock_id,event_type,event_key,payload FROM caregiver_availability_lock_events WHERE lock_id=%s AND event_type='lock_acquired' ORDER BY id", (lock["id"],), for_update)
        expected = {(int(segment["id"]), service_date) for segment in segments for service_date in service_dates if segment["assigned_start_date"] <= service_date <= segment["assigned_end_date"]}
        actual = set()
        for row in days:
            if (
                _required_positive_int(row, "id") <= 0
                or _required_positive_int(row, "lock_id") != _required_positive_int(lock, "id")
                or type(row.get("lock_date")) is not date
                or row.get("active_marker") != 1
            ):
                raise ServiceBeforeReplacementSourceUnavailable("replacement_waiting_lock_partial")
            segment = next((item for item in segments if item.get("id") == row.get("segment_id")), None)
            if segment is None or row.get("staff_id") != segment.get("staff_id") or row["lock_date"] not in service_dates:
                raise ServiceBeforeReplacementSourceUnavailable("replacement_waiting_lock_binding_drift")
            key = (int(row["segment_id"]), row["lock_date"])
            if key in actual:
                raise ServiceBeforeReplacementSourceUnavailable("replacement_waiting_lock_partial")
            actual.add(key)
        if len(events) != 1 or actual != expected:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_waiting_lock_partial")
        event = events[0]
        if (
            _required_positive_int(event, "id") <= 0
            or _required_positive_int(event, "lock_id") != _required_positive_int(lock, "id")
            or event.get("event_type") != "lock_acquired"
        ):
            raise ServiceBeforeReplacementSourceUnavailable("replacement_waiting_lock_partial")
        _json_object(event.get("payload"))
        return (lock, *days, *events)

    def _commitment(self, case_no, plan_id, segments, service_dates, for_update):
        commitment = self._one("SELECT id,case_no,matching_plan_id,commitment_key,plan_snapshot_sha256 FROM precontract_service_commitments WHERE case_no=%s AND matching_plan_id=%s", (case_no, plan_id), for_update)
        if commitment is None:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_commitment_unavailable")
        days = self._all("SELECT id,commitment_id,matching_segment_id,staff_id,service_date FROM precontract_service_commitment_days WHERE commitment_id=%s ORDER BY service_date,matching_segment_id,id", (commitment["id"],), for_update)
        terminal = self._all("SELECT id,event_type,event_key FROM precontract_service_commitment_events WHERE commitment_id=%s ORDER BY id", (commitment["id"],), for_update)
        expected = {(int(segment["id"]), service_date) for segment in segments for service_date in service_dates if segment["assigned_start_date"] <= service_date <= segment["assigned_end_date"]}
        actual = set()
        if commitment.get("case_no") != case_no or _required_positive_int(commitment, "matching_plan_id") != plan_id:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_commitment_binding_drift")
        for row in days:
            if type(row.get("service_date")) is not date:
                raise ServiceBeforeReplacementSourceUnavailable("replacement_commitment_partial")
            segment = next((item for item in segments if item.get("id") == row.get("matching_segment_id")), None)
            if segment is None or row.get("staff_id") != segment.get("staff_id") or row["service_date"] not in service_dates:
                raise ServiceBeforeReplacementSourceUnavailable("replacement_commitment_binding_drift")
            key = (int(row["matching_segment_id"]), row["service_date"])
            if key in actual:
                raise ServiceBeforeReplacementSourceUnavailable("replacement_commitment_partial")
            actual.add(key)
        if terminal or not days or actual != expected:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_commitment_partial")
        return (commitment, *days)

    def _signback(self, case_no, plan_id, segments, for_update):
        sessions = self._all("SELECT id,external_signing_session_id FROM contract_external_signing_sessions WHERE case_no=%s AND matching_plan_id=%s AND session_state<>'superseded' ORDER BY id", (case_no, plan_id), for_update)
        if len(sessions) > 1:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_signback_session_ambiguous")
        if sessions:
            reports = self._all("SELECT report.id AS report_id,report.report_id AS report_identity,report.external_signing_session_id AS report_session_id,report.case_no AS report_case_no,report.matching_segment_id,report.source_kind,report.source_event_identity,report.source_payload_sha256,report.line_inbox_event_id,report.verified_line_user_id,report.manual_confirmation_method,report.manual_reason,report.manual_evidence_reference,report.manual_evidence_sha256,report.resulting_status_version,document.id AS document_id,document.case_no AS document_case_no,document.matching_plan_id AS document_plan_id,document.matching_segment_id AS document_segment_id,document.document_scope,document.document_role,document.version_number,asset.sha256,receipt.id AS receipt_id,receipt.receipt_id AS receipt_identity,receipt.external_signing_session_id AS receipt_session_id,receipt.completion_report_id AS receipt_report_id,receipt.outcome_state,receipt.result_snapshot,inbox.id AS inbox_id,inbox.event_identity AS inbox_event_identity,inbox.payload_fingerprint AS inbox_payload_fingerprint,inbox.source_user_id AS inbox_source_user_id FROM contract_external_completion_reports report JOIN contract_document_versions document ON document.id=report.document_version_id JOIN media_assets asset ON asset.id=document.media_asset_id JOIN contract_external_signing_receipts receipt ON receipt.completion_report_id=report.id LEFT JOIN line_inbox_events inbox ON inbox.id=report.line_inbox_event_id WHERE report.external_signing_session_id=%s AND report.report_scope='staff' ORDER BY report.matching_segment_id,report.id,receipt.id", (sessions[0]["id"],), for_update)
            grouped = {}
            for row in reports:
                _validate_signback_row(
                    row,
                    case_no,
                    plan_id,
                    row.get("matching_segment_id"),
                    external=True,
                    session_database_id=int(sessions[0]["id"]),
                    session_identity=str(sessions[0]["external_signing_session_id"]),
                )
                grouped.setdefault(int(row["matching_segment_id"]), []).append(row)
            expected = {int(row["id"]) for row in segments}
            if set(grouped) != expected or any(
                len(values) != 1 or values[0].get("outcome_state") != "recorded"
                for values in grouped.values()
            ):
                raise ServiceBeforeReplacementSourceUnavailable("replacement_signback_incomplete")
            return tuple(grouped[key][0] for key in sorted(grouped))
        rows = self._all("SELECT document.id AS document_id,document.case_no AS document_case_no,document.matching_plan_id AS document_plan_id,document.matching_segment_id,document.document_scope,document.document_role,document.version_number,asset.sha256,event.id AS event_id,event.case_no AS event_case_no,event.matching_plan_id AS event_plan_id,event.matching_segment_id AS event_segment_id,event.event_key,event.payload,receipt.id AS receipt_id,receipt.case_no AS receipt_case_no,receipt.document_version_id AS receipt_document_id,receipt.signing_event_id AS receipt_event_id,receipt.idempotency_key,receipt.result_snapshot FROM contract_document_versions document JOIN media_assets asset ON asset.id=document.media_asset_id JOIN contract_signing_events event ON event.document_version_id=document.id AND event.event_type='signed_received' JOIN contract_signing_command_receipts receipt ON receipt.signing_event_id=event.id WHERE document.case_no=%s AND document.matching_plan_id=%s AND document.document_scope='staff_segment' AND document.document_role='signed_return' ORDER BY document.matching_segment_id,document.version_number DESC,event.id DESC", (case_no, plan_id), for_update)
        grouped = {}
        for row in rows:
            _validate_signback_row(row, case_no, plan_id, row.get("matching_segment_id"), external=False)
            grouped.setdefault(int(row["matching_segment_id"]), []).append(row)
        latest = {}
        for segment_id, candidates in grouped.items():
            highest = max(int(row["version_number"]) for row in candidates)
            exact = tuple(row for row in candidates if int(row["version_number"]) == highest)
            if len(exact) != 1:
                raise ServiceBeforeReplacementSourceUnavailable("replacement_signback_ambiguous")
            latest[segment_id] = exact[0]
        if set(latest) != {int(row["id"]) for row in segments}:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_signback_incomplete")
        return tuple(latest[key] for key in sorted(latest))

    def _recipient_bindings(self, recipients, for_update):
        result = []
        for row in recipients[1:]:
            line_user_id = row.get("recipient_line_user_id")
            if not isinstance(line_user_id, str) or not line_user_id.strip():
                raise ServiceBeforeReplacementSourceUnavailable("replacement_recipient_binding_unavailable")
            audience = row.get("audience_type")
            if audience == "customer":
                expected_type = "customer"
                expected_reference = str(row.get("client_id"))
            elif audience == "caregiver":
                expected_type = "staff"
                expected_reference = str(row.get("staff_id"))
            else:
                raise ServiceBeforeReplacementSourceUnavailable("replacement_recipient_binding_unavailable")
            binding = self._one("SELECT line_user_id,binding_status,subject_type,subject_reference,aggregate_version FROM line_identity_bindings WHERE line_user_id=%s", (line_user_id,), for_update)
            payload = _json_object(row.get("payload_snapshot"))
            if (
                payload.get("line_user_id") != line_user_id
                or binding is None
                or binding.get("binding_status") != "bound"
                or binding.get("subject_type") != expected_type
                or str(binding.get("subject_reference")) != expected_reference
                or not expected_reference or expected_reference == "None"
            ):
                raise ServiceBeforeReplacementSourceUnavailable("replacement_recipient_binding_unavailable")
            result.append((row, binding))
        return tuple(result)

    def _candidate_reuse(self, case_no, base, *, for_update):
        try:
            projection = self._matching_facts.load_sources(case_no, for_update=for_update)
        except ServiceBeforeReplacementSourceUnavailable:
            raise
        except MatchingCoordinationFactsAdapterError as error:
            raise ServiceBeforeReplacementSourceUnavailable(
                f"replacement_matching_{error.source_kind}_{error.reason}"
            ) from error
        except Exception as error:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_sources_unavailable") from error
        try:
            package = projection.matching_package
            pool = projection.candidate_pool
            candidates = tuple(pool.candidates)
            source_items = _matching_source_items(projection.source_versions)
        except Exception as error:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_sources_malformed") from error
        if package is None or len(candidates) != 1 or not package.candidate_results:
            return None
        candidate = candidates[0]
        if len(package.candidate_results) != 1:
            return None
        result = package.candidate_results[0]
        if str(result.candidate_id) != str(candidate.id) or result.staff_id != candidate.staff_id:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_reuse_binding_drift")
        if candidate.willingness not in {"willing", "unwilling"} or result.willingness != candidate.willingness:
            return None
        round_identity = f"matching-package:{package.package_id}"
        exact_versions = {}
        for kind in ("orders_service_dates", "scheduling_availability", "candidate_pool"):
            item = source_items.get(kind)
            if item is None or isinstance(item["version"], bool) or not isinstance(item["version"], int):
                raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_reuse_source_version_unavailable")
            exact_versions[kind] = item["version"]
        if tuple(package.required_service_dates) != tuple(projection.orders_service_dates.current_dates):
            raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_reuse_service_dates_drift")
        willingness_events = tuple(
            item for item in pool.events
            if getattr(item, "event_type", None) == "willingness_changed"
            and getattr(item, "candidate_id", None) == candidate.id
        )
        if not willingness_events:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_willingness_source_unavailable")
        try:
            latest_willingness = max(willingness_events, key=lambda item: int(item.id))
            willingness_version = int(latest_willingness.id)
        except (AttributeError, TypeError, ValueError) as error:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_willingness_source_unavailable") from error
        return CandidatePoolReuseProof(
            pool_identity=f"matching-candidate-pool:{pool.pool_id}",
            round_identity=round_identity,
            coverage_version=exact_versions["orders_service_dates"],
            availability_version=exact_versions["scheduling_availability"],
            willingness_version=willingness_version,
            fingerprint=fingerprint_payload({
                "case_no": case_no,
                "package": package.canonical_payload(),
                "candidate": candidate.id,
                "source_versions": tuple(sorted(
                    (kind, value["source_id"], value["version"], value["fingerprint"])
                    for kind, value in source_items.items()
                )),
            }),
            accepted_candidate=bool(package.segments),
            case_no=case_no,
            successor_round_identity=round_identity,
            generation_version=int(base["generation_number"]),
            event_version=int(base["event_version"]),
            candidate_identity=str(candidate.id),
        )

    def _successor_round(self, case_no, *, base=None, for_update):
        row = self._one("SELECT successor.successor_round_identity,successor.replacement_generation_id,successor.scenario,event.replacement_generation_id AS event_generation_id,event.replacement_generation_identity,event.replacement_event_identity,event.resulting_generation_version,event.resulting_event_version,successor.candidate_count,successor.zero_candidate_disposition FROM scheduling_service_before_replacement_successors successor JOIN scheduling_service_before_replacement_events event ON event.id=successor.replacement_event_id WHERE successor.case_no=%s ORDER BY successor.id DESC LIMIT 1", (case_no,), for_update)
        if row is None:
            return None
        if base is not None:
            expected_generation_identity = f"replacement-generation:{case_no}:{_required_positive_int(base, 'generation_number')}"
            if (
                row.get("scenario") != "R-07"
                or _required_positive_int(row, "replacement_generation_id") != _required_positive_int(base, "generation_id")
                or _required_positive_int(row, "event_generation_id") != _required_positive_int(base, "generation_id")
                or row.get("replacement_generation_identity") != expected_generation_identity
                or _required_positive_int(row, "resulting_generation_version") != _required_positive_int(base, "generation_number")
                or _required_positive_int(row, "resulting_event_version") != _required_int(base, "event_version")
            ):
                raise ServiceBeforeReplacementSourceUnavailable("replacement_successor_current_binding_drift")
        return SuccessorRoundFact(case_no, _required_text(row, "successor_round_identity"), _required_text(row, "replacement_generation_identity"), _required_text(row, "replacement_event_identity"), _required_nonnegative_int(row, "resulting_generation_version"), _required_nonnegative_int(row, "resulting_event_version"), _required_nonnegative_int(row, "candidate_count"), row.get("zero_candidate_disposition"))

    def _r07_prior(self, case_no, base, for_update):
        row = self._one("SELECT prior_generation_identity,prior_event_identity,expected_aggregate_version,expected_generation_version,expected_event_version,replacement_generation_id,resulting_generation_version,resulting_event_version FROM scheduling_service_before_replacement_events WHERE case_no=%s ORDER BY id DESC LIMIT 1", (case_no,), for_update)
        if row is None:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_successor_prior_unavailable")
        if (
            _required_positive_int(row, "replacement_generation_id") != _required_positive_int(base, "generation_id")
            or _required_int(row, "resulting_generation_version") != _required_positive_int(base, "generation_number")
            or _required_int(row, "resulting_event_version") != _required_int(base, "event_version")
        ):
            raise ServiceBeforeReplacementSourceUnavailable("replacement_successor_prior_binding_drift")
        _required_text(row, "prior_generation_identity")
        _required_text(row, "prior_event_identity")
        return row

    def _one(self, sql, params, for_update):
        rows = self._all(sql, params, for_update)
        if len(rows) > 1:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_source_ambiguous")
        return rows[0] if rows else None

    def _all(self, sql, params, for_update):
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(sql + (" FOR UPDATE" if for_update else ""), params)
                rows = tuple(cursor.fetchall() or ())
        except ServiceBeforeReplacementSourceUnavailable:
            raise
        except Exception as error:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_source_unavailable") from error
        if any(not isinstance(row, Mapping) for row in rows):
            raise ServiceBeforeReplacementSourceUnavailable("replacement_source_malformed")
        return rows


def _request_identity(request):
    case_no = getattr(request, "case_no", None)
    scenario = getattr(request, "scenario", None)
    if not isinstance(case_no, str) or not case_no.strip():
        raise ServiceBeforeReplacementSourceUnavailable("replacement_request_identity_invalid")
    try:
        scenario = scenario if isinstance(scenario, ReplacementScenario) else ReplacementScenario(scenario)
    except ValueError as error:
        raise ServiceBeforeReplacementSourceUnavailable("replacement_scenario_invalid") from error
    return case_no.strip(), scenario


def _root(kind, case_no, prefix, rows):
    if not rows:
        raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{kind.value}_unavailable")
    digest = fingerprint_payload({"kind": kind.value, "rows": _canonical(rows)}).value
    return ReplacementRootIdentity(kind, f"{prefix}:{case_no}:{digest}", case_no)


def _canonical(value):
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return tuple(_canonical(item) for item in value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "canonical_tuple"):
        return _canonical(value.canonical_tuple)
    return str(value)


def _json_object(value, *, allow_scalar=False):
    if allow_scalar:
        return value
    try:
        result = json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ServiceBeforeReplacementSourceUnavailable("replacement_json_source_malformed") from error
    if not isinstance(result, Mapping):
        raise ServiceBeforeReplacementSourceUnavailable("replacement_json_source_malformed")
    return result


def _required_text(row: Mapping[str, Any], key: str) -> str:
    value = _value(row, key)
    if not isinstance(value, str) or not value.strip():
        raise ServiceBeforeReplacementSourceUnavailable("replacement_source_malformed")
    return value.strip()


def _required_nonnegative_int(row: Mapping[str, Any], key: str) -> int:
    value = _value(row, key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ServiceBeforeReplacementSourceUnavailable("replacement_source_malformed")
    return value


def _required_int(row: Mapping[str, Any], key: str) -> int:
    return _required_nonnegative_int(row, key)


def _required_positive_int(row: Mapping[str, Any], key: str) -> int:
    value = _required_nonnegative_int(row, key)
    if value <= 0:
        raise ServiceBeforeReplacementSourceUnavailable("replacement_source_malformed")
    return value


def _value(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(key, default)
    return getattr(row, key, default)


def _matching_source_payload(values: Any, *, require_complete: bool = True) -> tuple[dict[str, Any], ...]:
    if isinstance(values, (str, bytes, bytearray)):
        try:
            values = json.loads(values)
        except (TypeError, ValueError) as error:
            raise TypeError("matching source tuple is malformed") from error
    if not isinstance(values, (tuple, list)):
        raise TypeError("matching source tuple is malformed")
    result = []
    seen = set()
    for item in values:
        source_kind = _value(item, "source_kind")
        source_id = _value(item, "source_id")
        version = _value(item, "version")
        fingerprint = _value(item, "fingerprint")
        fingerprint = getattr(fingerprint, "value", fingerprint)
        if not isinstance(source_kind, str) or source_kind in seen or not isinstance(source_id, str):
            raise TypeError("matching source version is malformed")
        if not isinstance(version, (int, str)) or isinstance(version, bool) or not isinstance(fingerprint, str):
            raise TypeError("matching source version is malformed")
        seen.add(source_kind)
        result.append({"source_kind": source_kind, "source_id": source_id, "version": version, "fingerprint": fingerprint})
    if require_complete and len(result) != 13:
        raise TypeError("matching source tuple is incomplete")
    return tuple(result)


def _matching_source_items(values: Any) -> dict[str, dict[str, Any]]:
    return {item["source_kind"]: item for item in _matching_source_payload(values)}


def _validate_matching_event_binding(
    row: Mapping[str, Any],
    case_no: str,
    snapshot: Any,
    package: Any,
    *,
    allowed_event_types: tuple[str, ...] = ("package_proposed", "customer_decision"),
) -> None:
    if row.get("case_no") != case_no or row.get("event_type") not in allowed_event_types:
        raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_reply_binding_drift")
    if str(row.get("criteria_snapshot_id")) != str(
        row.get("expected_snapshot_row_id", row.get("criteria_snapshot_id"))
    ):
        raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_reply_binding_drift")
    if str(row.get("package_lineage_id")) != str(
        row.get("expected_package_row_id", row.get("package_lineage_id"))
    ):
        raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_reply_binding_drift")
    if str(row.get("expected_snapshot_id")) != str(_value(snapshot, "snapshot_id")):
        raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_reply_binding_drift")
    if str(row.get("expected_package_id")) != str(_value(package, "package_id")):
        raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_reply_binding_drift")
    if not isinstance(row.get("event_id"), str) or not row["event_id"].strip():
        raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_reply_malformed")
    _required_positive_int(row, "resulting_version")
    payload = _json_object(row.get("event_payload"))
    package_payload = _json_object(row.get("package_snapshot"))
    expected_package_id = _value(package, "package_id")
    for value in (payload.get("package_id"), package_payload.get("package_id")):
        if value is not None and str(value) != str(expected_package_id):
            raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_reply_binding_drift")
    for value in (payload.get("criteria_snapshot_id"), package_payload.get("criteria_snapshot_id")):
        if value is not None and str(value) != str(_value(snapshot, "snapshot_id")):
            raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_reply_binding_drift")


def _validate_plan_bound_payload(
    payload: Mapping[str, Any],
    package_payload: Mapping[str, Any],
    case_no: str,
    plan: Mapping[str, Any],
    segments: tuple[Mapping[str, Any], ...],
    service_dates: tuple[date, ...],
    source_name: str,
) -> None:
    if not isinstance(payload, Mapping) or not isinstance(package_payload, Mapping):
        raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_malformed")
    for value in (payload.get("case_no"), package_payload.get("case_no")):
        if value is not None and value != case_no:
            raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_binding_drift")
    expected_plan = plan.get("id")
    for value in (payload.get("plan_id"), payload.get("matching_plan_id"), package_payload.get("plan_id"), package_payload.get("matching_plan_id")):
        if value is not None and value != expected_plan:
            raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_binding_drift")
    expected_staff = {item["staff_id"] for item in segments}
    expected_segments = {item["id"] for item in segments}
    values = payload.get("segments", package_payload.get("segments"))
    if values is not None:
        if not isinstance(values, (tuple, list)):
            raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_malformed")
        seen = set()
        expected_by_order = {item["segment_order"]: item for item in segments}
        for value in values:
            if not isinstance(value, Mapping):
                raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_malformed")
            staff_id = value.get("staff_id")
            segment_id = value.get("segment_id", value.get("id"))
            sequence = value.get("sequence", value.get("segment_order"))
            expected_segment = expected_by_order.get(sequence) if sequence is not None else None
            if expected_segment is not None and staff_id != expected_segment["staff_id"]:
                raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_binding_drift")
            if sequence is not None and expected_segment is None:
                raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_segment_drift")
            if staff_id is not None and staff_id not in expected_staff:
                raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_binding_drift")
            if segment_id is not None:
                if segment_id not in expected_segments or segment_id in seen:
                    raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_binding_drift")
                seen.add(segment_id)
            dates = value.get("service_dates")
            if dates is not None:
                parsed = tuple(item if type(item) is date else date.fromisoformat(str(item)) for item in dates)
                if parsed != tuple(sorted(set(parsed))) or any(item not in service_dates for item in parsed):
                    raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_date_drift")
                if expected_segment is not None:
                    expected_dates = tuple(
                        item for item in service_dates
                        if expected_segment["assigned_start_date"] <= item <= expected_segment["assigned_end_date"]
                    )
                    if parsed != expected_dates:
                        raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_date_drift")
        if seen and seen != expected_segments:
            raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_segment_drift")


def _validate_exact_plan_segments(
    payload: Mapping[str, Any],
    case_no: str,
    plan: Mapping[str, Any],
    segments: tuple[Mapping[str, Any], ...],
    service_dates: tuple[date, ...],
    source_name: str,
) -> None:
    required = ("case_no", "plan_id", "segments")
    if any(key not in payload for key in required) or payload.get("case_no") != case_no:
        raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_malformed")
    if payload.get("plan_id") != plan.get("id"):
        raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_binding_drift")
    values = payload["segments"]
    if not isinstance(values, (tuple, list)) or len(values) != len(segments):
        raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_segment_drift")
    expected = {item["segment_order"]: item for item in segments}
    seen = set()
    for value in values:
        if not isinstance(value, Mapping) or not {"sequence", "staff_id", "service_dates"}.issubset(value):
            raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_malformed")
        sequence = value["sequence"]
        current = expected.get(sequence)
        if current is None or sequence in seen or value["staff_id"] != current["staff_id"]:
            raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_binding_drift")
        dates = value["service_dates"]
        if not isinstance(dates, (tuple, list)):
            raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_malformed")
        try:
            parsed = tuple(item if type(item) is date else date.fromisoformat(str(item)) for item in dates)
        except (TypeError, ValueError) as error:
            raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_malformed") from error
        expected_dates = tuple(
            item for item in service_dates
            if current["assigned_start_date"] <= item <= current["assigned_end_date"]
        )
        if parsed != expected_dates:
            raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_date_drift")
        seen.add(sequence)
    if seen != set(expected):
        raise ServiceBeforeReplacementSourceUnavailable(f"replacement_{source_name}_segment_drift")


def _validate_signback_row(
    row: Mapping[str, Any],
    case_no: str,
    plan_id: int,
    segment_id: Any,
    *,
    external: bool,
    session_database_id: int | None = None,
    session_identity: str | None = None,
) -> None:
    try:
        valid_segment = isinstance(segment_id, int) and not isinstance(segment_id, bool) and segment_id > 0
    except TypeError:
        valid_segment = False
    if (
        _required_positive_int(row, "document_id") <= 0
        or row.get("document_case_no") != case_no
        or _required_positive_int(row, "document_plan_id") != plan_id
        or not valid_segment
        or _required_positive_int(row, "document_segment_id") != segment_id
        or row.get("document_scope") != "staff_segment"
        or row.get("document_role") != "signed_return"
        or _required_positive_int(row, "version_number") <= 0
        or not _digest(row.get("sha256"))
        or not _required_text(row, "source_event_identity" if external else "event_key")
    ):
        raise ServiceBeforeReplacementSourceUnavailable("replacement_signback_lineage_invalid")
    if external:
        snapshot = _json_object(row.get("result_snapshot"))
        if (
            not _digest(row.get("source_payload_sha256"))
            or not _required_text(row, "report_identity")
            or not _required_positive_int(row, "report_id")
            or not _required_positive_int(row, "receipt_id")
            or row.get("report_case_no") != case_no
            or row.get("report_session_id") != session_database_id
            or row.get("receipt_session_id") != session_database_id
            or row.get("receipt_report_id") != row.get("report_id")
            or not _required_text(row, "receipt_identity")
            or row.get("outcome_state") != "recorded"
            or snapshot.get("session_id") != session_identity
            or snapshot.get("scope") != "staff"
            or snapshot.get("matching_segment_id") != segment_id
            or snapshot.get("report_id") != row.get("report_identity")
            or snapshot.get("resulting_status_version")
            != row.get("resulting_status_version")
            or snapshot.get("command_type")
            != "record_external_staff_signing_report"
        ):
            raise ServiceBeforeReplacementSourceUnavailable("replacement_signback_lineage_invalid")
        source_kind = row.get("source_kind")
        if source_kind == "verified_line":
            if (
                row.get("line_inbox_event_id") != row.get("inbox_id")
                or row.get("inbox_event_identity") != row.get("source_event_identity")
                or row.get("inbox_payload_fingerprint")
                != row.get("source_payload_sha256")
                or row.get("inbox_source_user_id") != row.get("verified_line_user_id")
            ):
                raise ServiceBeforeReplacementSourceUnavailable(
                    "replacement_signback_lineage_invalid"
                )
        elif source_kind == "manual_attested":
            if (
                row.get("line_inbox_event_id") is not None
                or row.get("verified_line_user_id") is not None
                or not _required_text(row, "manual_confirmation_method")
                or not _required_text(row, "manual_reason")
                or not _required_text(row, "manual_evidence_reference")
                or not _digest(row.get("manual_evidence_sha256"))
            ):
                raise ServiceBeforeReplacementSourceUnavailable(
                    "replacement_signback_lineage_invalid"
                )
        else:
            raise ServiceBeforeReplacementSourceUnavailable(
                "replacement_signback_lineage_invalid"
            )
    elif (
        not _required_positive_int(row, "event_id")
        or row.get("event_case_no") != case_no
        or _required_positive_int(row, "event_plan_id") != plan_id
        or row.get("event_segment_id") != segment_id
        or row.get("receipt_document_id") != row.get("document_id")
        or row.get("receipt_event_id") != row.get("event_id")
        or _json_object(row.get("payload")) is None
        or _json_object(row.get("result_snapshot")) is None
    ):
        raise ServiceBeforeReplacementSourceUnavailable("replacement_signback_lineage_invalid")


def _validate_segment_coverage(
    segments: tuple[Mapping[str, Any], ...], service_dates: tuple[date, ...]
) -> None:
    if not service_dates:
        raise ServiceBeforeReplacementSourceUnavailable("replacement_orders_service_days_unavailable")
    covered = []
    for service_date in service_dates:
        owners = [segment for segment in segments if segment["assigned_start_date"] <= service_date <= segment["assigned_end_date"]]
        if len(owners) != 1:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_segment_date_drift")
        covered.append(owners[0]["id"])
    if set(covered) != {segment["id"] for segment in segments}:
        raise ServiceBeforeReplacementSourceUnavailable("replacement_matching_segment_date_drift")


def _digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _latest_per(events, key, event_type, expected_ids):
    result = {}
    for event in events:
        if (
            event.get("event_type") == event_type
            and event.get(key) is not None
            and int(event[key]) in expected_ids
        ):
            result[int(event[key])] = event
    if tuple(sorted(result)) != tuple(sorted(expected_ids)):
        raise ServiceBeforeReplacementSourceUnavailable("replacement_willingness_set_incomplete")
    for event in result.values():
        payload = _json_object(event.get("payload"))
        if payload.get("willingness") not in {"willing", "unwilling"}:
            raise ServiceBeforeReplacementSourceUnavailable("replacement_willingness_nonterminal")
    return tuple(result[item] for item in sorted(result))


__all__ = [
    "MySqlServiceBeforeReplacementLoader",
    "ServiceBeforeReplacementSourceUnavailable",
]
