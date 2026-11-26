"""
File: test_registration_redis_acl_contract.py
Description: 以真實 Docker Redis 7 驗證 deploy/registration ACL 與 staging/maintenance 全生命週期契約。
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import time
from uuid import uuid4

import pytest
import redis
from redis.exceptions import AuthenticationError, ConnectionError as RedisConnectionError, NoPermissionError

from domains.case_import.provisional_registration import ProvisionalRegistrationCandidate
from infrastructure.redis.registration_maintenance import RegistrationAofMaintenance
from infrastructure.redis.registration_staging_repository import RedisRegistrationStagingRepository
from infrastructure.redis.staff_profile_change_staging import StaffProfileChangeStaging
from shared_kernel.fingerprints import fingerprint_payload

ROOT = Path(__file__).resolve().parents[7]
REDIS_IMAGE = "redis:7-alpine@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499"


def _candidate(line_user_id: str, image_id: str) -> ProvisionalRegistrationCandidate:
    client_payload = {
        "line_user_id": line_user_id,
        "name": "真實Redis驗收",
        "phone": "0900000001",
        "address": "新竹市東區測試路1號",
        "expected_date": "2026-12-20",
        "service_days": 10,
        "passbook_image_id": image_id,
    }
    beclass_payload = {
        "name": "真實Redis驗收",
        "survey_details": {
            "特殊計費:胎數": "單胞胎",
            "代購食材": "自行準備",
            "_liff_meta": {"registration_kind": "non_citizen"},
        },
    }
    fp = fingerprint_payload({"client": client_payload, "beclass": beclass_payload})
    return ProvisionalRegistrationCandidate(line_user_id, client_payload, beclass_payload, fp)


def _start_disposable_redis(tmp_path: Path, admin_pw: str, intake_pw: str) -> tuple[str, int]:
    if shutil.which("docker") is None:
        pytest.fail("需要 Docker CLI 來執行真實 Redis 7 ACL 合約測試")
    secrets_dir = tmp_path / "secrets"
    data_dir = tmp_path / "data"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    (secrets_dir / "registration_admin_password").write_bytes(admin_pw.encode("utf-8"))
    (secrets_dir / "registration_intake_password").write_bytes(intake_pw.encode("utf-8"))

    conf = (ROOT / "deploy" / "registration" / "redis.conf").as_posix()
    entrypoint = (ROOT / "deploy" / "registration" / "redis-entrypoint.sh").as_posix()
    name = f"lu-test-reg-redis-acl-{uuid4().hex[:10]}"
    cmd = [
        "docker", "run", "-d", "--name", name,
        "-p", "127.0.0.1:0:6379",
        "-v", f"{conf}:/usr/local/etc/redis/redis.conf:ro",
        "-v", f"{entrypoint}:/entrypoint.sh:ro",
        "-v", f"{secrets_dir.as_posix()}:/run/secrets:ro",
        "-v", f"{data_dir.as_posix()}:/data",
        "--entrypoint", "/bin/sh",
        REDIS_IMAGE,
        "/entrypoint.sh", "redis-server", "/usr/local/etc/redis/redis.conf",
    ]
    run = subprocess.run(cmd, capture_output=True, text=True, check=True)
    cid = run.stdout.strip()
    try:
        mapped = subprocess.run(
            ["docker", "port", cid, "6379/tcp"],
            capture_output=True, text=True, check=True,
        ).stdout.strip().splitlines()[0]
        port = int(mapped.rsplit(":", 1)[-1])

        deadline = time.monotonic() + 15.0
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            probe = redis.Redis(host="127.0.0.1", port=port, username="registration-admin", password=admin_pw, decode_responses=True)
            try:
                if probe.ping():
                    probe.close()
                    return cid, port
            except (RedisConnectionError, AuthenticationError, NoPermissionError) as exc:
                last_error = exc
            finally:
                probe.close()
            time.sleep(0.2)
    except Exception:
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True, text=True)
        raise
    subprocess.run(["docker", "rm", "-f", cid], capture_output=True, text=True)
    raise AssertionError(f"Redis 7 ACL 測試容器未能就緒: {last_error}")


def test_real_redis_7_acl_supports_full_registration_and_staff_profile_lifecycles(tmp_path: Path) -> None:
    admin_pw = "AclAdminPass!2026"
    intake_pw = "AclIntakePass!2026"
    cid, port = _start_disposable_redis(tmp_path, admin_pw, intake_pw)

    admin_text = redis.Redis(host="127.0.0.1", port=port, username="registration-admin", password=admin_pw, decode_responses=True)
    intake_text = redis.Redis(host="127.0.0.1", port=port, username="registration-intake", password=intake_pw, decode_responses=True)
    anon_text = redis.Redis(host="127.0.0.1", port=port, decode_responses=True)
    try:
        admin_repo = RedisRegistrationStagingRepository(admin_text)
        intake_repo = RedisRegistrationStagingRepository(intake_text)

        # 1. 初始化與登記入件／審核／AOF 維護全流程
        admin_repo.initialize(0, new_empty_instance=True)
        image_meta = intake_repo.stage_passbook_image(
            line_user_id="U_ACL_APPROVE",
            filename="passbook.png",
            mime_type="image/png",
            content=b"\x89PNG\r\n\x1a\nacl-test-bytes",
        )
        loaded_meta, loaded_bytes = intake_repo.get_passbook_image(
            image_meta["passbook_image_id"], line_user_id="U_ACL_APPROVE"
        )
        assert loaded_meta["sha256"] == image_meta["sha256"]
        assert loaded_bytes == b"\x89PNG\r\n\x1a\nacl-test-bytes"

        sub_1 = str(uuid4())
        cand_1 = _candidate("U_ACL_APPROVE", image_meta["passbook_image_id"])
        snap_1 = intake_repo.submit(cand_1, sub_1)
        assert snap_1.status == "pending" and snap_1.replayed is False
        assert intake_repo.submit(cand_1, sub_1).replayed is True
        assert intake_repo.status_for_submission("U_ACL_APPROVE", sub_1).registration_id == snap_1.registration_id

        pending_list = admin_repo.pending(limit=10)
        assert [item.registration_id for item in pending_list] == [snap_1.registration_id]
        claimed_reg = admin_repo.claim_approval(snap_1.registration_id, 1, "admin-acl")
        assert claimed_reg.status == "approving"
        completed_reg = admin_repo.complete(
            snap_1.registration_id,
            claimed_reg.operation_id,
            {
                "client_id": 1001,
                "beclass_record_id": 2002,
                "case_no": "C-ACL-1",
                "approved_at_utc": "2026-11-26T00:00:00+00:00",
            },
        )
        assert completed_reg.status == "approved"
        maint_state = RegistrationAofMaintenance(admin_repo).run_once()
        assert maint_state in {"started", "running", "clean"}

        sub_2 = str(uuid4())
        image_meta_2 = intake_repo.stage_passbook_image(
            line_user_id="U_ACL_REJECT",
            filename="passbook2.png",
            mime_type="image/png",
            content=b"\x89PNG\r\n\x1a\nacl-test-reject",
        )
        snap_2 = intake_repo.submit(_candidate("U_ACL_REJECT", image_meta_2["passbook_image_id"]), sub_2)
        rejected_reg = admin_repo.reject(snap_2.registration_id, 1, "admin-acl")
        assert rejected_reg.status == "rejected"

        # 2. 月嫂個人資料變更暫存 (for_staff / pending / submit / update_web / decide / EXPIRE)
        profile_staging = StaffProfileChangeStaging(admin_text)
        assert profile_staging.for_staff(7) == []
        assert profile_staging.pending(0, 10) == ([], None)

        basis = {"version": 3, "phone": "0900000000"}
        p_sub_1 = str(uuid4())
        created = profile_staging.submit(
            7, p_sub_1, basis, {"phone": "0911111111"}, {"changed_fields": ["phone"]},
        )
        assert created["status"] == "pending" and created["version"] == 1
        assert profile_staging.find_submission(7, p_sub_1, basis)["id"] == created["id"]
        assert [item["id"] for item in profile_staging.for_staff(7)] == [created["id"]]
        pending_items, pending_next = profile_staging.pending(0, 10)
        assert [item["id"] for item in pending_items] == [created["id"]]
        assert pending_next is None

        updated = profile_staging.update_web(
            created["id"], 1, {"phone": "0922222222"}, {"changed_fields": ["phone"]},
        )
        assert updated["version"] == 2
        claimed_profile = profile_staging.decide(
            created["id"], "claim", version=2, actor="admin-acl", operation_id="op-prof-1",
        )
        assert claimed_profile["status"] == "approving"
        completed_profile = profile_staging.decide(
            created["id"], "complete", actor="admin-acl", operation_id="op-prof-1",
            content="", review='{"changed_fields": ["phone"]}',
        )
        assert completed_profile["status"] == "approved"
        assert profile_staging.pending(0, 10) == ([], None)

        p_sub_2 = str(uuid4())
        created_2 = profile_staging.submit(
            7, p_sub_2, basis, {"phone": "0933333333"}, {"changed_fields": ["phone"]},
        )
        rejected_profile = profile_staging.decide(
            created_2["id"], "reject", version=1, actor="admin-acl",
        )
        assert rejected_profile["status"] == "rejected"

        # 3. 最小權限負向邊界：未驗證、intake、越權指令、跨 key prefix 一律被拒絕
        with pytest.raises(AuthenticationError):
            anon_text.ping()
        with pytest.raises(NoPermissionError):
            intake_text.zrevrange("registration:staff-profile:staff:7", 0, -1)
        with pytest.raises(NoPermissionError):
            intake_text.delete("registration:ready")
        with pytest.raises(NoPermissionError):
            intake_text.info("persistence")
        with pytest.raises(NoPermissionError):
            intake_text.keys("*")
        with pytest.raises(NoPermissionError):
            admin_text.keys("*")
        with pytest.raises(NoPermissionError):
            admin_text.config_get("*")
        with pytest.raises(NoPermissionError):
            admin_text.set("other:key", "1")
        with pytest.raises(NoPermissionError):
            intake_text.set("other:key", "1")
    finally:
        anon_text.close()
        intake_text.close()
        admin_text.close()
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True, text=True)
