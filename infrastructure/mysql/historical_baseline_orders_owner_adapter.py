"""
File: historical_baseline_orders_owner_adapter.py
Description: 以借用的 MySQL 連線讀取 Orders 歷史基準的精確根事實。
"""

from __future__ import annotations

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
from shared_kernel.validation import require_canonical_text


_CASE_NUMBER_MAXIMUM_LENGTH = 50
_SIGNED_BIGINT_MAXIMUM = 9_223_372_036_854_775_807
_COMPLETED_STATUS = "訂單完成"
_ORDER_IDENTITY_PREFIX = "order:"
_HISTORICAL_ADOPTION_TRIGGER = "historical_order_adoption"
_ACTUAL_START_EVENT_TYPES = frozenset(
    {"confirmed", "corrected", "reconfirmed_after_delayed_settlement"}
)


_ORDER_FACTS_SQL = (
    "SELECT o.case_no,o.client_id,o.lifecycle_version,o.status,o.start_date,"
    "o.end_date,o.service_days,o.service_hours_per_day,o.floor_fee,"
    "o.service_start_time,o.service_end_time,o.service_end_day_offset,"
    "o.actual_start_date,o.actual_end_date,o.contract_identity,"
    "c.id AS client_row_id,c.case_no AS client_case_no,c.identity_status "
    "FROM orders o JOIN clients c ON c.id=o.client_id AND c.case_no=o.case_no "
    "WHERE o.case_no=%s"
)
_TERMS_EVENTS_SQL = (
    "SELECT e.id,e.case_no,e.expected_order_version,e.resulting_order_version,"
    "r.id AS receipt_id,r.case_no AS receipt_case_no,r.order_version AS receipt_order_version,"
    "r.lifecycle_event_id AS receipt_lifecycle_event_id "
    "FROM order_terms_change_events e "
    "LEFT JOIN order_terms_apply_receipts r ON r.order_terms_event_id=e.id "
    "WHERE e.case_no=%s ORDER BY e.id"
)
_ADOPTION_SQL = (
    "SELECT r.id,r.case_no,r.source_event_identity,r.outcome,r.expected_version,"
    "r.resulting_version,r.lifecycle_event_id "
    "FROM historical_order_adoption_receipts r "
    "WHERE r.case_no=%s ORDER BY r.id"
)
_LIFECYCLE_SQL = (
    "SELECT e.id,e.case_no,e.trigger_event,e.before_status,e.after_status,"
    "e.expected_version "
    "FROM order_lifecycle_state_events e WHERE e.case_no=%s ORDER BY e.id"
)
_ACTUAL_START_EVENTS_SQL = (
    "SELECT e.id,e.case_no,e.event_type,e.after_actual_start_date,"
    "e.expected_order_version,e.resulting_order_version,"
    "r.id AS receipt_id,r.case_no AS receipt_case_no,r.actual_start_date AS receipt_actual_start_date,"
    "r.order_version AS receipt_order_version,r.actual_start_event_id "
    "FROM order_actual_start_events e "
    "LEFT JOIN order_actual_start_apply_receipts r ON r.actual_start_event_id=e.id "
    "WHERE e.case_no=%s ORDER BY e.id"
)
_COMPLETION_EVENTS_SQL = (
    "SELECT e.id,e.case_no,e.trigger_event,e.before_status,e.after_status,"
    "e.expected_version,e.expected_version + 1 AS resulting_order_version,"
    "r.id AS receipt_id,r.case_no AS receipt_case_no,"
    "r.lifecycle_event_id AS receipt_lifecycle_event_id,r.order_version AS receipt_order_version "
    "FROM order_lifecycle_state_events e "
    "LEFT JOIN order_auto_completion_apply_receipts r ON r.lifecycle_event_id=e.id "
    "WHERE e.case_no=%s AND e.after_status='訂單完成' ORDER BY e.id"
)


