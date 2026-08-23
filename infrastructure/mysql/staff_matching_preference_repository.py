"""
File: staff_matching_preference_repository.py
Description: 提供 Staff matching preference 的 MySQL aggregate lock 與持久化 adapter。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from domains.scheduling.staff_matching_preferences import (
    PreferenceComparisonOperator,
    PreferenceValue,
    PreferenceValueKind,
    StaffPreferenceDefinition,
    parse_preference_value,
)
from shared_kernel.identities import IdempotencyKey
from subsystems.scheduling.staff_matching_preference_workflow import (
    PreferenceEvent,
    PreferenceReceipt,
)
from subsystems.scheduling.matching_coordination_query import (
    StaffProfileValuesFacts,
)


class MySqlStaffMatchingPreferenceRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def list_definitions(self, *, active_only: bool, for_update: bool = False):
        clause = " WHERE status='active'" if active_only else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                _DEFINITION_SELECT
                + clause
                + " ORDER BY id"
                + (" FOR UPDATE" if for_update else "")
            )
            rows = cursor.fetchall() or ()
        return tuple(_definition_with_version(row) for row in rows)

    def load_definitions(
        self, *, for_update: bool = False
    ) -> tuple[tuple[StaffPreferenceDefinition, int], ...]:
        """Project active owner definitions through the M3 typed read port."""

        return self.list_definitions(active_only=True, for_update=for_update)

    def load_profile_values(
        self, staff_ids: tuple[int, ...], *, for_update: bool = False
    ) -> tuple[StaffProfileValuesFacts, ...]:
        """Read canonical profile values without creating a command claim."""

        if staff_ids != tuple(sorted(set(staff_ids))) or any(
            isinstance(staff_id, bool) or not isinstance(staff_id, int) or staff_id <= 0
            for staff_id in staff_ids
        ):
            raise ValueError("staff_profile_ids_not_canonical")
        definitions = {
            definition.preference_key: definition
            for definition, _version in self.load_definitions(for_update=for_update)
        }
        result = []
        for staff_id in staff_ids:
            version, raw_values = self.load_profile(staff_id, for_update=for_update)
            values = []
            for key, payload in sorted(raw_values.items()):
                definition = definitions.get(key)
                if definition is None:
                    raise ValueError("preference_definition_not_active")
                values.append((key, parse_preference_value(definition, payload)))
            result.append(StaffProfileValuesFacts(staff_id, version, tuple(values)))
        return tuple(result)

    def load_definition(self, preference_key: str, *, for_update: bool):
        lock_clause = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                _DEFINITION_SELECT + " WHERE preference_key=%s" + lock_clause,
                (preference_key,),
            )
            row = cursor.fetchone()
        return None if row is None else _definition_with_version(row)

    def staff_exists(self, staff_id: int) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM staff WHERE id=%s", (staff_id,))
            return cursor.fetchone() is not None

    def lock_profile_aggregate(self, staff_id: int) -> None:
        """Lock the stable staff identity even when no profile row exists."""
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT id FROM staff WHERE id=%s FOR UPDATE", (staff_id,))
            if cursor.fetchone() is None:
                raise ValueError("staff_not_found")

    def load_profile(self, staff_id: int, *, for_update: bool):
        lock_clause = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT version FROM staff_matching_preference_profiles "
                "WHERE staff_id=%s" + lock_clause,
                (staff_id,),
            )
            profile = cursor.fetchone()
            cursor.execute(
                "SELECT d.preference_key,v.value_json "
                "FROM staff_matching_preference_values v "
                "JOIN staff_matching_preference_definitions d "
                "ON d.id=v.definition_id WHERE v.staff_id=%s"
                + (" FOR UPDATE" if for_update else ""),
                (staff_id,),
            )
            rows = cursor.fetchall() or ()
        values = {str(row["preference_key"]): _json_object(row["value_json"]) for row in rows}
        return (0 if profile is None else int(profile["version"]), values)

    def find_receipt(self, key: IdempotencyKey, *, for_update: bool):
        lock_clause = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT command_fingerprint,result_json "
                "FROM staff_matching_preference_receipts "
                "WHERE idempotency_key=%s" + lock_clause,
                (key.value,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return {
            "command_fingerprint": str(row["command_fingerprint"]),
            "result": _json_object(row["result_json"]),
        }

    def save_definition(self, definition, version, actor):
        with self._connection.cursor() as cursor:
            cursor.execute(
                _DEFINITION_UPSERT,
                _definition_values(definition, version, actor),
            )

    def save_profile(self, staff_id, values, version, actor):
        with self._connection.cursor() as cursor:
            cursor.execute(
                _PROFILE_UPSERT,
                (staff_id, version, actor, actor),
            )
            definition_ids = _definition_ids(cursor, tuple(values))
            _delete_removed_values(cursor, staff_id, tuple(definition_ids.values()))
            for key, value in values.items():
                cursor.execute(
                    _VALUE_UPSERT,
                    (
                        staff_id,
                        definition_ids[key],
                        _canonical_json(value.canonical_payload()),
                        version,
                        actor,
                    ),
                )

    def append_event(self, event: PreferenceEvent) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(_EVENT_INSERT, _event_values(event))
            return int(cursor.lastrowid)

    def save_receipt(self, receipt: PreferenceReceipt) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_INSERT, _receipt_values(receipt))


def _definition_with_version(row):
    definition = StaffPreferenceDefinition(
        str(row["preference_key"]),
        str(row["display_name"]),
        PreferenceValueKind(str(row["value_kind"])),
        bool(row["is_filterable"]),
        row.get("order_fact_key"),
        _comparison_operator(row.get("comparison_operator")),
        str(row["status"]) == "active",
    )
    return definition, int(row["version"])


def _comparison_operator(value):
    return None if value is None else PreferenceComparisonOperator(str(value))


def _definition_values(definition, version, actor):
    return (
        definition.preference_key,
        definition.display_name,
        definition.value_kind.value,
        int(definition.is_filterable),
        definition.order_fact_key,
        None if definition.comparison_operator is None else definition.comparison_operator.value,
        "active" if definition.active else "inactive",
        version,
        actor,
        actor,
    )


def _definition_ids(cursor, keys):
    if not keys:
        return {}
    placeholders = ",".join(["%s"] * len(keys))
    cursor.execute(
        "SELECT id,preference_key FROM staff_matching_preference_definitions "
        f"WHERE preference_key IN ({placeholders}) AND status='active'",
        keys,
    )
    result = {str(row["preference_key"]): int(row["id"]) for row in cursor.fetchall() or ()}
    if set(result) != set(keys):
        raise ValueError("preference_definition_not_active")
    return result


def _delete_removed_values(cursor, staff_id, kept_definition_ids):
    if not kept_definition_ids:
        cursor.execute("DELETE FROM staff_matching_preference_values WHERE staff_id=%s", (staff_id,))
        return
    placeholders = ",".join(["%s"] * len(kept_definition_ids))
    cursor.execute(
        "DELETE FROM staff_matching_preference_values "
        f"WHERE staff_id=%s AND definition_id NOT IN ({placeholders})",
        (staff_id, *kept_definition_ids),
    )


def _event_values(event):
    return (
        event.event_type,
        event.aggregate_identity,
        event.resulting_version,
        event.actor,
        event.reason,
        event.correlation_id,
        event.idempotency_key,
        _canonical_json(event.before),
        _canonical_json(event.after),
    )


def _receipt_values(receipt):
    return (
        receipt.key.value,
        receipt.command_family,
        receipt.aggregate_identity,
        receipt.command_fingerprint.value,
        receipt.preview_fingerprint.value,
        _canonical_json(receipt.result),
    )


def _json_object(value: Any) -> dict[str, Any]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, Mapping):
        raise ValueError("staff_preference_json_invalid")
    return dict(parsed)


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


_DEFINITION_SELECT = (
    "SELECT id,preference_key,display_name,value_kind,is_filterable,"
    "order_fact_key,comparison_operator,status,version "
    "FROM staff_matching_preference_definitions"
)

_DEFINITION_UPSERT = (
    "INSERT INTO staff_matching_preference_definitions "
    "(preference_key,display_name,value_kind,is_filterable,order_fact_key,"
    "comparison_operator,status,version,created_by,updated_by) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
    "ON DUPLICATE KEY UPDATE display_name=VALUES(display_name),"
    "is_filterable=VALUES(is_filterable),status=VALUES(status),"
    "version=VALUES(version),updated_by=VALUES(updated_by)"
)

_PROFILE_UPSERT = (
    "INSERT INTO staff_matching_preference_profiles "
    "(staff_id,version,created_by,updated_by) VALUES (%s,%s,%s,%s) "
    "ON DUPLICATE KEY UPDATE version=VALUES(version),updated_by=VALUES(updated_by)"
)

_VALUE_UPSERT = (
    "INSERT INTO staff_matching_preference_values "
    "(staff_id,definition_id,value_json,profile_version,updated_by) "
    "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
    "value_json=VALUES(value_json),profile_version=VALUES(profile_version),"
    "updated_by=VALUES(updated_by)"
)

_EVENT_INSERT = (
    "INSERT INTO staff_matching_preference_events "
    "(event_type,aggregate_identity,resulting_version,actor,reason,"
    "correlation_id,idempotency_key,before_json,after_json) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

_RECEIPT_INSERT = (
    "INSERT INTO staff_matching_preference_receipts "
    "(idempotency_key,command_family,aggregate_identity,command_fingerprint,"
    "preview_fingerprint,result_json) VALUES (%s,%s,%s,%s,%s,%s)"
)
