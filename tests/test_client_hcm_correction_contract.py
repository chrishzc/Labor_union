"""Focused contract tests for the Client-owned HCM correction boundary."""

from __future__ import annotations

import pytest

from domains.clients.hcm_correction import ClientHcmCorrectionCommand


def _command(**changes):
    values = {
        "client_id": 3,
        "case_no": "CASE-3",
        "expected_client_version": 4,
        "review_identity": "hcm-review:3",
        "source_event_identity": "hcm-source:3",
        "field_path": "服務方式",
        "values": {"service_type": "週休一日"},
        "idempotency_key": "hcm-correction:3",
        "actor": "admin",
        "reason": "人工核准修正",
        "correlation_id": "corr:3",
    }
    values.update(changes)
    return ClientHcmCorrectionCommand(**values)


def test_client_command_accepts_service_type_only() -> None:
    command = _command()
    assert command.values == {"service_type": "週休一日"}


@pytest.mark.parametrize(
    "values",
    [
        {"end_date": "2026-09-01"},
        {"orders.service_type": "週休一日"},
        {"identity_status": "一般市民"},
    ],
)
def test_client_command_rejects_non_client_targets(values) -> None:
    with pytest.raises(ValueError, match="Client-owned"):
        _command(values=values)
