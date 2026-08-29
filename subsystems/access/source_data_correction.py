"""Preview/Apply corrections for approved source-data tables only."""

from __future__ import annotations

from typing import Any, Mapping

from subsystems.access.admin_command_support import fingerprint, replay_result


_FAMILY = "access_source_data_correction/v1"
_EDITABLE_FIELDS = {
    "clients": {"name", "gender", "phone", "city", "address", "notes", "admin_notes", "reject_reason"},
    "beclass_records": {"name", "email", "phone", "tel", "ext", "city", "zip_code", "address", "admin_notes"},
    "staff": {"name", "phone", "tel", "tel_ext", "email", "city", "zip_code", "address", "birthday", "has_massage_cert", "weekly_rest_days", "service_regions", "special_skills", "care_babies"},
}


def editable_fields(table: str) -> tuple[str, ...]:
    return tuple(sorted(_EDITABLE_FIELDS.get(table, ())))


def preview(repository, table: str, row_id: int, updates: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _validate(table, updates)
    row = repository.load_source_row(table, row_id)
    return _preview_payload(table, row_id, row, normalized)


def apply(repository, unit_of_work_factory, table: str, row_id: int, updates: Mapping[str, Any], preview_fingerprint: str, idempotency_key: str, actor: str, reason: str) -> dict[str, Any]:
    normalized = _validate(table, updates)
    request_fingerprint = fingerprint({"table": table, "row_id": row_id, "updates": normalized, "actor": actor, "reason": reason})
    replay = replay_result(repository.load_receipt(_FAMILY, idempotency_key), request_fingerprint)
    if replay is not None:
        return replay
    with unit_of_work_factory() as unit_of_work:
        current = repository.load_source_row(table, row_id, for_update=True)
        preview_payload = _preview_payload(table, row_id, current, normalized)
        if preview_payload["preview_fingerprint"] != preview_fingerprint:
            raise ValueError("stale_preview")
        repository.update_source_row(table, row_id, normalized)
        result = {"table": table, "row_id": row_id, "changed_fields": sorted(normalized)}
        repository.save_receipt(_FAMILY, idempotency_key, request_fingerprint, preview_fingerprint, actor, reason, result)
        unit_of_work.commit()
        return result


def _validate(table: str, updates: Mapping[str, Any]) -> dict[str, Any]:
    allowed = _EDITABLE_FIELDS.get(table)
    if allowed is None:
        raise ValueError("source_table_not_editable")
    if not updates:
        raise ValueError("source_updates_required")
    protected = set(updates) - allowed
    if protected:
        raise ValueError("protected_source_field:" + ",".join(sorted(protected)))
    return dict(updates)


def _preview_payload(table: str, row_id: int, row: Mapping[str, Any] | None, updates: Mapping[str, Any]) -> dict[str, Any]:
    if row is None:
        raise ValueError("source_row_not_found")
    changes = {field: {"before": row.get(field), "after": value} for field, value in updates.items() if row.get(field) != value}
    payload = {"table": table, "row_id": row_id, "changes": changes}
    return {**payload, "preview_fingerprint": fingerprint(payload)}
