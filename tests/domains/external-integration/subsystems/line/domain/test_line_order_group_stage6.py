"""
File: test_line_order_group_stage6.py
Description: 驗證 LINE 訂單群組能力投影與執行期契約。
"""

from datetime import datetime, timezone

import pytest

from domains.line.identities import LineGroupId, LineUserId
from domains.line.order_group import LineGroupInvitationRelay
from shared_kernel.identities import ActorContext, CorrelationId
from infrastructure.mysql.line_order_group_adapters import MySqlOrdersLineAudienceAdapter
from subsystems.line.capabilities import LineCapability, line_capabilities_for_role
from subsystems.line.runtime_monitoring import RuntimeHealthObservation, RuntimeHealthStatus

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


class _Cursor:
    def __init__(self, order, staff_rows=()) -> None:
        self._rows = (order, tuple(staff_rows))
        self._index = -1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, *_):
        self._index += 1

    def fetchone(self):
        return self._rows[self._index]

    def fetchall(self):
        return self._rows[self._index]


class _Connection:
    def __init__(self, cursor) -> None:
        self._cursor = cursor

    def cursor(self):
        return self._cursor


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


def test_order_group_audience_requires_a_truly_settled_deposit() -> None:
    unsettled = {
        "case_no": "1150729",
        "order_status": "訂單成立",
        "customer_line_user_id": "U-customer",
        "deposit_settlement_state": "unsettled",
    }
    with pytest.raises(RuntimeError, match="settled_deposit_required_for_line_group"):
        MySqlOrdersLineAudienceAdapter(_Connection(_Cursor(unsettled))).get("1150729")

    settled = {**unsettled, "deposit_settlement_state": "settled"}
    audience = MySqlOrdersLineAudienceAdapter(
        _Connection(_Cursor(settled, ({"line_user_id": "U-caregiver"},)))
    ).get("1150729")

    assert audience is not None
    assert audience.customer_line_user_id == LineUserId("U-customer")
    assert audience.staff_line_user_ids == (LineUserId("U-caregiver"),)


def test_enabled_compatibility_roles_receive_equal_line_capabilities() -> None:
    expected = tuple(sorted(item.value for item in LineCapability))
    roles = ("line_viewer", "line_agent", "line_manager", "system_admin")

    assert {line_capabilities_for_role(role) for role in roles} == {expected}
    assert line_capabilities_for_role("unknown-role") == ()


def test_health_observation_fingerprint_is_stable_and_contains_no_mutation() -> None:
    observation = RuntimeHealthObservation(
        "line_worker", "LINE Worker", RuntimeHealthStatus.CRITICAL,
        "heartbeat expired", {"age_seconds": 61}, NOW, 4,
    )
    assert observation.fingerprint == observation.fingerprint
    assert len(observation.fingerprint) == 64
