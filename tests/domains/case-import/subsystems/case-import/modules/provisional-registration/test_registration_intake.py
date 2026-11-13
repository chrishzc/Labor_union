"""
File: test_registration_intake.py
Description: 驗證公開登記收件容器邊界與胎數閉鎖輸入之 422 拒收行為。
"""
import ast
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.registration_intake import app, get_staging, get_verifier
from domains.line.identities import LineUserId


def test_intake_import_closure_cannot_load_sql_or_app_settings():
    source = """
import importlib.abc, sys
class BlockSql(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname.startswith(('infrastructure.mysql','pymysql','mysql','sqlalchemy','api.main','api.nas_apps','config.settings')):
   raise AssertionError('SQL dependency crossed intake boundary')
sys.meta_path.insert(0,BlockSql())
import api.registration_intake
assert all('approve' not in r.path and 'reject' not in r.path for r in api.registration_intake.app.routes)
"""
    result = subprocess.run([sys.executable, "-B", "-c", source], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_intake_validation_does_not_echo_questionnaire_or_tokens():
    app.dependency_overrides[get_staging] = lambda: object()
    app.dependency_overrides[get_verifier] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/line/identity/registration/apply", json={"line_id_token": "synthetic-private-token",
                "refund_account_no": "synthetic-private-account"})
        assert response.status_code == 422
        assert "synthetic-private" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_preview_uses_verified_subject_and_never_opens_staging_or_sql():
    def read_only_get_passbook(image_id, *, line_user_id=None):
        assert image_id == "pbk_synthetic_preview"
        assert line_user_id == "U-verified-synthetic"
        return ({"passbook_image_id": image_id}, b"img")
    def no_write(*_args, **_kwargs):
        raise AssertionError("Preview is zero write")
    app.dependency_overrides[get_staging] = lambda: SimpleNamespace(
        get_passbook_image=read_only_get_passbook,
        submit=no_write,
        stage_passbook_image=no_write,
    )
    app.dependency_overrides[get_verifier] = lambda: SimpleNamespace(verify=lambda _: SimpleNamespace(line_user_id=LineUserId("U-verified-synthetic")))
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/line/identity/registration/preview", json={
                "line_id_token": "synthetic-token", "name": "合成申請", "phone": "0900000000",
                "address": "合成地址", "service_days": 10, "expected_date": "2026-11-20",
                "passbook_image_id": "pbk_synthetic_preview",
                "survey_details": {"特殊計費:胎數": "單胞胎"}})
            assert response.status_code == 200
            assert response.json()["data"]["expected_binding_version"] == 0
            bad = client.post("/api/v1/line/identity/registration/preview", json={
                "line_id_token": "synthetic-token", "name": "合成申請", "phone": "0900000000",
                "address": "合成地址", "service_days": 10, "expected_date": "2026-11-20",
                "passbook_image_id": "pbk_synthetic_preview",
                "survey_details": {"特殊計費:胎數": "第一胎"}})
            assert bad.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_old_public_registration_routes_cannot_reach_sql():
    from api.routes.line_identity import public_router
    assert not any("/registration/" in route.path for route in public_router.routes)
    tree = ast.parse(Path("line/line_bot.py").read_text(encoding="utf-8"))
    handler = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "line_register")
    assert len(handler.body) == 1 and isinstance(handler.body[0], ast.Raise)


def test_public_container_has_no_mysql_settings_or_network_egress():
    import yaml
    config = yaml.safe_load(Path("docker-compose.registration.yml").read_text(encoding="utf-8"))
    intake = config["services"]["registration-intake"]
    assert not any(key.startswith(("DB_", "MYSQL")) for key in intake["environment"])
    assert all(config["networks"][key].get("internal") is True for key in intake["networks"])
    assert "ports" not in config["services"]["registration-redis"]
    image_source = Path("deploy/registration/Dockerfile").read_text(encoding="utf-8")
    assert "COPY infrastructure/mysql" not in image_source
    assert "COPY api/main.py" not in image_source


def test_registration_deployment_multipart_proxy_and_minimal_redis_acl():
    reqs = Path("deploy/registration/requirements.txt").read_text(encoding="utf-8")
    assert any(line.strip().startswith("python-multipart==") for line in reqs.splitlines())

    proxy = Path("deploy/registration/proxy-location.conf").read_text(encoding="utf-8")
    assert "location = /api/v1/line/identity/registration/passbook" in proxy
    assert "client_max_body_size 6m;" in proxy
    assert "client_max_body_size 300k;" in proxy

    acl_script = Path("deploy/registration/redis-entrypoint.sh").read_text(encoding="utf-8")
    intake_line = next(line for line in acl_script.splitlines() if line.startswith("user registration-intake "))
    assert "+pexpireat" in intake_line
    assert "%RW~registration:passbook:meta:*" in intake_line
    assert "%RW~registration:passbook:data:*" in intake_line
    assert "%RW~registration:*" not in intake_line
    assert "registration:decision:*" not in intake_line
    assert "+del" not in intake_line
    assert "+persist" not in intake_line


