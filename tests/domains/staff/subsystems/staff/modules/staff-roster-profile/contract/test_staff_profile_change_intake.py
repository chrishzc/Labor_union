from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
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
    monkeypatch.setattr(route, "_bound_staff_id", lambda body: 8 if body.line_id_token == "other-staff" else 7)
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
        original = {"submission_id": payload["submission_id"]}
        status_url = f"{intake}/submission-status"
        assert client.post(status_url, json=original).json()["data"] == {"status": "not_received"}
        submitted = client.post(f"{intake}/submit", json=payload)
        assert submitted.status_code == 200
        receipt = submitted.json()["data"]
        assert receipt["status"] == "pending" and not writes
        assert set(receipt) == {"id", "status", "version"}
        assert client.post(status_url, json=original).json()["data"] == receipt
        assert client.post(status_url, json={**original, "line_id_token": "other-staff"}).json()["data"] == {"status": "not_received"}
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
        assert client.post(status_url, json=original).json()["data"]["status"] == "approved"
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


def test_query_form_translates_missing_redis_configuration_to_typed_503(monkeypatch):
    from api.exception_handlers import install_typed_error_handlers
    from infrastructure.redis.registration_connection import RegistrationRedisConfigurationError

    @contextmanager
    def application():
        yield (
            SimpleNamespace(form=lambda staff_id: {"basis": {"version": 1}}),
            SimpleNamespace(load=lambda staff_id, lock=False: SimpleNamespace(state=StaffLifecycleState.ACTIVE)),
        )

    def missing_staging():
        raise RegistrationRedisConfigurationError("missing registration redis password")

    monkeypatch.setattr(route, "staff_profile_change_application", application)
    monkeypatch.setattr(route, "staff_profile_change_staging", missing_staging)
    monkeypatch.setattr(route, "_bound_staff_id", lambda body: 7)
    app = FastAPI()
    install_typed_error_handlers(app)
    app.include_router(route.router)
    with TestClient(app) as client:
        for path, body in (("query", {}), ("submission-status", {"submission_id": str(uuid4())})):
            response = client.post(f"/api/v1/line/staff-self-service/profile-change/{path}", json=body)
            assert response.status_code == 503
            assert response.json()["detail"]["error"]["code"] == "staff_profile_change_unavailable"



@pytest.mark.parametrize("scenario", ["receipt-lost", "not-received", "known-conflict", "lost-reopen", "absent-reopen"])
def test_liff_submission_recovery_in_browser(scenario):
    from playwright.sync_api import expect, sync_playwright

    from api.routes.line_identity import page_router

    app = FastAPI()
    app.include_router(page_router)
    origin = "https://staff-profile-receipt.example.test"
    root = next(path for path in Path(__file__).resolve().parents if (path / "line" / "static").is_dir())
    photo_script = (root / "line/static/staff_profile_web_photos.js").read_text(encoding="utf-8")
    prefix = "/api/v1/line/staff-self-service/profile-change"
    form_data = {
        "basis": {"profile": 0, "bank": 0, "relations": "a" * 64, "transportation": "b" * 64, "matching": 0},
        "profile": {"phone": "0900000000"}, "relations": {},
    }
    receipt = {"id": 17, "status": "pending", "version": 1}
    submissions = []
    statuses = []

    with TestClient(app) as client, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()

        def handle(request):
            url = request.request.url
            if url == f"{origin}/line-staff-profile-update":
                document = client.get("/line-staff-profile-update")
                request.fulfill(status=document.status_code, body=document.text, content_type="text/html; charset=utf-8")
            elif url.endswith("/sdk.js"):
                request.fulfill(content_type="text/javascript", body=(
                    'window.liff = {init: async () => {}, isLoggedIn: () => true, getIDToken: () => "fixture-token"};'
                ))
            elif url == f"{origin}/static/staff_profile_web_photos.js":
                request.fulfill(content_type="text/javascript", body=photo_script)
            elif url == f"{origin}/api/v1/line/identity/runtime-config":
                request.fulfill(json={"data": {"liff_id": "fixture"}})
            elif url == f"{origin}{prefix}/query":
                request.fulfill(json={"data": form_data})
            elif url == f"{origin}{prefix}/submit":
                submissions.append(request.request.post_data_json)
                if len(submissions) > 1:
                    request.fulfill(json={"data": receipt})
                elif scenario == "known-conflict":
                    request.fulfill(status=409, json={"detail": {"error": {"code": "staff_profile_change_stale"}}})
                elif scenario == "not-received":
                    request.fulfill(json={"data": {**receipt, "id": 0}})
                else:
                    request.abort()
            elif url == f"{origin}{prefix}/submission-status":
                statuses.append(request.request.post_data_json)
                if scenario == "not-received" and len(statuses) == 1:
                    request.fulfill(status=503, json={"detail": {"error": {"code": "staff_profile_change_unavailable"}}})
                elif scenario in {"known-conflict", "not-received"} or (
                    scenario == "absent-reopen" and len(statuses) == 1
                ):
                    request.fulfill(json={"data": {"status": "not_received"}})
                else:
                    request.fulfill(json={"data": receipt})
            else:
                request.abort()

        page.route("**/*", handle)
        page.goto(f"{origin}/line-staff-profile-update")
        phone = page.locator("#phone")
        recovery = page.locator("#submission-recovery")
        status = page.locator("#status")
        phone.fill("0911111111")
        page.locator("#send").click()
        expect(recovery).to_be_visible()
        expect(page.locator("#send")).to_be_disabled()
        expect(phone).to_have_value("0911111111")
        assert len(submissions) == 1
        submission_id = submissions[0]["submission_id"]
        saved = page.evaluate("Object.values(sessionStorage)")
        assert saved and set(saved) == {submission_id}

        if scenario in {"lost-reopen", "absent-reopen"}:
            page.reload()
        else:
            expect(recovery).to_have_text("查詢原申請" if scenario == "known-conflict" else "重新送出")
            recovery.click()

        if scenario == "not-received":
            expect(status).to_contain_text("尚未確認送件成功")
            expect(recovery).to_be_enabled()
            assert len(submissions) == 1
            recovery.click()

        if scenario == "absent-reopen":
            expect(status).to_contain_text("原填寫資料已無法復原")
            expect(page.locator("#form")).to_be_hidden()
            expect(page.locator("#send")).to_be_disabled()
            expect(recovery).to_have_text("查詢原申請")
            expect(recovery).to_be_enabled()
            assert len(submissions) == 1
            assert page.evaluate("Object.values(sessionStorage)") == [submission_id]
            recovery.click()

        if scenario == "known-conflict":
            expect(status).to_contain_text("本次申請未送出")
            expect(recovery).to_be_hidden()
            expect(page.locator("#send")).to_be_disabled()
            page.reload()
            expect(status).to_contain_text("本次申請未送出")
            expect(page.locator("#form")).to_be_hidden()
        else:
            expect(status).to_have_text("申請 #17，待工會審核")
            expect(page.locator("#form")).to_be_hidden()
            assert page.evaluate("Object.values(sessionStorage)") == []

        assert len(submissions) == (2 if scenario == "not-received" else 1)
        assert all(submission == submissions[0] for submission in submissions)
        assert statuses == [{"line_id_token": "fixture-token", "submission_id": submission_id}] * (
            2 if scenario in {"known-conflict", "not-received", "absent-reopen"} else 1
        )
        browser.close()
