"""Stage 6 order-group invitation and runtime health domain contracts."""

from datetime import datetime, timezone

import pytest

from domains.line.identities import LineGroupId, LineUserId
from domains.line.order_group import LineGroupInvitationRelay
from shared_kernel.identities import ActorContext, CorrelationId
from subsystems.line.capabilities import LineCapability, line_capabilities_for_role
from subsystems.line.runtime_monitoring import RuntimeHealthObservation, RuntimeHealthStatus

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def test_invitation_accepts_only_clean_line_group_url_and_never_repr_leaks_secret() -> None:
    relay = LineGroupInvitationRelay(
        "1150729",
        LineGroupId("C-group"),
        "https://line.me/R/ti/g/example",
        (LineUserId("U-customer"),),
        ActorContext("admin:1", (LineCapability.ORDER_GROUP_BIND.value,)),
        CorrelationId("correlation-1"),
    )
    assert "https://" not in repr(relay)
    assert len(relay.invitation_fingerprint.value) == 64

    with pytest.raises(ValueError):
        LineGroupInvitationRelay(
            "1150729", LineGroupId("C-group"), "https://example.com/invite",
            (LineUserId("U-customer"),), relay.actor, relay.correlation_id,
        )


def test_operational_read_and_group_capabilities_are_role_scoped() -> None:
    viewer = line_capabilities_for_role("line_viewer")
    agent = line_capabilities_for_role("line_agent")
    assert LineCapability.MONITOR_READ.value in viewer
    assert LineCapability.ORDER_GROUP_READ.value in viewer
    assert LineCapability.ORDER_GROUP_BIND.value not in viewer
    assert LineCapability.ORDER_GROUP_BIND.value in agent
    assert LineCapability.ALERT_MANAGE.value not in agent


def test_health_observation_fingerprint_is_stable_and_contains_no_mutation() -> None:
    observation = RuntimeHealthObservation(
        "line_worker", "LINE Worker", RuntimeHealthStatus.CRITICAL,
        "heartbeat expired", {"age_seconds": 61}, NOW, 4,
    )
    assert observation.fingerprint == observation.fingerprint
    assert len(observation.fingerprint) == 64
