from datetime import date

import pytest

from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.orders.actual_start_workflow import ActualStartApplyRequest


def _request(*, reason: str = "confirm service start") -> ActualStartApplyRequest:
    return ActualStartApplyRequest(
        "CASE-1",
        date(2026, 8, 3),
        ExpectedVersion(1),
        ExpectedVersion(2),
        ExpectedVersion(3),
        ExpectedVersion(4),
        PreviewFingerprint("a" * 64),
        IdempotencyKey("actual-start-1"),
        ActorContext("admin"),
        reason,
        CorrelationId("actual-start-correlation"),
    )


def test_actual_start_request_uses_direct_canonical_source_contract() -> None:
    request = _request()

    assert request.case_no == "CASE-1"
    assert request.new_actual_start_date == date(2026, 8, 3)


def test_actual_start_request_rejects_blank_change_reason() -> None:
    with pytest.raises(ValueError, match="change reason"):
        _request(reason=" ")
