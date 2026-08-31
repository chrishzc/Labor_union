"""Regression contracts for shared primitives used across multiple domains."""

from datetime import datetime, timedelta, timezone

import pytest

from shared_kernel.business_time import current_business_instant
from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from shared_kernel.ttl_cache import CacheTelemetry, TtlProjectionCache


def test_money_ntd_keeps_integer_only_contract_and_arithmetic():
    assert MoneyNTD(100) + MoneyNTD(25) == MoneyNTD(125)
    assert MoneyNTD(100) - MoneyNTD(125) == MoneyNTD(-25)
    assert MoneyNTD(25) * 4 == MoneyNTD(100)
    assert -MoneyNTD(25) == MoneyNTD(-25)
    assert MoneyNTD(0).is_zero is True
    assert MoneyNTD(1).is_zero is False

    for invalid in (True, False, 1.0, "1", None):
        with pytest.raises(TypeError, match="integer"):
            MoneyNTD(invalid)

    with pytest.raises(TypeError):
        _ = MoneyNTD(1) + 1
    with pytest.raises(TypeError):
        _ = MoneyNTD(1) * True


def test_fingerprint_payload_is_canonical_across_key_order_and_sequence_types():
    left = fingerprint_payload(
        {
            "case_id": "案件-001",
            "version": 3,
            "flags": [True, None],
            "nested": {"b": 2, "a": 1},
        }
    )
    right = fingerprint_payload(
        {
            "nested": {"a": 1, "b": 2},
            "flags": (True, None),
            "version": 3,
            "case_id": "案件-001",
        }
    )

    assert left == right
    assert len(left.value) == 64
    assert left.value == left.value.lower()


def test_fingerprint_payload_rejects_noncanonical_values_and_keys():
    with pytest.raises(TypeError, match="keys must be strings"):
        fingerprint_payload({"nested": {1: "value"}})
    with pytest.raises(TypeError, match="non-canonical value"):
        fingerprint_payload({"amount": 1.5})
    with pytest.raises(TypeError, match="non-canonical value"):
        fingerprint_payload({"items": {"a", "b"}})


def test_business_time_requires_utc_and_converts_to_taipei():
    instant = datetime(2026, 8, 31, 16, 30, tzinfo=timezone.utc)

    business_time = current_business_instant(instant)

    assert business_time.tzinfo == TAIPEI_TIME_ZONE
    assert business_time == datetime(2026, 9, 1, 0, 30, tzinfo=TAIPEI_TIME_ZONE)

    with pytest.raises(ValueError, match="timezone-aware"):
        current_business_instant(datetime(2026, 8, 31, 16, 30))
    with pytest.raises(ValueError, match="UTC offset"):
        current_business_instant(
            datetime(
                2026,
                8,
                31,
                16,
                30,
                tzinfo=timezone(timedelta(hours=8)),
            )
        )
    with pytest.raises(TypeError, match="aware UTC datetime"):
        current_business_instant("2026-08-31T16:30:00Z")


def test_fixed_business_clock_normalizes_to_taipei_and_uses_local_date():
    clock = FixedBusinessClock(datetime(2026, 8, 31, 16, 30, tzinfo=timezone.utc))

    assert clock.now() == datetime(2026, 9, 1, 0, 30, tzinfo=TAIPEI_TIME_ZONE)
    assert clock.today().isoformat() == "2026-09-01"

    with pytest.raises(ValueError, match="timezone-aware"):
        FixedBusinessClock(datetime(2026, 8, 31, 16, 30))


def test_ttl_projection_cache_is_copy_safe_and_reports_cache_activity(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("shared_kernel.ttl_cache.monotonic", lambda: now[0])
    cache = TtlProjectionCache[dict[str, list[int]]](ttl_seconds=10)
    loads = []

    def loader():
        loads.append("load")
        return {"items": [1]}

    first = cache.get_or_load("case-1", loader)
    first["items"].append(99)
    second = cache.get_or_load("case-1", loader)

    assert second == {"items": [1]}
    assert loads == ["load"]
    assert cache.telemetry() == CacheTelemetry(1, 1, 1, 0)

    now[0] = 111.0
    assert cache.get_or_load("case-1", loader) == {"items": [1]}
    assert loads == ["load", "load"]
    assert cache.telemetry() == CacheTelemetry(1, 2, 2, 0)

    cache.invalidate("case-1")
    cache.invalidate("case-1")
    assert cache.telemetry() == CacheTelemetry(1, 2, 2, 1)


def test_ttl_projection_cache_validates_configuration_and_key():
    with pytest.raises(ValueError, match="positive"):
        TtlProjectionCache(0)

    cache = TtlProjectionCache[int](1)
    with pytest.raises(ValueError, match="cache key"):
        cache.get_or_load("   ", lambda: 1)


def test_command_identity_values_reject_ambiguous_or_noncanonical_input():
    assert ActorContext(
        "operator-1",
        ("finance.read", "orders.write"),
    ).permission_scope == ("finance.read", "orders.write")
    assert ExpectedVersion(0).value == 0
    assert IdempotencyKey("order-123:cancel:v1").value == "order-123:cancel:v1"

    with pytest.raises(ValueError, match="sorted and unique"):
        ActorContext("operator-1", ("orders.write", "finance.read"))
    with pytest.raises(ValueError, match="sorted and unique"):
        ActorContext("operator-1", ("orders.write", "orders.write"))
    with pytest.raises(TypeError, match="tuple"):
        ActorContext("operator-1", ["orders.write"])
    with pytest.raises(ValueError, match="nonnegative integer"):
        ExpectedVersion(True)
    with pytest.raises(ValueError, match="canonical non-empty text"):
        IdempotencyKey(" key-with-whitespace ")


def test_typed_error_only_allows_retryable_unavailable_and_canonical_blockers():
    correlation_id = CorrelationId("corr-001")
    unavailable = TypedError(
        ErrorCategory.UNAVAILABLE,
        "provider_unavailable",
        "provider is temporarily unavailable",
        correlation_id,
        retryable=True,
    )

    assert unavailable.retryable is True

    with pytest.raises(ValueError, match="only unavailable"):
        TypedError(
            ErrorCategory.CONFLICT,
            "version_conflict",
            "version conflict",
            correlation_id,
            retryable=True,
        )
    with pytest.raises(ValueError, match="sorted and unique"):
        TypedError(
            ErrorCategory.DOMAIN_BLOCKED,
            "blocked",
            "blocked by current facts",
            correlation_id,
            domain_blockers=("orders", "finance"),
        )