def test_passbook_upload_size_limits_magic_bytes_and_cross_user_isolation():
    from datetime import datetime, timezone
    staged_images = {}

    class _Staging:
        def stage_passbook_image(self, *, line_user_id, filename, mime_type, content):
            image_id = f"pbk_{len(staged_images) + 1:08d}"
            staged_images[image_id] = ({"passbook_image_id": image_id, "line_user_id": line_user_id,
                                        "filename": filename, "mime_type": mime_type, "size_bytes": len(content)}, content)
            return staged_images[image_id][0]

        def get_passbook_image(self, image_id, *, line_user_id=None):
            entry = staged_images.get(image_id)
            if not entry:
                return None
            meta, content = entry
            if line_user_id is not None and meta["line_user_id"] != line_user_id:
                return None
            return meta, content

    current_user = {"id": "U-owner-A"}
    app.dependency_overrides[get_staging] = lambda: _Staging()
    app.dependency_overrides[get_verifier] = lambda: SimpleNamespace(
        verify=lambda _: SimpleNamespace(line_user_id=LineUserId(current_user["id"]))
    )
    png_header = b"\x89PNG\r\n\x1a\n"
    try:
        with TestClient(app) as client:
            near_limit = png_header + b"0" * (5 * 1024 * 1024 - len(png_header) - 64)
            ok = client.post(
                "/api/v1/line/identity/registration/passbook",
                data={"line_id_token": "synthetic-token"},
                files={"file": ("passbook.png", near_limit, "image/png")},
            )
            assert ok.status_code == 200
            image_id = ok.json()["data"]["passbook_image_id"]

            oversized = png_header + b"0" * (5 * 1024 * 1024 + 1)
            too_big = client.post(
                "/api/v1/line/identity/registration/passbook",
                data={"line_id_token": "synthetic-token"},
                files={"file": ("too_big.png", oversized, "image/png")},
            )
            assert too_big.status_code in {413, 422}

            invalid_magic = client.post(
                "/api/v1/line/identity/registration/passbook",
                data={"line_id_token": "synthetic-token"},
                files={"file": ("fake.jpg", b"<svg>not-an-image</svg>", "image/jpeg")},
            )
            assert invalid_magic.status_code == 422

            # Other registration endpoints keep the tighter 300 KB body limit.
            oversized_preview = client.post(
                "/api/v1/line/identity/registration/preview",
                content=b"{" + b" " * (301 * 1024) + b"}",
                headers={"Content-Type": "application/json"},
            )
            assert oversized_preview.status_code == 413

            # Another LINE user cannot bind User A's passbook image.
            current_user["id"] = "U-other-B"
            cross_user = client.post(
                "/api/v1/line/identity/registration/preview",
                json={
                    "line_id_token": "synthetic-token", "name": "跨帳號測試", "phone": "0900000000",
                    "address": "合成地址", "service_days": 10, "expected_date": "2026-11-20",
                    "passbook_image_id": image_id,
                    "survey_details": {"特殊計費:胎數": "單胞胎"},
                },
            )
            assert cross_user.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_redis_passbook_atomic_stage_ttl_sync_and_fail_closed_recovery():
    from datetime import datetime, timezone
    import json
    from domains.case_import.provisional_registration import ProvisionalRegistrationCandidate
    from infrastructure.redis.registration_staging_repository import RedisRegistrationStagingRepository, _STAGE_PASSBOOK, _SUBMIT, _DECIDE, _COMPLETE
    from shared_kernel.fingerprints import PreviewFingerprint
    from shared_kernel.identities import CorrelationId
    from subsystems.case_import.provisional_registration_types import ProvisionalRegistrationStorageError
    from subsystems.case_import.registration_staging import RegistrationReviewApplication, StagedRegistration

    # 1. Verify Redis repository passes passbook keys to atomic Lua scripts.
    eval_calls = []

    class _FakeRedis:
        def __init__(self):
            self.kv = {"registration:ready": "1", "registration:counter": "2"}

        def get(self, key):
            return self.kv.get(key)

        def eval(self, script, numkeys, *keys_and_args):
            keys = list(keys_and_args[:numkeys])
            args = list(keys_and_args[numkeys:])
            eval_calls.append((script, keys, args))
            if script is _STAGE_PASSBOOK:
                self.kv[keys[0]] = args[0]
                self.kv[keys[1]] = args[1]
                return ["staged"]
            if script is _SUBMIT:
                return ["created", "2"]
            if script is _DECIDE:
                return ["approving"]
            if script is _COMPLETE:
                return ["approved"]
            return ["ok"]

    fake = _FakeRedis()
    repo = RedisRegistrationStagingRepository(fake, now_ms=lambda: 1_700_000_000_000)
    staged_meta = repo.stage_passbook_image(line_user_id="U-1", filename="p.png", mime_type="image/png", content=b"\x89PNG\r\n\x1a\n123")
    image_id = staged_meta["passbook_image_id"]
    assert eval_calls[-1][0] is _STAGE_PASSBOOK
    assert f"registration:passbook:meta:{image_id}" in eval_calls[-1][1]
    assert f"registration:passbook:data:{image_id}" in eval_calls[-1][1]

    fake.kv["registration:meta:2"] = json.dumps({
        "registration_id": 2, "subject": staged_meta["subject"],
        "fingerprint": "a" * 64, "submitted_ms": 1_700_000_000_000,
        "expires_ms": 1_700_000_100_000, "registration_kind": "citizen_registration",
    })
    fake.kv["registration:content:2"] = json.dumps({
        "client": {"line_user_id": "U-1", "passbook_image_id": image_id},
        "beclass": {"survey_details": {"_liff_meta": {"passbook_image_id": image_id}}},
    })
    assert f"registration:passbook:meta:{image_id}" in repo._passbook_keys_for_registration(2)

    # 2. Verify fail-closed approval when passbook is missing or archiver fails, and idempotent recovery.
    class _WorkflowStaging:
        def __init__(self, has_image=True):
            self.status = "pending"
            self.has_image = has_image
            self.deleted = False
            self.completed = False
            self.candidate = ProvisionalRegistrationCandidate(
                "U-1",
                {"line_user_id": "U-1", "passbook_image_id": image_id},
                {"survey_details": {"_liff_meta": {"passbook_image_id": image_id}}},
                PreviewFingerprint("a" * 64),
            )

        def _snap(self):
            return StagedRegistration(
                2, 1 if self.status == "pending" else 2, self.status,
                datetime.now(timezone.utc), datetime.now(timezone.utc),
                "citizen_registration", self.candidate, "op-1", "admin-1",
            )

        def claim_approval(self, registration_id, expected_version, actor):
            self.status = "approving"
            return self._snap()

        def get(self, registration_id):
            return self._snap()

        def processing_ids(self, *, limit=100):
            return (2,) if self.status == "approving" else ()

        def get_passbook_image(self, req_id):
            return ({"filename": "p.png", "mime_type": "image/png"}, b"img") if self.has_image else None

        def delete_passbook_image(self, req_id):
            self.deleted = True

        def complete(self, registration_id, operation_id, receipt):
            self.completed = True
            self.status = "approved"
            return self._snap()

    class _Formal:
        def __init__(self):
            self.create_calls = 0
            self.receipt = None

        def approve_staged_registration(self, snapshot, correlation_id):
            self.create_calls += 1
            self.receipt = {"client_id": 501, "beclass_record_id": 601, "case_no": None,
                            "approved_at_utc": datetime.now(timezone.utc).isoformat()}
            return self.receipt

        def registration_approval_receipt(self, registration_id, operation_id):
            return self.receipt

    # Missing passbook image -> must fail closed and NOT mark approved.
    missing_staging = _WorkflowStaging(has_image=False)
    app_missing = RegistrationReviewApplication(missing_staging, _Formal(), passbook_archiver=lambda **_: None)
    import pytest
    with pytest.raises(ProvisionalRegistrationStorageError, match="registration_passbook_image_missing"):
        app_missing.approve_registration(2, 1, "admin-1", CorrelationId("corr-1"))
    assert missing_staging.status == "approving"
    assert not missing_staging.completed

    # Archiver failure (NAS down) -> preserves approving & temp image; retry via recover() succeeds without duplicate client.
    flaky_staging = _WorkflowStaging(has_image=True)
    formal = _Formal()
    should_fail = {"flag": True}

    def _archiver(**_kwargs):
        if should_fail["flag"]:
            raise ProvisionalRegistrationStorageError("controlled_file_storage_unavailable")

    app_flaky = RegistrationReviewApplication(flaky_staging, formal, passbook_archiver=_archiver)
    with pytest.raises(ProvisionalRegistrationStorageError, match="controlled_file_storage_unavailable"):
        app_flaky.approve_registration(2, 1, "admin-1", CorrelationId("corr-2"))
    assert flaky_staging.status == "approving"
    assert not flaky_staging.completed
    assert not flaky_staging.deleted
    assert formal.create_calls == 1

    should_fail["flag"] = False
    recovery = app_flaky.recover()
    assert (recovery.recovered, recovery.failed) == (1, 0)
    assert flaky_staging.status == "approved"
    assert flaky_staging.completed
    assert flaky_staging.deleted
    assert formal.create_calls == 1
