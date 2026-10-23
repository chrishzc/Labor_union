from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.safe_review_link_application import SafeReviewLinkApplication
from subsystems.line.safe_review_link_contracts import (
    IssueSafeReviewLink,
    RedeemSafeReviewLink,
    RevokeSafeReviewLink,
    SafeReviewLinkError,
)


class FakeRepository:
    def __init__(self):
        self.links = {}
        self.receipts = {}
        self.events = []
        self.outbox = []
        self.runtime_targets = [{
            "id": 1, "target_type": "group", "enabled": True,
            "minimum_status": "warning",
            "updated_at_utc": datetime(2026, 9, 1, tzinfo=timezone.utc),
        }]

    def find_active_group_targets(self, *, for_update):
        return tuple(dict(row) for row in self.runtime_targets if row["enabled"])

    def get_issued_runtime_target(self, link_pk):
        return next((args[-1].get("runtime_alert_target") for pk, args in self.events
                     if pk == link_pk and args[0] == "issued"), None)

    def get_link(self, link_id, *, for_update=False):
        row = self.links.get(link_id)
        return dict(row) if row else None

    def insert_link(self, **values):
        values["expires_at_utc"] = values.pop("expires_at")
        values["issued_at_utc"] = values.pop("issued_at")
        row = {"id": len(self.links) + 1, **values, "status": "issued", "root_version": 0,
               "redeemed_at_utc": None, "revoked_at_utc": None}
        self.links[values["link_id"]] = row
        return row["id"]

    def transition(self, link_pk, status, at):
        row = next(row for row in self.links.values() if row["id"] == link_pk)
        row["status"] = status
        row["root_version"] += 1
        if status == "redeemed": row["redeemed_at_utc"] = at
        if status == "revoked": row["revoked_at_utc"] = at

    def insert_event(self, link_pk, *args): self.events.append((link_pk, args))
    def insert_outbox(self, link_pk, *args): self.outbox.append((link_pk, args))
    def insert_receipt(self, key, fingerprint, outcome, result, link_pk):
        self.receipts[key] = {"idempotency_key": key, "command_fingerprint": fingerprint,
                              "outcome": outcome, "result_snapshot": result,
                              "link_id": next(k for k,v in self.links.items() if v["id"] == link_pk)}
    def load_receipt(self, key, *, for_update=False):
        row = self.receipts.get(key)
        return dict(row) if row else None


class FakeUnitOfWork:
    def __init__(self, repo):
        self.safe_review_links = repo
        self.runtime_monitor = repo
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def commit(self): pass


def _factory(repo): return lambda: FakeUnitOfWork(repo)


def _actor(name="admin:1"): return ActorContext(name, ("line.alert.manage",))


def _issue(key="issue-1", now=None):
    return IssueSafeReviewLink("link-1", "opaque-token-123456", "/api/v1/runtime/health-status", 3,
        "alert:1", "admin:1", "line.alert.manage", 60, _actor(), IdempotencyKey(key), CorrelationId("corr-1"))


@pytest.mark.parametrize("existing", [False, True])
def test_group_link_issue_and_redeem_are_retired_without_writes(existing):
    repo = FakeRepository()
    if existing:
        repo.receipts["issue-1"] = {"historical": "receipt"}
    def forbidden():
        pytest.fail("retired operations must not open a writer or read historical tokens")
    app = SafeReviewLinkApplication(forbidden, lambda: datetime.now(timezone.utc))
    commands = [lambda: app.issue(_issue()), lambda: app.redeem(RedeemSafeReviewLink(
        "link-1", "opaque-token-123456", _actor(), "line.alert.manage", "/api/v1/runtime/health-status", 3,
        IdempotencyKey("redeem-1"), CorrelationId("corr-2")))]
    for operation in commands:
        with pytest.raises(SafeReviewLinkError) as error:
            operation()
        assert error.value.code == "line_alert_group_retired"
    assert not repo.links and not repo.events and not repo.outbox


def test_historical_group_link_can_still_be_revoked_and_queried():
    from subsystems.line.safe_review_link_contracts import QuerySafeReviewLink
    from hashlib import sha256
    repo = FakeRepository(); now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    repo.insert_link(link_id="link-1", token_digest=sha256(b"historical").hexdigest(),
        canonical_internal_target="/api/v1/runtime/health-status", target_version=3, source_alert_identity="alert:1",
        allowed_actor_ref="admin:1", required_capability="line.alert.manage", issued_at=now,
        expires_at=now+timedelta(seconds=60), idempotency_key="historical", correlation_id="historical")
    app = SafeReviewLinkApplication(_factory(repo), lambda: now)
    result = app.revoke(RevokeSafeReviewLink("link-1", _actor(), "撤銷歷史連結", IdempotencyKey("revoke-1"), CorrelationId("revoke")))
    assert result.outcome.value == "revoked"
    assert app.query(QuerySafeReviewLink("link-1")).status.value == "revoked"
    replay = app.revoke(RevokeSafeReviewLink("link-1", _actor(), "撤銷歷史連結", IdempotencyKey("revoke-1"), CorrelationId("revoke")))
    assert replay.replayed