class MySqlHistoricalBaselineOrdersOwnerAdapter:
    """Read the three Orders-owned v2 descriptors using a borrowed connection."""

    owner_domain = "orders"

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._descriptors = {
            (descriptor.step, descriptor.contract_id): descriptor
            for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
            if descriptor.owner_domain == self.owner_domain
            and descriptor.step in {1, 10, 11}
        }

    def read_owner_observations(
        self,
        identity: HistoricalOrderIdentity,
        descriptor: HistoricalBaselineOwnerRootDescriptor,
        *,
        for_update: bool = False,
    ) -> HistoricalBaselineOwnerObservationReadback:
        """Read exactly one descriptor collection without owning transaction state."""

        if not isinstance(identity, HistoricalOrderIdentity):
            raise TypeError("historical baseline Orders identity is invalid")
        if not isinstance(descriptor, HistoricalBaselineOwnerRootDescriptor):
            raise TypeError("historical baseline Orders descriptor is invalid")
        if not isinstance(for_update, bool):
            raise TypeError("historical baseline Orders read mode is invalid")
        expected = self._descriptors.get((descriptor.step, descriptor.contract_id))
        if expected is None or descriptor.canonical_tuple != expected.canonical_tuple:
            raise ValueError("historical_baseline_orders_descriptor_unsupported")

        try:
            with self._connection.cursor() as cursor:
                if descriptor.step == 1:
                    observation = self._read_order(cursor, identity, descriptor, for_update)
                elif descriptor.step == 10:
                    observation = self._read_actual_start(cursor, identity, descriptor, for_update)
                else:
                    observation = self._read_completion(cursor, identity, descriptor, for_update)
        except Exception:
            observation = _unavailable(
                descriptor,
                identity.case_no,
                f"orders_step_{descriptor.step}_read_failed",
            )
        return HistoricalBaselineOwnerObservationReadback(identity, (observation,))

    def _read_order(self, cursor: Any, identity, descriptor, for_update):
        order_rows = _rows(cursor, _ORDER_FACTS_SQL, identity.case_no, for_update)
        if not order_rows:
            return _unavailable(descriptor, identity.case_no, "orders_step_1_order_missing")
        if len(order_rows) != 1:
            return _unavailable(descriptor, identity.case_no, "orders_step_1_order_ambiguous")
        order = order_rows[0]
        if not _case_matches(order, identity.case_no, "client_case_no"):
            return _unavailable(descriptor, identity.case_no, "orders_step_1_cross_case")
        if order.get("case_no") != identity.case_no:
            return _unavailable(descriptor, identity.case_no, "orders_step_1_cross_case")
        if order.get("client_id") != order.get("client_row_id"):
            return _unavailable(descriptor, identity.case_no, "orders_step_1_client_binding_invalid")
        if not _terms_complete(order):
            return _unavailable(descriptor, identity.case_no, "orders_step_1_terms_incomplete")
        current_version = _nonnegative_int(order.get("lifecycle_version"))
        if current_version is None:
            return _unavailable(descriptor, identity.case_no, "orders_step_1_version_invalid")
        expected_identity = _ORDER_IDENTITY_PREFIX + identity.case_no
        if identity.order_identity != expected_identity:
            return _unavailable(descriptor, identity.case_no, "orders_step_1_identity_mismatch")

        lifecycle_rows = _rows(cursor, _LIFECYCLE_SQL, identity.case_no, for_update)
        adoption_rows = _rows(cursor, _ADOPTION_SQL, identity.case_no, for_update)
        terms_rows = _rows(cursor, _TERMS_EVENTS_SQL, identity.case_no, for_update)
        adoption = _exact_adoption(
            adoption_rows,
            lifecycle_rows,
            identity.case_no,
            current_version,
            str(order.get("status")),
        )
        if adoption[0] == "ambiguous":
            return _unavailable(descriptor, identity.case_no, "orders_step_1_adoption_ambiguous")
        if adoption[0] == "invalid":
            return _unavailable(descriptor, identity.case_no, "orders_step_1_adoption_invalid")
        if adoption[0] == "exact":
            row = adoption[1]
            if not _is_positive_int(row.get("id")):
                return _unavailable(descriptor, identity.case_no, "orders_step_1_adoption_invalid")
            return _available(
                descriptor,
                identity.case_no,
                identity.order_identity,
                str(row["source_event_identity"]),
                int(row["id"]),
            )

        exact_terms = _exact_terms(
            terms_rows,
            lifecycle_rows,
            identity.case_no,
            current_version,
            str(order.get("status")),
        )
        if exact_terms[0] == "ambiguous":
            return _unavailable(descriptor, identity.case_no, "orders_step_1_terms_event_ambiguous")
        if exact_terms[0] == "invalid":
            return _unavailable(descriptor, identity.case_no, "orders_step_1_terms_event_invalid")
        if exact_terms[0] != "exact":
            return _unavailable(descriptor, identity.case_no, "orders_step_1_source_event_missing")
        event = exact_terms[1]
        return _available(
            descriptor,
            identity.case_no,
            identity.order_identity,
            f"orders-terms-event:{identity.case_no}:{event['id']}",
            current_version,
        )

    def _read_actual_start(self, cursor: Any, identity, descriptor, for_update):
        order_rows = _rows(cursor, _ORDER_FACTS_SQL, identity.case_no, for_update)
        if len(order_rows) != 1:
            return _unavailable(
                descriptor,
                identity.case_no,
                "orders_step_10_order_missing" if not order_rows else "orders_step_10_order_ambiguous",
            )
        order = order_rows[0]
        if order.get("case_no") != identity.case_no or order.get("client_case_no") != identity.case_no:
            return _unavailable(descriptor, identity.case_no, "orders_step_10_cross_case")
        if identity.order_identity != _ORDER_IDENTITY_PREFIX + identity.case_no:
            return _unavailable(descriptor, identity.case_no, "orders_step_10_identity_mismatch")
        current_version = _nonnegative_int(order.get("lifecycle_version"))
        event_date = order.get("actual_start_date")
        if current_version is None or event_date is None:
            return _unavailable(descriptor, identity.case_no, "orders_step_10_current_root_incomplete")
        rows = _rows(cursor, _ACTUAL_START_EVENTS_SQL, identity.case_no, for_update)
        eligible = []
        malformed = False
        for row in rows:
            if row.get("case_no") != identity.case_no or row.get("receipt_case_no") not in (None, identity.case_no):
                malformed = True
                continue
            resulting_version = row.get("resulting_order_version")
            if not _is_nonnegative_int(resulting_version) or resulting_version > current_version:
                malformed = True
                continue
            if row.get("expected_order_version") != resulting_version - 1:
                continue
            if row.get("event_type") not in _ACTUAL_START_EVENT_TYPES:
                malformed = True
                continue
            if row.get("after_actual_start_date") != event_date:
                continue
            if (
                not _is_positive_int(row.get("id"))
                or not _is_positive_int(row.get("receipt_id"))
                or row.get("actual_start_event_id") != row.get("id")
                or row.get("receipt_actual_start_date") != event_date
            ):
                malformed = True
                continue
            if row.get("receipt_order_version") != row.get("resulting_order_version"):
                malformed = True
                continue
            eligible.append(row)
        if malformed:
            return _unavailable(descriptor, identity.case_no, "orders_step_10_event_invalid")
        if not eligible:
            return _unavailable(descriptor, identity.case_no, "orders_step_10_event_missing")
        latest_version = max(row["resulting_order_version"] for row in eligible)
        latest = [row for row in eligible if row["resulting_order_version"] == latest_version]
        if len(latest) != 1:
            return _unavailable(descriptor, identity.case_no, "orders_step_10_event_ambiguous")
        event = latest[0]
        event_identity = f"orders-actual-start-event:{identity.case_no}:{event['id']}"
        return _available(
            descriptor,
            identity.case_no,
            event_identity,
            event_identity,
            event["resulting_order_version"],
        )

    def _read_completion(self, cursor: Any, identity, descriptor, for_update):
        order_rows = _rows(cursor, _ORDER_FACTS_SQL, identity.case_no, for_update)
        if len(order_rows) != 1:
            return _unavailable(
                descriptor,
                identity.case_no,
                "orders_step_11_order_missing" if not order_rows else "orders_step_11_order_ambiguous",
            )
        order = order_rows[0]
        if order.get("case_no") != identity.case_no or order.get("client_case_no") != identity.case_no:
            return _unavailable(descriptor, identity.case_no, "orders_step_11_cross_case")
        if identity.order_identity != _ORDER_IDENTITY_PREFIX + identity.case_no:
            return _unavailable(descriptor, identity.case_no, "orders_step_11_identity_mismatch")
        current_version = _nonnegative_int(order.get("lifecycle_version"))
        if current_version is None or current_version <= 0 or order.get("status") != _COMPLETED_STATUS:
            return _unavailable(descriptor, identity.case_no, "orders_step_11_current_root_incomplete")
        rows = _rows(cursor, _COMPLETION_EVENTS_SQL, identity.case_no, for_update)
        eligible = []
        malformed = False
        for row in rows:
            if row.get("case_no") != identity.case_no or row.get("receipt_case_no") not in (None, identity.case_no):
                malformed = True
                continue
            if (
                row.get("after_status") != _COMPLETED_STATUS
                or row.get("trigger_event") != "evaluation_time_reached"
                or row.get("before_status") != "服務中"
                or row.get("resulting_order_version") != current_version
            ):
                malformed = True
                continue
            if row.get("expected_version") != current_version - 1:
                continue
            if (
                not _is_positive_int(row.get("id"))
                or not _is_positive_int(row.get("receipt_id"))
                or row.get("receipt_lifecycle_event_id") != row.get("id")
            ):
                malformed = True
                continue
            if row.get("receipt_order_version") != current_version:
                malformed = True
                continue
            eligible.append(row)
        if len(eligible) > 1:
            return _unavailable(descriptor, identity.case_no, "orders_step_11_event_ambiguous")
        if malformed:
            return _unavailable(descriptor, identity.case_no, "orders_step_11_event_invalid")
        if not eligible:
            return _unavailable(descriptor, identity.case_no, "orders_step_11_event_missing")
        event = eligible[0]
        event_identity = f"orders-completion-event:{identity.case_no}:{event['id']}"
        return _available(descriptor, identity.case_no, event_identity, event_identity, current_version)


