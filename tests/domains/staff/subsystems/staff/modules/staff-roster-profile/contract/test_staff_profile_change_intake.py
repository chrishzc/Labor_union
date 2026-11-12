from contextlib import contextmanager
from dataclasses import asdict
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis import Redis

from api.routes import notification_tasks, staff_profile_change as route
from domains.staff.retirement import StaffLifecycleState
from infrastructure.redis.staff_profile_change_staging import StaffProfileChangeStaging
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, ExpectedVersion
from subsystems.staff.profile_change_approval import VersionedChange


def test_liff_submission_and_review_with_disposable_redis(monkeypatch):
    port = os.getenv("STAFF_PROFILE_CHANGE_TEST_REDIS_PORT")
    if port is None:
        pytest.skip("requires a disposable Redis bound to localhost")
    assert int(port) != 6379
    redis = Redis(host="127.0.0.1", port=int(port), decode_responses=True, socket_connect_timeout=2)
    assert redis.ping()
    staging = StaffProfileChangeStaging(redis)
    basis = {"profile": 0, "bank": 0, "relations": "a" * 64, "transportation": "b" * 64, "matching": 0}
    writes = []
    actor = ActorContext("admin:fixture")
    synthetic_account = "0123456789"

    class Application:
        def form(self, staff_id):
            assert staff_id == 7
            return {"basis": basis}

        def prepare(self, staff_id, proposed, expected):
            assert staff_id == 7 and expected == basis
            contact = VersionedChange(proposed["profile"], ExpectedVersion(0), PreviewFingerprint("c" * 64))
            bank = VersionedChange(
                {**proposed["bank"], "operation": "replace", "account_id": 3},
                ExpectedVersion(0), PreviewFingerprint("d" * 64),
            )
            return {"profile": asdict(contact), "bank": asdict(bank)}, {
                "bank": {"before": {"account_last4": "0000"}, "after": {"account_last4": "6789"}},
            }

        def apply(self, change, operation, actor, reason):
            assert change.staff_id == 7
            assert change.bank.proposed["account_no"] == synthetic_account
            assert change.profile.proposed["phone"] == "0900000000"
            writes.append((operation, actor.actor_id))

    @contextmanager
    def application():
        def load(staff_id, *, lock):
            assert staff_id == 7 and not lock
            return SimpleNamespace(state=StaffLifecycleState.ACTIVE)

        yield Application(), SimpleNamespace(load=load)

    monkeypatch.setattr(route, "staff_profile_change_application", application)
    monkeypatch.setattr(route, "staff_profile_change_staging", lambda: staging)
    monkeypatch.setattr(route, "_bound_staff_id", lambda body: 7)
    monkeypatch.setattr(route, "admin_actor_context", lambda principal: actor)
    monkeypatch.setattr(notification_tasks, "admin_actor_context", lambda principal: actor)
    monkeypatch.setattr(notification_tasks, "staff_profile_change_staging", lambda: staging)
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.require_registry_writer] = lambda: object()
    with TestClient(app) as client:
        intake = "/api/v1/line/staff-self-service/profile-change"
        assert client.post(f"{intake}/query", json={}).json()["data"]["basis"] == basis
        payload = {
            "submission_id": str(uuid4()), "basis": basis, "profile": {"phone": "0900000000"},
            "bank": {"bank_code": "001", "branch_code": "0001", "account_no": synthetic_account},
        }
        submitted = client.post(f"{intake}/submit", json=payload)
        assert submitted.status_code == 200
        receipt = submitted.json()["data"]
        assert receipt["status"] == "pending" and not writes
        assert client.post(f"{intake}/submit", json=payload).json()["data"] == receipt
        notice = notification_tasks._read_source(notification_tasks.Source.STAFF_PROFILE, 0, None)
        assert any(item.reference_id == receipt["id"] for item in notice.items)
        assert synthetic_account not in notice.model_dump_json()
        review = f"/api/v1/admin/staff-profile-change-requests/{receipt['id']}"
        assert synthetic_account not in client.get(review).text
        decision = {"version": receipt["version"], "action": "approve"}
        assert client.post(f"{review}/decision", json=decision).json()["data"]["status"] == "approved"
        assert client.post(f"{review}/decision", json=decision).json()["data"]["status"] == "approved"
        assert len(writes) == 1
        assert "content" not in staging.get(receipt["id"])
        notice = notification_tasks._read_source(notification_tasks.Source.STAFF_PROFILE, 0, None)
        assert all(item.reference_id != receipt["id"] for item in notice.items)
        second = client.post(f"{intake}/submit", json={**payload, "submission_id": str(uuid4())}).json()["data"]
        rejected = client.post(f"/api/v1/admin/staff-profile-change-requests/{second['id']}/decision",
                               json={"version": second["version"], "action": "reject"})
        assert rejected.json()["data"]["status"] == "rejected"
        assert "content" not in staging.get(second["id"])
        assert len(writes) == 1
    redis.close()
