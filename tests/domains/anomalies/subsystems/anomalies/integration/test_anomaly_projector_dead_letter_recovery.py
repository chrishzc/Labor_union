"""
File: test_anomaly_projector_dead_letter_recovery.py
Description: 驗證舊 projector dead-letter URL 在 generic replacement 可用前 fail closed。
"""

from fastapi import HTTPException
import pytest

from api.routes.anomaly_recovery import (
    apply_projector_dead_letter_retry,
    apply_projector_dead_letter_supersede,
    preview_projector_dead_letter_retry as preview_retry_route,
    preview_projector_dead_letter_supersede as preview_supersede_route,
    retry_anomaly_projector,
    scan_anomaly_definition,
)
@pytest.mark.parametrize(
    "route",
    (preview_retry_route, apply_projector_dead_letter_retry,
     preview_supersede_route, apply_projector_dead_letter_supersede),
)
def test_legacy_projector_dead_letter_routes_fail_closed(route) -> None:
    with pytest.raises(HTTPException) as raised:
        route("government_overpayment", 17)

    error = raised.value
    assert error.status_code == 410
    payload = error.detail["error"]
    assert payload["code"] == "anomaly_projector_dead_letter_endpoint_retired"
    assert payload["retryable"] is False
    assert payload["domain_blockers"] == [
        "replacement_identifier:Global durable-job retry/supersede mechanism"
    ]


def test_legacy_projector_dead_letter_query_fails_closed() -> None:
    from api.routes.anomaly_recovery import query_projector_dead_letters

    with pytest.raises(HTTPException) as raised:
        query_projector_dead_letters()

    _assert_retired_error(raised.value)


@pytest.mark.parametrize(
    ("invoke", "code", "replacement"),
    (
        (
            lambda: scan_anomaly_definition("IMPORT-006"),
            "anomaly_definition_scan_retired",
            "Global durable anomaly.recheck job with an owner-composed bounded detector",
        ),
        (
            retry_anomaly_projector,
            "anomaly_projector_retry_retired",
            "Global durable-job retry/supersede mechanism",
        ),
    ),
)
def test_legacy_maintenance_entries_are_stable_typed_410(
    invoke, code: str, replacement: str
) -> None:
    with pytest.raises(HTTPException) as raised:
        invoke()

    error = raised.value
    assert error.status_code == 410
    payload = error.detail["error"]
    assert payload["code"] == code
    assert payload["retryable"] is False
    assert payload["domain_blockers"] == [
        f"replacement_identifier:{replacement}",
        "removal_gate:blocked_external_caller_evidence",
    ]


def _assert_retired_error(error: HTTPException) -> None:
    assert error.status_code == 410
    assert error.detail["error"] == {
        "category": "domain_blocked",
        "code": "anomaly_projector_dead_letter_endpoint_retired",
        "message": "Projector dead-letter recovery has moved to the Global durable-job contract.",
        "correlation_id": error.detail["error"]["correlation_id"],
        "field_errors": [],
        "domain_blockers": [
            "replacement_identifier:Global durable-job retry/supersede mechanism",
        ],
        "retryable": False,
        "current_version": None,
    }