def _rows(cursor: Any, statement: str, case_no: str, for_update: bool) -> tuple[Mapping[str, Any], ...]:
    suffix = " FOR UPDATE" if for_update else ""
    cursor.execute(statement + suffix, (case_no,))
    raw = cursor.fetchall()
    if raw is None:
        return ()
    rows = tuple(raw)
    if any(not isinstance(row, Mapping) for row in rows):
        raise TypeError("historical baseline Orders read row is invalid")
    return rows


def _terms_complete(row: Mapping[str, Any]) -> bool:
    if row.get("terms_complete") is False:
        return False
    required = (
        "start_date",
        "end_date",
        "service_days",
        "service_hours_per_day",
        "floor_fee",
        "service_start_time",
        "service_end_time",
        "service_end_day_offset",
    )
    return all(row.get(key) is not None for key in required)


def _exact_adoption(
    rows,
    lifecycle_rows,
    case_no: str,
    current_version: int,
    current_status: str,
):
    candidates = []
    invalid = False
    lifecycle_by_id = {row.get("id"): row for row in lifecycle_rows}
    for row in rows:
        if row.get("case_no") != case_no:
            invalid = True
            continue
        if row.get("outcome") != "adopted":
            continue
        source = row.get("source_event_identity")
        lifecycle = lifecycle_by_id.get(row.get("lifecycle_event_id"))
        expected_version = row.get("expected_version")
        resulting_version = row.get("resulting_version")
        if (
            isinstance(source, str)
            and source.strip()
            and _is_positive_int(row.get("id"))
            and expected_version == current_version == resulting_version
            and row.get("lifecycle_event_id") is None
        ):
            candidates.append(row)
            continue
        if (
            not isinstance(source, str)
            or not source.strip()
            or resulting_version != current_version
            or expected_version != current_version - 1
            or not _is_positive_int(row.get("id"))
            or not _is_positive_int(row.get("lifecycle_event_id"))
            or lifecycle is None
            or lifecycle.get("case_no") != case_no
            or lifecycle.get("expected_version") != current_version - 1
            or lifecycle.get("after_status") != current_status
            or lifecycle.get("trigger_event") != _HISTORICAL_ADOPTION_TRIGGER
        ):
            invalid = True
            continue
        candidates.append(row)
    if len(candidates) > 1:
        return "ambiguous", None
    if invalid:
        return "invalid", None
    return ("exact", candidates[0]) if candidates else ("none", None)


