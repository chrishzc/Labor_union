from __future__ import annotations

from subsystems.access.admin_command_support import fingerprint, replay_result

_FAMILY = "scheduling_holiday_maintenance/v1"


def preview(repository, command):
    return _preview_payload(command, repository.load_holiday(command["holiday_date"]))


def apply(repository, command, preview_fingerprint, idempotency_key, actor, reason):
    request_fingerprint = fingerprint({"command": command, "actor": actor, "reason": reason})
    replay = replay_result(repository.load_receipt(_FAMILY, idempotency_key), request_fingerprint)
    if replay is not None:
        return replay
    preview_payload = _preview_payload(command, repository.load_holiday(command["holiday_date"], for_update=True))
    if preview_payload["preview_fingerprint"] != preview_fingerprint:
        raise ValueError("stale_preview")
    if command["action"] == "delete":
        repository.delete_holiday(command["holiday_date"])
    else:
        repository.upsert_holiday(command["holiday_date"], command["holiday_name"], command["is_double_pay_default"])
    result = {"action": command["action"], "holiday_date": command["holiday_date"], "changed": True}
    repository.save_receipt(_FAMILY, idempotency_key, request_fingerprint, preview_fingerprint, actor, reason, result)
    repository.commit()
    return result


def _preview_payload(command, before):
    if command["action"] == "delete" and before is None:
        raise ValueError("holiday_not_found")
    payload = {"command": command, "before": before, "schedule_impact": "none", "payroll_impact": "none"}
    return {**payload, "preview_fingerprint": fingerprint(payload)}
