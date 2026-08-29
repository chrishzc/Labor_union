"""
File: test_case_anomaly_readback.py
Description: 驗證案件異常回讀的排序、零案件與 fail-closed 契約。
"""

from datetime import date, datetime, timezone

import pytest

from subsystems.anomalies.case_anomaly_readback import (
    CaseAnomalyAlert,
    CaseAnomalyDefinitionRead,
    CaseAnomalyReadbackService,
    CaseAnomalyReadbackStatus,
    resolve_case_anomalies,
)


class _Source:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def read_definition(self, case_no, definition_code, *, as_of):
        self.calls.append((case_no, definition_code, as_of))
        return self.results[definition_code]


def _alert(code, fingerprint="a" * 64, identity="CASE-1", version=4):
    return CaseAnomalyAlert(code, fingerprint, identity, version, "open")


AS_OF = date(2026, 8, 27)


def test_resolver_returns_active_alerts_and_source_versions_for_single_case():
    source = _Source({
        "SCHEDULE-006": CaseAnomalyDefinitionRead(
            "SCHEDULE-006", (_alert("SCHEDULE-006"),), (("case:CASE-1", 4),)
        )
    })

    result = resolve_case_anomalies(
        "CASE-1", ["SCHEDULE-006"], source,
        as_of=AS_OF,
        read_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
    )

    assert result.status is CaseAnomalyReadbackStatus.COMPLETE
    assert result.resolved_alerts[0].definition_code == "SCHEDULE-006"
    assert result.source_versions == (("case:CASE-1", 4),)
    assert result.unresolved_definitions == ()


def test_resolver_distinguishes_zero_alerts_from_unresolved_definition():
    source = _Source({
        "SCHEDULE-002": CaseAnomalyDefinitionRead("SCHEDULE-002"),
        "CLIENTREFUND-001": CaseAnomalyDefinitionRead(
            "CLIENTREFUND-001", unresolved_reason="canonical_binding_unavailable"
        ),
    })

    result = CaseAnomalyReadbackService(source).resolve_case_anomalies(
        "CASE-1", ["SCHEDULE-002", "CLIENTREFUND-001"], as_of=AS_OF
    )

    assert result.resolved_alerts == ()
    assert result.status is CaseAnomalyReadbackStatus.UNAVAILABLE
    assert result.unresolved_definitions == (
        ("CLIENTREFUND-001", "canonical_binding_unavailable"),
    )


def test_resolver_keeps_multi_case_alert_when_source_binds_target_case():
    source = _Source({
        "SCHEDULE-003": CaseAnomalyDefinitionRead(
            "SCHEDULE-003",
            (_alert("SCHEDULE-003", "b" * 64, "101:202", 9),),
            (("101:202", 9),),
        )
    })

    result = resolve_case_anomalies("CASE-2", ["SCHEDULE-003"], source, as_of=AS_OF)

    assert result.status is CaseAnomalyReadbackStatus.COMPLETE
    assert result.resolved_alerts[0].source_identity == "101:202"


def test_unrequested_or_identity_mismatched_result_fails_closed():
    source = _Source({
        "SCHEDULE-006": CaseAnomalyDefinitionRead("SCHEDULE-002"),
    })

    result = resolve_case_anomalies(
        "CASE-1", ["SCHEDULE-006", "LINE-004"], source, as_of=AS_OF
    )

    assert result.status is CaseAnomalyReadbackStatus.UNAVAILABLE
    assert result.unresolved_definitions == (
        ("LINE-004", "definition_not_in_cancellation_readback"),
        ("SCHEDULE-006", "definition_identity_mismatch"),
    )


@pytest.mark.parametrize("value", ["", " CASE-1", "CASE-1 "])
def test_case_identity_is_strict(value):
    with pytest.raises(ValueError):
        resolve_case_anomalies(value, ["SCHEDULE-006"], _Source({}), as_of=AS_OF)