def _exact_terms(
    rows,
    lifecycle_rows,
    case_no: str,
    current_version: int,
    current_status: str,
):
    lifecycle_by_id = {row.get("id"): row for row in lifecycle_rows}
    candidates = []
    invalid = False
    for row in rows:
        if row.get("case_no") != case_no:
            invalid = True
            continue
        resulting_version = row.get("resulting_order_version")
        if not _is_nonnegative_int(resulting_version) or resulting_version != current_version:
            invalid = True
            continue
        lifecycle = lifecycle_by_id.get(row.get("receipt_lifecycle_event_id"))
        if (
            not _is_positive_int(row.get("id"))
            or row.get("expected_order_version") != resulting_version - 1
            or not _is_positive_int(row.get("receipt_id"))
            or not _is_positive_int(row.get("receipt_lifecycle_event_id"))
            or row.get("receipt_case_no") != case_no
            or row.get("receipt_order_version") != resulting_version
            or lifecycle is None
            or lifecycle.get("case_no") != case_no
            or lifecycle.get("expected_version") != current_version - 1
            or lifecycle.get("after_status") != current_status
            or lifecycle.get("trigger_event") != "terms_changed"
        ):
            invalid = True
            continue
        candidates.append(row)
    if len(candidates) > 1:
        latest_version = max(row["resulting_order_version"] for row in candidates)
        candidates = [
            row for row in candidates
            if row["resulting_order_version"] == latest_version
        ]
    if len(candidates) > 1:
        return "ambiguous", None
    if invalid:
        return "invalid", None
    return ("exact", candidates[0]) if candidates else ("none", None)


