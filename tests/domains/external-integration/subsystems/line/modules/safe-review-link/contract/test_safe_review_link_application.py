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
    def __init__(self, repo): self.safe_review_links = repo
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def commit(self): pass


def _factory(repo): return lambda: FakeUnitOfWork(repo)


def _actor(name="admin:1"): return ActorContext(name, ("line.alert.manage",))


def _issue(key="issue-1", now=None):
    return IssueSafeReviewLink("link-1", "opaque-token-123456", "/api/v1/runtime/health-status", 3,
        "alert:1", "admin:1", "line.alert.manage", 60, _actor(), IdempotencyKey(key), CorrelationId("corr-1"))


def test_issue_persists_digest_and_redeem_is_one_time():
    repo = FakeRepository(); now = datetime.now(timezone.utc)
    app = SafeReviewLinkApplication(_factory(repo), lambda: now)
    receipt, token = app.issue(_issue())
    assert token == "opaque-token-123456"
    assert repo.links["link-1"]["token_digest"] != token
    redeemed = app.redeem(RedeemSafeReviewLink("link-1", token, _actor(), "line.alert.manage",
        "/api/v1/runtime/health-status", 3, IdempotencyKey("redeem-1"), CorrelationId("corr-2")))
    assert redeemed.outcome.value == "redeemed"
    with pytest.raises(SafeReviewLinkError, match="already redeemed"):
        app.redeem(RedeemSafeReviewLink("link-1", token, _actor(), "line.alert.manage",
            "/api/v1/runtime/health-status", 3, IdempotencyKey("redeem-2"), CorrelationId("corr-3")))


def test_wrong_actor_and_stale_target_fail_without_transition():
    repo = FakeRepository(); now = datetime.now(timezone.utc)
    app = SafeReviewLinkApplication(_factory(repo), lambda: now)
    app.issue(_issue())
    with pytest.raises(SafeReviewLinkError, match="not allowed"):
        app.redeem(RedeemSafeReviewLink("link-1", "opaque-token-123456", _actor("admin:2"), "line.alert.manage",
            "/api/v1/runtime/health-status", 3, IdempotencyKey("redeem-wrong"), CorrelationId("corr-2")))
    with pytest.raises(SafeReviewLinkError, match="stale"):
        app.redeem(RedeemSafeReviewLink("link-1", "opaque-token-123456", _actor(), "line.alert.manage",
            "/api/v1/runtime/other", 3, IdempotencyKey("redeem-stale"), CorrelationId("corr-3")))
    assert repo.links["link-1"]["status"] == "issued"


def test_expiry_revocation_version_conflict_and_idempotent_issue_are_closed():
    repo = FakeRepository()
    clock = [datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)]
    app = SafeReviewLinkApplication(_factory(repo), lambda: clock[0])

    first, token = app.issue(replace(_issue(), ttl_seconds=1))
    replay, replay_token = app.issue(replace(_issue(), ttl_seconds=1))
    assert first.outcome.value == "issued"
    assert replay.replayed is True
    assert replay_token == ""

    clock[0] += timedelta(seconds=2)
    with pytest.raises(SafeReviewLinkError) as expired:
        app.redeem(RedeemSafeReviewLink(
            "link-1", token, _actor(), "line.alert.manage",
            "/api/v1/runtime/health-status", 3,
            IdempotencyKey("redeem-expired"), CorrelationId("corr-expired"),
        ))
    assert expired.value.code == "safe_review_link_expired"
    assert repo.links["link-1"]["status"] == "expired"
    assert repo.events[-1][1][0] == "expired"

    repo = FakeRepository()
    clock[0] = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
    app = SafeReviewLinkApplication(_factory(repo), lambda: clock[0])
    app.issue(_issue())
    revoked = app.revoke(RevokeSafeReviewLink(
        "link-1", _actor(), "人工撤銷", IdempotencyKey("revoke-1"), CorrelationId("corr-revoke"),
    ))
    assert revoked.outcome.value == "revoked"
    assert repo.links["link-1"]["status"] == "revoked"
    with pytest.raises(SafeReviewLinkError) as revoked_replay:
        app.redeem(RedeemSafeReviewLink(
            "link-1", "opaque-token-123456", _actor(), "line.alert.manage",
            "/api/v1/runtime/health-status", 3,
            IdempotencyKey("redeem-revoked"), CorrelationId("corr-revoked"),
        ))
    assert revoked_replay.value.code == "safe_review_link_revoked"

    repo = FakeRepository()
    app = SafeReviewLinkApplication(_factory(repo), lambda: clock[0])
    app.issue(_issue())
    with pytest.raises(SafeReviewLinkError) as version_conflict:
        app.redeem(RedeemSafeReviewLink(
            "link-1", "opaque-token-123456", _actor(), "line.alert.manage",
            "/api/v1/runtime/health-status", 4,
            IdempotencyKey("redeem-stale-version"), CorrelationId("corr-stale-version"),
        ))
    assert version_conflict.value.code == "safe_review_link_version_conflict"
    assert repo.links["link-1"]["status"] == "issued"
