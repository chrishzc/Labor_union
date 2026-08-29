from __future__ import annotations

from subsystems.access.admin_command_support import fingerprint, replay_result

_FAMILY = "orders_client_name_maintenance/v1"


def preview(repository, case_no, client_name):
    return _preview_payload(case_no, client_name, repository.load_client_name(case_no))


def apply(repository, unit_of_work_factory, case_no, client_name, preview_fingerprint, idempotency_key, actor, reason):
    request_fingerprint = fingerprint({"case_no": case_no, "client_name": client_name, "actor": actor, "reason": reason})
    replay = replay_result(repository.load_receipt(_FAMILY, idempotency_key), request_fingerprint)
    if replay is not None:
        return replay
    with unit_of_work_factory() as unit_of_work:
        preview_payload = _preview_payload(case_no, client_name, repository.load_client_name(case_no, for_update=True))
        if preview_payload["preview_fingerprint"] != preview_fingerprint:
            raise ValueError("stale_preview")
        repository.update_client_name(case_no, client_name)
        result = {"case_no": case_no, "client_name": client_name, "changed": preview_payload["before_client_name"] != client_name}
        repository.save_receipt(_FAMILY, idempotency_key, request_fingerprint, preview_fingerprint, actor, reason, result)
        unit_of_work.commit()
        return result


def _preview_payload(case_no, client_name, before):
    if before is None:
        raise ValueError("client_not_found")
    payload = {"case_no": case_no, "before_client_name": before["name"], "after_client_name": client_name, "terms_impact": "none", "scheduling_impact": "none"}
    return {**payload, "preview_fingerprint": fingerprint(payload)}