def _case_matches(row: Mapping[str, Any], case_no: str, field: str) -> bool:
    return row.get(field) == case_no


def _nonnegative_int(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value <= _SIGNED_BIGINT_MAXIMUM else None


def _is_nonnegative_int(value: Any) -> bool:
    return _nonnegative_int(value) is not None


def _is_positive_int(value: Any) -> bool:
    return type(value) is int and 0 < value <= _SIGNED_BIGINT_MAXIMUM


def _available(descriptor, case_no, root_identity, source_event_identity, source_version):
    return HistoricalBaselineOwnerObservation(
        descriptor,
        root_identity,
        source_event_identity,
        source_version,
        True,
        None,
        case_no,
    )


def _unavailable(descriptor, case_no: str, code: str):
    require_canonical_text(code, "historical baseline Orders unavailable code", 500)
    return HistoricalBaselineOwnerObservation.unavailable(descriptor, code=code, case_no=case_no)


HistoricalBaselineOrdersOwnerAdapter = MySqlHistoricalBaselineOrdersOwnerAdapter
MySqlHistoricalBaselineOwnerOrdersAdapter = MySqlHistoricalBaselineOrdersOwnerAdapter


__all__ = [
    "HistoricalBaselineOrdersOwnerAdapter",
    "MySqlHistoricalBaselineOrdersOwnerAdapter",
    "MySqlHistoricalBaselineOwnerOrdersAdapter",
]
