"""
File: test_anomaly_manual_resolve_guard.py
Description: 驗證人工 tracking resolve 不能代替 owner root 修正。
"""

import pytest
from fastapi import HTTPException

from api.routes.anomaly_registry import claim_anomaly, query_anomaly_detail, resolve_anomaly
from domains.anomalies.registry import default_anomaly_registry
from subsystems.anomalies.alert_workflow import AnomalyApplication


class _MustNotMutateRepository:
    def __getattr__(self, _name):
        raise AssertionError("manual resolve must not read or mutate anomaly storage")


def test_generic_manual_resolve_is_fail_closed_before_storage() -> None:
    application = AnomalyApplication(
        default_anomaly_registry(),
        _MustNotMutateRepository(),
        lambda: pytest.fail("manual resolve must not open a unit of work"),
    )

    with pytest.raises(ValueError, match="anomaly_manual_resolve_forbidden"):
        application.resolve(object())


@pytest.mark.parametrize(
    ("route", "code", "replacement"),
    (
        (
            query_anomaly_detail,
            "anomaly_fingerprint_detail_retired",
            "GET /api/v1/anomaly-recovery/{issue_key}",
        ),
        (
            claim_anomaly,
            "anomaly_claim_retired",
            "Owning Domain typed Query/Preview/Apply action",
        ),
        (
            resolve_anomaly,
            "anomaly_resolve_retired",
            "Owning Domain typed Query/Preview/Apply action followed by bounded recheck",
        ),
    ),
)
def test_legacy_fingerprint_workflow_routes_are_stable_typed_410(
    route, code: str, replacement: str
) -> None:
    with pytest.raises(HTTPException) as raised:
        route("a" * 64)

    error = raised.value
    assert error.status_code == 410
    payload = error.detail["error"]
    assert payload["code"] == code
    assert payload["retryable"] is False
    assert payload["domain_blockers"] == [
        f"replacement_identifier:{replacement}",
        "removal_gate:blocked_external_caller_evidence",
    ]
