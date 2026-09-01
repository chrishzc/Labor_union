"""Development-only LINE notification baseline fixture producer.

The fixture uses the existing notification owner source-event ingress.  It never
creates a business decision or calls a provider; the repository only creates
durable source, decision, intent, and delivery-task projections.
"""

from __future__ import annotations

import re
import hashlib
import json
from datetime import datetime, timezone
from typing import Callable

from shared_kernel.identities import ActorContext
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.notification_policy import NotificationSourceEvent


_TARGET = re.compile(r"^lu_test_[a-z0-9_]+$")
_FIXTURE_DOMAIN = "line_task96_fixture"
_FIXTURE_ACTOR = "system:line-task96-baseline"

_BASELINE = (
    ("LU96-M1-GATEWAY-RETRY-FAIL-SOURCE-V1", "gateway.identity_mismatch.second_attempt", "customer_service.ticket_owner"),
    ("LU96-M1-LEAVE-EXTENSION-SOURCE-V1", "scheduling.leave.extension_requested", "client.bound_case"),
    ("LU96-M1-STAFF-RETIRE-SOURCE-V1", "staff.retirement.committed", "staff.binding_owner"),
    ("LU96-M2-ROUTER-REPLY-SOURCE-V1", "router.deterministic.reply_committed", "conversation.bound_actor"),
    ("LU96-M2-FEEDBACK-UNRESOLVED-SOURCE-V1", "feedback.unresolved.recorded", "customer_service.ticket_owner"),
    ("LU96-M3-ZERO-POOL-SOURCE-V1", "matching.zero_pool.preview_applied", "matching.request.participants"),
    ("LU96-M3-MATCH-SUCCESS-CLIENT-SOURCE-V1", "matching.decision.committed.client", "assignment.client_snapshot"),
    ("LU96-M3-MATCH-SUCCESS-STAFF-SOURCE-V1", "matching.decision.committed.staff", "assignment.staff_snapshot"),
    ("LU96-M3-LEAVE-AGREE-SOURCE-V1", "client.leave.extension_agreed", "scheduling.owner"),
    ("LU96-M3-LEAVE-DISAGREE-SOURCE-V1", "client.leave.extension_rejected", "customer_service.ticket_owner"),
    ("LU96-M4-SAFE-ALERT-SOURCE-V1", "runtime.alert.review_required", "admin.review_actor"),
    ("LU96-M4-COMPLAINT-HIGH-SOURCE-V1", "complaint.ingress.hold_high_ticket", "customer_service.claim_owner"),
    ("LU96-M4-SALARY-PAYABLE-SOURCE-V1", "payroll.substitute.obligation_projected", "staff_payables.anomaly_owner"),
)


def baseline_identities() -> tuple[tuple[str, str, str], ...]:
    """Return the immutable source identity, trigger, and selector contract."""
    return _BASELINE


def build_baseline_events(
    *,
    target_database: str,
    occurred_at: datetime | None = None,
) -> tuple[NotificationSourceEvent, ...]:
    """Build synthetic owner envelopes without business-root mutations."""
    _require_fixture_target(target_database)
    when = occurred_at or datetime.now(timezone.utc)
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError("notification baseline occurred_at must be timezone-aware")
    events = []
    for index, (source_identity, trigger, selector) in enumerate(_BASELINE, start=1):
        case_no = f"LU96-P0-{index:02d}"
        source_digest = hashlib.sha256(
            json.dumps(
                {
                    "identity": source_identity,
                    "trigger_kind": trigger,
                    "recipient_selector": selector,
                    "source_subject": f"task96:{source_identity}",
                    "producer_reference": "fixture:task96-line14-p0",
                    "contract_revision": 1,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        events.append(
            NotificationSourceEvent(
                identity=source_identity,
                event_code=trigger,
                historical_silent=False,
                facts={
                    "case_no": case_no,
                    "source_subject": f"task96:{source_identity}",
                    "trigger_kind": trigger,
                    "producer_reference": "fixture:task96-line14-p0",
                    "contract_revision": 1,
                    "source_digest": source_digest,
                    "recipient_projection": {
                        "selector": selector,
                        "type": "user",
                        "identity": f"lu_test_line96_recipient_{index:02d}",
                    },
                },
                source_domain=_FIXTURE_DOMAIN,
                source_aggregate_type="line_notification_baseline",
                source_aggregate_identity=f"task96-line14-p0:{index:02d}",
                source_version=1,
                occurred_at=when,
            )
        )
    return tuple(events)


def bootstrap_notification_baseline(
    unit_of_work_factory: Callable[[], object],
    *,
    target_database: str,
    actor: ActorContext,
    occurred_at: datetime | None = None,
) -> tuple[int, ...]:
    """Persist the baseline exactly once per immutable source identity."""
    _require_fixture_target(target_database)
    if actor.actor_id != _FIXTURE_ACTOR:
        raise PermissionError("notification baseline requires its development-only actor")
    require_line_capability(actor, LineCapability.CONFIG_MANAGE)
    with unit_of_work_factory() as unit_of_work:
        source_ids = tuple(
            unit_of_work.notification_rules.register_and_project(event)
            for event in build_baseline_events(
                target_database=target_database,
                occurred_at=occurred_at,
            )
        )
        unit_of_work.commit()
    return source_ids


def _require_fixture_target(target_database: str) -> None:
    if not isinstance(target_database, str) or _TARGET.fullmatch(target_database) is None:
        raise ValueError("notification baseline requires an explicitly named lu_test_* database")


__all__ = [
    "baseline_identities",
    "bootstrap_notification_baseline",
    "build_baseline_events",
]
