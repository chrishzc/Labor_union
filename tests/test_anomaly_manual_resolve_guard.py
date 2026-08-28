"""
File: test_anomaly_manual_resolve_guard.py
Description: 驗證人工 tracking resolve 不能代替 owner root 修正。
"""

import pytest

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
