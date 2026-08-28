"""
File: historical_baseline_matching_owner_adapter.py
Description: 以借用的 MySQL 連線讀取 Matching HCAT v2 根事實。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from domains.orders.historical_operational_baseline import (
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    HistoricalBaselineOwnerObservation,
    HistoricalBaselineOwnerRootDescriptor,
    HistoricalOrderIdentity,
)
from subsystems.orders.historical_baseline_owner_vector import (
    HistoricalBaselineOwnerObservationReadback,
)


_MAX_BIGINT = 9_223_372_036_854_775_807
_DESCRIPTORS = {
    (item.step, item.root_identity_kind): item
    for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    if item.owner_domain == "matching"
}
_POOL_KINDS = {"candidate_pool", "candidate_contact", "willingness_binding"}
_SELECTION_KINDS = {"selected_staff", "customer_decision"}


class MySqlHistoricalBaselineMatchingOwnerAdapter:
    """Read Matching observations without taking ownership of transaction state."""

    owner_domain = "matching"

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def read_owner_observations(
        self,
        identity: HistoricalOrderIdentity,
        descriptor: HistoricalBaselineOwnerRootDescriptor,
        *,
        for_update: bool = False,
    ) -> HistoricalBaselineOwnerObservationReadback:
        if not isinstance(identity, HistoricalOrderIdentity):
            raise TypeError("historical baseline Matching identity is invalid")
        if not isinstance(descriptor, HistoricalBaselineOwnerRootDescriptor):
            raise TypeError("historical baseline Matching descriptor is invalid")
        if not isinstance(for_update, bool):
            raise TypeError("historical baseline Matching read mode is invalid")
        expected = _DESCRIPTORS.get((descriptor.step, descriptor.root_identity_kind))
        if expected is None or descriptor.canonical_tuple != expected.canonical_tuple:
            raise ValueError("historical_baseline_matching_descriptor_unsupported")

        try:
            if descriptor.root_identity_kind in _POOL_KINDS:
                observations = self._read_pool_descriptor(identity, descriptor, for_update)
            elif descriptor.root_identity_kind in _SELECTION_KINDS:
                observations = self._read_selection_descriptor(identity, descriptor, for_update)
            else:
                observations = self._read_caregiver_binding(identity, descriptor, for_update)
        except Exception:
            observations = (_unavailable(descriptor, identity.case_no, _read_failed(descriptor)),)
        return HistoricalBaselineOwnerObservationReadback(identity, tuple(observations))

    def _read_pool_descriptor(self, identity, descriptor, for_update):
        with self._connection.cursor() as cursor:
            pool_rows = _rows(cursor, _POOL_SQL, identity.case_no, for_update)
            if len(pool_rows) != 1:
                return (_unavailable(descriptor, identity.case_no, f"matching_step_{descriptor.step}_pool_unavailable"),)
            pool = pool_rows[0]
            pool_id = _positive(pool.get("id"))
            if pool_id is None or pool.get("case_no") != identity.case_no:
                return (_unavailable(descriptor, identity.case_no, f"matching_step_{descriptor.step}_cross_case"),)
            entries = _rows(cursor, _ENTRIES_SQL, pool_id, for_update)
            events = _rows(cursor, _POOL_EVENTS_SQL, pool_id, for_update)
        parsed = _parse_pool(pool, entries, events, identity.case_no)
        if parsed[0] is not None:
            return (_unavailable(descriptor, identity.case_no, parsed[0]),)
        entry_rows, event_rows = parsed[1], parsed[2]
        if not entry_rows:
            return (_unavailable(descriptor, identity.case_no, f"matching_step_{descriptor.step}_entries_missing"),)
        if descriptor.root_identity_kind == "candidate_pool":
            return tuple(_candidate_observation(descriptor, identity.case_no, row, event_rows) for row in entry_rows)
        if descriptor.root_identity_kind == "candidate_contact":
            result = []
            for entry in entry_rows:
                for info_kind in ("info_1_sent", "info_2_sent"):
                    exact = _latest_candidate_event(event_rows, entry["id"], info_kind)
                    if exact is None:
                        result.append(_unavailable(descriptor, identity.case_no, f"matching_candidate_contact_{entry['id']}_{info_kind}_missing"))
                    elif exact[0] is not None:
                        result.append(_unavailable(descriptor, identity.case_no, exact[0]))
                    else:
                        event = exact[1]
                        result.append(_available(descriptor, identity.case_no, f"matching.candidate_contact:{identity.case_no}:candidate:{entry['id']}:info:{info_kind[5]}", str(event["event_key"]), int(event["id"]), _delivery_terminal(event["payload"])))
            return tuple(result)
        # The v2 catalog has one willingness binding, not one scalar per
        # candidate.  Prefer the unique selected entry; otherwise only a
        # single-candidate pool can prove this descriptor.
        selected = [entry for entry in entry_rows if entry.get("status") == "selected"]
        if len(selected) > 1 or (not selected and len(entry_rows) != 1):
            return (_unavailable(descriptor, identity.case_no, "matching_willingness_binding_cardinality_unavailable"),)
        willingness_entries = selected or entry_rows
        result = []
        for entry in willingness_entries:
            exact = _latest_candidate_event(event_rows, entry["id"], "willingness_changed")
            if exact is None:
                result.append(_unavailable(descriptor, identity.case_no, f"matching_willingness_{entry['id']}_missing"))
            elif exact[0] is not None:
                result.append(_unavailable(descriptor, identity.case_no, exact[0]))
            else:
                event = exact[1]
                payload = event["payload"]
                if payload.get("willingness") not in {"willing", "unwilling"}:
                    result.append(_unavailable(descriptor, identity.case_no, f"matching_willingness_{entry['id']}_malformed"))
                    continue
                willing = payload["willingness"] == "willing"
                result.append(_available(descriptor, identity.case_no, f"matching.willingness_binding:{identity.case_no}:candidate:{entry['id']}", str(event["event_key"]), int(event["id"]), willing))
        return tuple(result)

    def _read_selection_descriptor(self, identity, descriptor, for_update):
        with self._connection.cursor() as cursor:
            criteria = _rows(cursor, _CRITERIA_SQL, identity.case_no, for_update)
            packages = _rows(cursor, _PACKAGE_SQL, identity.case_no, for_update)
            events = _rows(cursor, _MATCHING_EVENTS_SQL, identity.case_no, for_update)
        result = _selection_facts(identity.case_no, criteria, packages, events)
        if result[0] is not None:
            return (_unavailable(descriptor, identity.case_no, result[0]),)
        facts = result[1]
        event = facts["event"]
        candidate_id = facts["candidate_id"]
        if descriptor.root_identity_kind == "selected_staff":
            root = f"matching.selected_staff:{identity.case_no}:candidate:{candidate_id}"
        else:
            root = f"matching.customer_decision:{identity.case_no}:{event['event_id']}"
        return (_available(descriptor, identity.case_no, root, str(event["event_id"]), int(event["resulting_version"]), True),)

    def _read_caregiver_binding(self, identity, descriptor, for_update):
        with self._connection.cursor() as cursor:
            plans = _rows(cursor, _ACCEPTED_PLAN_SQL, identity.case_no, for_update)
            if len(plans) != 1:
                return (_unavailable(descriptor, identity.case_no, "matching_caregiver_binding_plan_ambiguous" if plans else "matching_caregiver_binding_plan_missing"),)
            plan = plans[0]
            plan_id = _positive(plan.get("id"))
            if plan_id is None or plan.get("case_no") != identity.case_no or plan.get("status") != "accepted" or plan.get("is_active") != 1:
                return (_unavailable(descriptor, identity.case_no, "matching_caregiver_binding_plan_invalid"),)
            segments = _rows(cursor, _PLAN_SEGMENTS_SQL, plan_id, for_update)
            packages = _rows(cursor, _PACKAGE_SQL, identity.case_no, for_update)
        if not 1 <= len(segments) <= 4:
            return (_unavailable(descriptor, identity.case_no, "matching_caregiver_binding_segments_incomplete"),)
        segment_error = _validate_segments(segments, plan_id, identity.case_no)
        if segment_error:
            return (_unavailable(descriptor, identity.case_no, segment_error),)
        package_result = _current_package(identity.case_no, packages)
        if package_result[0] is not None:
            return (_unavailable(descriptor, identity.case_no, f"matching_caregiver_binding_{package_result[0]}"),)
        package = package_result[1]
        snapshot_segments = _package_segments(package.get("package_snapshot"))
        if snapshot_segments is None or not _segments_equal(segments, snapshot_segments):
            return (_unavailable(descriptor, identity.case_no, "matching_caregiver_binding_package_segment_drift"),)
        return (_available(descriptor, identity.case_no, f"matching.caregiver_binding:{identity.case_no}:plan:{plan_id}:v{plan['version']}", f"matching.package:{package['package_id']}", int(package["package_version"]), True),)


_POOL_SQL = "SELECT id,case_no FROM caregiver_candidate_contact_pools WHERE case_no=%s"
_ENTRIES_SQL = "SELECT id,pool_id,staff_id,status,active_marker FROM caregiver_candidate_contact_entries WHERE pool_id=%s ORDER BY id"
_POOL_EVENTS_SQL = "SELECT id,pool_id,candidate_id,event_type,event_key,payload,occurred_at FROM caregiver_candidate_contact_events WHERE pool_id=%s ORDER BY id"
_CRITERIA_SQL = "SELECT id,snapshot_id,case_no,criteria_version,criteria_snapshot,source_version_tuple,criteria_digest FROM matching_coordination_criteria_snapshots WHERE case_no=%s ORDER BY criteria_version DESC LIMIT 1"
_PACKAGE_SQL = "SELECT id,package_id,case_no,criteria_snapshot_id,package_version,package_state,package_snapshot,source_version_tuple,package_digest FROM matching_coordination_package_lineage WHERE case_no=%s ORDER BY package_version DESC LIMIT 1"
_MATCHING_EVENTS_SQL = "SELECT id,event_id,case_no,criteria_snapshot_id,package_lineage_id,event_type,expected_version,resulting_version,event_payload,source_version_tuple,event_digest FROM matching_coordination_events WHERE case_no=%s ORDER BY id"
_ACCEPTED_PLAN_SQL = "SELECT id,case_no,version,status,is_active,start_date,end_date FROM caregiver_matching_plans WHERE case_no=%s AND status='accepted' AND is_active=1 ORDER BY version DESC"
_PLAN_SEGMENTS_SQL = "SELECT s.id,s.plan_id,p.case_no AS plan_case_no,s.segment_order,s.staff_id,s.assigned_start_date,s.assigned_end_date FROM caregiver_matching_plan_segments s JOIN caregiver_matching_plans p ON p.id=s.plan_id WHERE s.plan_id=%s ORDER BY s.segment_order,s.id"


def _rows(cursor: Any, statement: str, parameter: Any, for_update: bool) -> tuple[Mapping[str, Any], ...]:
    cursor.execute(statement + (" FOR UPDATE" if for_update else ""), (parameter,))
    values = tuple(cursor.fetchall() or ())
    if any(not isinstance(row, Mapping) for row in values):
        raise TypeError("historical baseline Matching row is invalid")
    return values


def _json(value: Any) -> tuple[dict[str, Any] | None, str | None]:
    try:
        decoded = json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, "matching_event_payload_malformed"
    return (dict(decoded), None) if isinstance(decoded, Mapping) else (None, "matching_event_payload_malformed")


def _parse_pool(pool, entries, events, case_no):
    ids = []
    normalized_entries = []
    for row in entries:
        entry_id, pool_id, staff_id = _positive(row.get("id")), _positive(row.get("pool_id")), _positive(row.get("staff_id"))
        if entry_id is None or pool_id != pool.get("id") or staff_id is None or row.get("active_marker") not in (None, 1):
            return "matching_candidate_pool_entry_invalid", (), ()
        if entry_id in ids:
            return "matching_candidate_pool_entry_ambiguous", (), ()
        ids.append(entry_id)
        normalized_entries.append(row)
    normalized_events = []
    for row in events:
        if (_positive(row.get("id")) is None or row.get("pool_id") != pool.get("id")
                or not isinstance(row.get("event_key"), str) or not row["event_key"].strip()):
            return "matching_candidate_pool_event_cross_pool", (), ()
        payload, error = _json(row.get("payload"))
        if error:
            return error, (), ()
        event = dict(row)
        event["payload"] = payload
        normalized_events.append(event)
    for event in normalized_events:
        candidate_id = event.get("candidate_id")
        if candidate_id is not None and (_positive(candidate_id) is None or candidate_id not in ids):
            return "matching_candidate_pool_event_cross_pool", (), ()
        if event.get("event_type") not in {"candidates_added", "info_1_sent", "info_2_sent", "willingness_changed", "candidate_selected", "candidate_withdrawn"}:
            return "matching_candidate_pool_event_malformed", (), ()
        if event.get("event_type") == "candidates_added":
            candidate_ids = event["payload"].get("candidate_ids")
            if not isinstance(candidate_ids, list) or any(_positive(item) is None for item in candidate_ids) or len(set(candidate_ids)) != len(candidate_ids):
                return "matching_candidate_pool_candidates_added_malformed", (), ()
            if event.get("candidate_id") is not None:
                return "matching_candidate_pool_candidates_added_malformed", (), ()
    entry_ids = set(ids)
    for event in normalized_events:
        if event.get("event_type") == "candidates_added" and set(event["payload"]["candidate_ids"]) != entry_ids:
            return "matching_candidate_pool_candidates_added_drift", (), ()
    return None, tuple(sorted(normalized_entries, key=lambda row: row["id"])), tuple(sorted(normalized_events, key=lambda row: row["id"]))


def _candidate_observation(descriptor, case_no, entry, events):
    entry_id = entry["id"]
    exact = [event for event in events if event.get("event_type") == "candidates_added" and entry_id in event["payload"].get("candidate_ids", [])]
    if not exact:
        return _unavailable(descriptor, case_no, f"matching_candidate_pool_{entry_id}_source_missing")
    source = exact[0]
    status = entry.get("status")
    if status in {"selected", "withdrawn"}:
        expected_type = "candidate_selected" if status == "selected" else "candidate_withdrawn"
        successors = [event for event in events if event.get("event_type") == expected_type and event.get("candidate_id") == entry_id and event.get("id") > source["id"] and event["payload"].get("candidate_id") == entry_id]
        if len(successors) != 1:
            return _unavailable(descriptor, case_no, f"matching_candidate_pool_{entry_id}_status_transition_invalid")
    return _available(descriptor, case_no, f"matching.candidate_pool:{case_no}:candidate:{entry_id}:staff:{entry['staff_id']}", str(source["event_key"]), int(source["id"]), True)


def _latest_candidate_event(events, candidate_id, event_type):
    matches = [event for event in events if event.get("candidate_id") == candidate_id and event.get("event_type") == event_type]
    if not matches:
        return None
    latest = max(matches, key=lambda event: event.get("id", -1))
    if not _positive(latest.get("id")) or not isinstance(latest.get("event_key"), str) or not latest["event_key"].strip():
        return "matching_candidate_event_identity_invalid", None
    return None, latest


def _selection_facts(case_no, criteria_rows, package_rows, event_rows, *, require_candidate=True):
    if criteria_rows:
        if len(criteria_rows) != 1 or criteria_rows[0].get("case_no") != case_no or _positive(criteria_rows[0].get("id")) is None:
            return "criteria_cross_case_or_ambiguous", None
        criteria = criteria_rows[0]
        criteria_payload, criteria_error = _json(criteria.get("criteria_snapshot"))
        criteria_sources = _typed_sources(criteria.get("source_version_tuple"))
        if criteria_error or criteria_payload is None or criteria_sources is None or not criteria_sources:
            return "criteria_snapshot_malformed", None
        if criteria.get("criteria_digest") is not None and criteria_payload.get("fingerprint") not in (None, criteria.get("criteria_digest")):
            return "criteria_snapshot_digest_drift", None
    else:
        criteria = None
    if len(package_rows) != 1:
        return "package_missing_or_ambiguous", None
    package = package_rows[0]
    if package.get("case_no") != case_no or package.get("package_state") != "accepted":
        return "package_not_current_accepted", None
    package_payload, error = _json(package.get("package_snapshot"))
    if error or package_payload is None:
        return "package_snapshot_malformed", None
    if package_payload.get("package_id") not in (None, package.get("package_id")) or package_payload.get("version") not in (None, package.get("package_version")):
        return "package_identity_drift", None
    package_sources = _typed_sources(package_payload.get("source_versions"))
    stored_package_sources = _typed_sources(package.get("source_version_tuple"))
    if package_sources is None or not package_sources or stored_package_sources is None or not stored_package_sources or package_sources != stored_package_sources:
        return "package_source_malformed_or_drift", None
    if package.get("package_digest") is not None and package_payload.get("fingerprint") not in (None, package.get("package_digest")):
        return "package_digest_drift", None
    if criteria is not None and (package.get("criteria_snapshot_id") != criteria.get("id") or package_payload.get("criteria_snapshot_id") not in (None, criteria.get("snapshot_id"))):
        return "criteria_package_drift", None
    if criteria is not None and criteria_sources != package_sources:
        return "criteria_package_source_drift", None
    package = dict(package)
    package["package_snapshot"] = package_payload
    candidates = package_payload.get("candidate_results")
    if not isinstance(candidates, list):
        return "package_candidates_malformed", None
    accepted = []
    for event in event_rows:
        if event.get("case_no") != case_no:
            return "matching_event_cross_case", None
        payload, error = _json(event.get("event_payload"))
        if error:
            return error, None
        event = dict(event)
        event["event_payload"] = payload
        if event.get("event_type") == "customer_decision" and payload.get("result_state") in {"accepted", "rejected", "disagree"}:
            if event.get("package_lineage_id") == package.get("id") and event.get("criteria_snapshot_id") == (criteria.get("id") if criteria else package.get("criteria_snapshot_id")):
                event_sources = _typed_sources(event.get("source_version_tuple"))
                if event_sources is None or not event_sources or event_sources != package_sources:
                    return "accepted_customer_source_drift", None
                event["_candidate_id"] = payload.get("cross_domain_request", {}).get("candidate_id") if isinstance(payload.get("cross_domain_request"), Mapping) else None
                if payload.get("result_state") == "accepted":
                    accepted.append(event)
                else:
                    accepted.append({**event, "_rejected": True})
    if not accepted:
        return "accepted_customer_decision_missing_or_ambiguous", None
    event = max(accepted, key=lambda item: item.get("id", -1))
    if event.get("_rejected"):
        return "accepted_customer_decision_stale", None
    candidate_id = event.get("_candidate_id")
    if require_candidate and not any(item.get("candidate_id") == candidate_id for item in candidates if isinstance(item, Mapping)):
        return "accepted_customer_candidate_missing", None
    if not _positive(event.get("id")) or not isinstance(event.get("event_id"), str) or not event["event_id"].strip() or not _nonnegative(event.get("resulting_version")):
        return "accepted_customer_event_invalid", None
    if event.get("expected_version") != event.get("resulting_version") - 1 or event.get("resulting_version") != package.get("package_version"):
        return "accepted_customer_event_version_drift", None
    return None, {"package": package, "event": event, "candidate_id": candidate_id}


def _current_package(case_no, package_rows):
    """Validate the unique current accepted M3 package for Step 8."""

    if len(package_rows) != 1:
        return "package_missing_or_ambiguous", None
    package = package_rows[0]
    if package.get("case_no") != case_no or package.get("package_state") != "accepted":
        return "package_not_current_accepted", None
    payload, error = _json(package.get("package_snapshot"))
    if error or payload is None:
        return "package_snapshot_malformed", None
    version = _nonnegative(package.get("package_version"))
    package_id = package.get("package_id")
    if not isinstance(package_id, str) or not package_id.strip() or version is None:
        return "package_invalid", None
    if payload.get("package_id") not in (None, package_id) or payload.get("version") not in (None, version):
        return "package_identity_drift", None
    package_sources = _typed_sources(payload.get("source_versions"))
    stored_sources = _typed_sources(package.get("source_version_tuple"))
    if package_sources is None or not package_sources or stored_sources is None or not stored_sources or package_sources != stored_sources:
        return "package_source_malformed_or_drift", None
    if package.get("package_digest") is not None and payload.get("fingerprint") not in (None, package.get("package_digest")):
        return "package_digest_drift", None
    normalized = dict(package)
    normalized["package_snapshot"] = payload
    return None, normalized


def _package_segments(value):
    if not isinstance(value, Mapping) or not isinstance(value.get("segments"), list):
        return None
    result = []
    for item in value["segments"]:
        if not isinstance(item, Mapping) or _positive(item.get("staff_id")) is None or not _positive(item.get("sequence")):
            return None
        dates = item.get("service_dates")
        if not isinstance(dates, list) or not dates:
            return None
        result.append((item["sequence"], item["staff_id"], tuple(str(day) for day in dates)))
    return tuple(sorted(result)) if 1 <= len(result) <= 4 else None


def _validate_segments(rows, plan_id, case_no):
    orders = sorted((row.get("segment_order") for row in rows))
    if orders != list(range(1, len(rows) + 1)):
        return "matching_caregiver_binding_segment_order_invalid"
    seen = set()
    for row in rows:
        if row.get("plan_id") != plan_id or row.get("plan_case_no", row.get("case_no")) != case_no or _positive(row.get("id")) is None or _positive(row.get("staff_id")) is None:
            return "matching_caregiver_binding_segment_invalid"
        start, end = row.get("assigned_start_date"), row.get("assigned_end_date")
        if start is None or end is None or start > end or row["staff_id"] in seen:
            return "matching_caregiver_binding_segment_invalid"
        seen.add(row["staff_id"])
    return None


def _segments_equal(rows, package_segments):
    actual = tuple(sorted((row["segment_order"], row["staff_id"], (str(row["assigned_start_date"]), str(row["assigned_end_date"]))) for row in rows))
    expected = tuple(sorted((sequence, staff_id, (dates[0], dates[-1])) for sequence, staff_id, dates in package_segments))
    return actual == expected


def _delivery_terminal(payload):
    return payload.get("delivery_status") in {"sent", "manually_confirmed"}


def _positive(value):
    return value if type(value) is int and 0 < value <= _MAX_BIGINT else None


def _nonnegative(value):
    return value if type(value) is int and 0 <= value <= _MAX_BIGINT else None


def _json_list(value):
    try:
        decoded = json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return list(decoded) if isinstance(decoded, list) else None


def _typed_sources(value):
    values = _json_list(value)
    if values is None or not values:
        return None
    required = {"source_kind", "source_id", "version", "fingerprint"}
    normalized = []
    for item in values:
        if not isinstance(item, Mapping) or set(item) != required:
            return None
        if not all(isinstance(item[key], str) and item[key].strip() for key in ("source_kind", "source_id")):
            return None
        if _nonnegative(item["version"]) is None or not isinstance(item["fingerprint"], str) or len(item["fingerprint"]) != 64 or item["fingerprint"] != item["fingerprint"].lower() or any(char not in "0123456789abcdef" for char in item["fingerprint"]):
            return None
        normalized.append(dict(item))
    return normalized


def _available(descriptor, case_no, root_identity, source_event_identity, source_version, terminal):
    return HistoricalBaselineOwnerObservation(descriptor, root_identity, source_event_identity, source_version, terminal, None, case_no)


def _unavailable(descriptor, case_no, code):
    return HistoricalBaselineOwnerObservation.unavailable(descriptor, code=code, case_no=case_no)


def _read_failed(descriptor):
    return f"matching_step_{descriptor.step}_{descriptor.root_identity_kind}_read_failed"


MySqlHistoricalBaselineOwnerMatchingAdapter = MySqlHistoricalBaselineMatchingOwnerAdapter
HistoricalBaselineMatchingOwnerAdapter = MySqlHistoricalBaselineMatchingOwnerAdapter

__all__ = [
    "HistoricalBaselineMatchingOwnerAdapter",
    "MySqlHistoricalBaselineMatchingOwnerAdapter",
    "MySqlHistoricalBaselineOwnerMatchingAdapter",
]
