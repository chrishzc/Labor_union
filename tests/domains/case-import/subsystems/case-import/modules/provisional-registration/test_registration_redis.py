"""
File: test_registration_redis.py
Description: 驗證專用 Redis 待審問卷儲存與並發冪等契約。
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
import os
from pathlib import Path
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from redis import Redis
from redis.exceptions import NoPermissionError

from domains.case_import.provisional_registration import ProvisionalRegistrationIntent, build_provisional_registration_candidate
from infrastructure.redis.registration_staging_repository import RedisRegistrationStagingRepository, PREFIX, RETENTION_MS
from subsystems.case_import.provisional_registration_types import ProvisionalRegistrationConflictError
from subsystems.case_import.registration_staging import RegistrationReviewApplication


pytestmark = pytest.mark.skipif(os.getenv("REGISTRATION_REDIS_TEST") != "1", reason="dedicated disposable Redis opt-in")


@pytest.fixture(scope="module")
def stores():
    assert os.environ.get("APP_ENV", "development") == "development"
    directory = Path(os.environ["REGISTRATION_REDIS_TEST_SECRET_DIR"])
    port = int(os.environ["REGISTRATION_REDIS_TEST_PORT"])
    assert port != 6379
    clients = {role: Redis(host="127.0.0.1", port=port, username=f"registration-{role}",
        password=(directory / f"{role}.secret").read_text(encoding="ascii"), decode_responses=True,
        socket_timeout=3, socket_connect_timeout=3) for role in ("admin", "intake")}
    admin, intake = (RedisRegistrationStagingRepository(clients[role]) for role in ("admin", "intake"))
    admin.initialize(100, new_empty_instance=True)
    yield admin, intake
    for client in clients.values():
        client.close()


def candidate():
    return build_provisional_registration_candidate(ProvisionalRegistrationIntent(
        line_user_id="U-synthetic-" + uuid4().hex, name="合成待審申請", phone="0900000000",
        expected_date="2026-11-20", service_days=10, address="合成地址", gender=None,
        email=None, birth_date=None, tel=None, ext=None, city=None, zip_code=None,
        id_number=None, liff_config_revision=None,
        survey_details={"特殊計費:胎數": "單胞胎", "銀行帳號": "000012345678", "補助款退款:銀行代號+分行代號": "0000000"}))


def receipt():
    return {"client_id": 90001, "beclass_record_id": 90002, "case_no": None,
            "approved_at_utc": datetime.now(timezone.utc).isoformat()}


def test_submission_is_immutable_idempotent_and_retains_original_deadline(stores):
    admin, intake = stores
    value, key = candidate(), str(uuid4())
    first = intake.submit(value, key)
    second = intake.submit(value, key)
    assert first.registration_id == second.registration_id > 100
    assert not first.replayed and second.replayed
    alias = str(uuid4())
    assert intake.submit(value, alias).registration_id == first.registration_id
    assert intake.status_for_submission(value.line_user_id, alias).registration_id == first.registration_id
    assert first.submitted_at_utc == second.submitted_at_utc
    assert (first.expires_at_utc - first.submitted_at_utc).total_seconds() == 14 * 24 * 60 * 60
    loaded = admin.get(first.registration_id)
    assert loaded.candidate.payload_fingerprint == value.payload_fingerprint
    with pytest.raises(ProvisionalRegistrationConflictError):
        intake.submit(replace(value, payload_fingerprint=type(value.payload_fingerprint)("a" * 64)), key)
    admin.reject(first.registration_id, 1, "synthetic-admin")
    assert intake.submit(value, key).status == "rejected"
    # Only an explicitly new submission identifier starts another application.
    next_item = intake.submit(value, str(uuid4()))
    assert next_item.registration_id > first.registration_id
    admin.reject(next_item.registration_id, 1, "synthetic-admin")


def test_concurrent_submission_and_decision_have_one_winner(stores):
    admin, intake = stores
    value, key = candidate(), str(uuid4())
    with ThreadPoolExecutor(max_workers=4) as pool:
        submitted = list(pool.map(lambda _: intake.submit(value, key), range(4)))
    assert len({item.registration_id for item in submitted}) == 1
    registration_id = submitted[0].registration_id
    def decide(action):
        try:
            return (admin.claim_approval if action == "approve" else admin.reject)(registration_id, 1, "synthetic-admin").status
        except ProvisionalRegistrationConflictError:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, ["approve", "reject"]))
    assert results.count("conflict") == 1
    if "approving" in results:
        item = admin.get(registration_id)
        admin.complete(registration_id, item.operation_id, receipt())


def test_expiry_rejects_approval_and_removes_content_index_and_active_subject(stores):
    admin, intake = stores
    value, key = candidate(), str(uuid4())
    submitted = intake.submit(value, key)
    future = RedisRegistrationStagingRepository(admin.client, now_ms=lambda: int(submitted.expires_at_utc.timestamp() * 1000))
    with pytest.raises(ProvisionalRegistrationConflictError, match="expired"):
        future.claim_approval(submitted.registration_id, 1, "synthetic-admin")
    assert not admin.client.exists(PREFIX + f"content:{submitted.registration_id}")
    assert admin.get(submitted.registration_id).status == "expired"
    assert intake.submit(value, key).status == "expired"
    # Still no payload in the terminal view.
    assert admin.get(submitted.registration_id).candidate is None


def test_approval_claim_survives_deadline_until_verified_sql_commit(stores):
    admin, intake = stores
    submitted = intake.submit(candidate(), str(uuid4()))
    claimed = admin.claim_approval(submitted.registration_id, 1, "synthetic-admin")
    future = RedisRegistrationStagingRepository(admin.client, now_ms=lambda: int(submitted.expires_at_utc.timestamp() * 1000) + 1)
    recovered = future.claim_approval(submitted.registration_id, 2, "another-admin")
    assert recovered.status == "approving" and recovered.operation_id == claimed.operation_id
    assert recovered.actor == "synthetic-admin" and recovered.candidate is not None
    with pytest.raises(ProvisionalRegistrationConflictError):
        future.reject(submitted.registration_id, 2, "another-admin")
    result = future.complete(submitted.registration_id, claimed.operation_id, receipt())
    assert result.status == "approved" and result.candidate is None
    assert not admin.client.exists(PREFIX + f"content:{submitted.registration_id}")
    assert submitted.registration_id not in admin.processing_ids()


def test_sql_committed_cleanup_failure_only_replays_original_receipt(stores):
    admin, intake = stores
    submitted = intake.submit(candidate(), str(uuid4()))
    claimed = admin.claim_approval(submitted.registration_id, 1, "synthetic-admin")
    saved = receipt()
    class Formal:
        def registration_approval_receipt(self, registration_id, operation_id):
            assert (registration_id, operation_id) == (submitted.registration_id, claimed.operation_id)
            return saved
        def approve_staged_registration(self, *_):
            pytest.fail("committed approval must not be created again")
    review = RegistrationReviewApplication(admin, Formal())
    readback = review.registration_application(submitted.registration_id)
    assert readback.status == "approving" and readback.client_id == saved["client_id"]
    assert admin.client.exists(PREFIX + f"content:{submitted.registration_id}")
    assert review.recover().recovered >= 1
    assert review.registration_application(submitted.registration_id).status == "approved"


def test_processing_before_commit_resumes_same_operation(stores):
    admin, intake = stores
    submitted = intake.submit(candidate(), str(uuid4()))
    claimed = admin.claim_approval(submitted.registration_id, 1, "synthetic-admin")
    class Formal:
        def registration_approval_receipt(self, *_): return None
        def approve_staged_registration(self, staged, _):
            assert staged.operation_id == claimed.operation_id and staged.actor == claimed.actor
            return receipt()
    assert RegistrationReviewApplication(admin, Formal()).recover().recovered >= 1
    assert admin.get(submitted.registration_id).status == "approved"


def test_public_acl_cannot_decide_read_private_decisions_or_delete_content(stores):
    admin, intake = stores
    submitted = intake.submit(candidate(), str(uuid4()))
    for operation in (
        lambda: intake.client.get(PREFIX + f"decision:{submitted.registration_id}"),
        lambda: intake.client.set(PREFIX + f"result:{submitted.registration_id}", "{}"),
        lambda: intake.client.delete(PREFIX + f"content:{submitted.registration_id}"),
        lambda: intake.client.execute_command("CONFIG", "SET", "appendonly", "no"),
        lambda: intake.client.execute_command("FLUSHDB"),
    ):
        with pytest.raises(NoPermissionError): operation()
    admin.reject(submitted.registration_id, 1, "synthetic-admin")


def test_default_user_is_disabled_even_with_internal_aof_replay_permissions(stores):
    from redis.exceptions import AuthenticationError
    port = int(os.environ["REGISTRATION_REDIS_TEST_PORT"])
    client = Redis(host="127.0.0.1", port=port, socket_connect_timeout=2, socket_timeout=2)
    try:
        with pytest.raises(AuthenticationError): client.ping()
    finally:
        client.close()


def test_incomplete_high_water_restore_fails_closed(stores):
    from subsystems.case_import.provisional_registration_types import ProvisionalRegistrationStorageError
    admin, intake = stores
    counter = admin.client.get(PREFIX + "counter")
    try:
        admin.client.delete(PREFIX + "counter")
        with pytest.raises(ProvisionalRegistrationStorageError): admin.initialize(100, new_empty_instance=True)
        with pytest.raises(ProvisionalRegistrationStorageError): intake.submit(candidate(), str(uuid4()))
    finally:
        # Test-only restoration of the exact prior counter on this disposable instance.
        admin.client.set(PREFIX + "counter", counter)


def test_unknown_acknowledgement_can_only_be_resolved_by_original_submission(stores):
    from redis.exceptions import TimeoutError
    from subsystems.case_import.provisional_registration_types import ProvisionalRegistrationStorageError
    admin, intake = stores
    value, key = candidate(), str(uuid4())
    def execute_then_timeout(*args):
        intake.client.eval(*args)
        raise TimeoutError("synthetic lost acknowledgement")
    unknown = RedisRegistrationStagingRepository(SimpleNamespace(eval=execute_then_timeout))
    with pytest.raises(ProvisionalRegistrationStorageError): unknown.submit(value, key)
    saved = intake.status_for_submission(value.line_user_id, key)
    assert saved.status == "pending"
    assert intake.submit(value, key).registration_id == saved.registration_id
    assert intake.status_for_submission("U-other-synthetic", key) is None
    admin.reject(saved.registration_id, 1, "synthetic-admin")


def test_configured_internal_host_starts_and_stops_durable_maintenance(stores, monkeypatch):
    from threading import Event
    from api.dependencies import line_identity, registration_applications
    from api.dependencies.registration_runtime import registration_maintenance_runtime
    admin, _ = stores
    assert admin.processing_ids() == ()
    started = Event()
    class Formal:
        def registration_id_high_water(self):
            started.set()
            return 100
        def registration_approval_receipt(self, *_): pytest.fail("no processing rows were seeded")
    monkeypatch.setenv("REGISTRATION_REDIS_ADMIN_PASSWORD_FILE", str(Path(os.environ["REGISTRATION_REDIS_TEST_SECRET_DIR"]) / "admin.secret"))
    monkeypatch.setenv("REGISTRATION_REDIS_HOST", "127.0.0.1")
    monkeypatch.setenv("REGISTRATION_REDIS_PORT", os.environ["REGISTRATION_REDIS_TEST_PORT"])
    monkeypatch.setattr(line_identity, "get_line_identity_application", lambda: Formal())
    monkeypatch.setattr(registration_applications, "get_line_identity_application", lambda: Formal())
    registration_applications.get_registration_review_application.cache_clear()
    registration_applications.get_registration_staging_repository.cache_clear()
    try:
        with registration_maintenance_runtime():
            assert started.wait(3)
    finally:
        registration_applications.get_registration_review_application.cache_clear()
        registration_applications.get_registration_staging_repository.cache_clear()


def test_redis_failure_never_falls_back_to_memory_or_sql():
    from redis.exceptions import ConnectionError
    from subsystems.case_import.provisional_registration_types import ProvisionalRegistrationStorageError
    broken = SimpleNamespace(eval=lambda *_: (_ for _ in ()).throw(ConnectionError("private command")))
    with pytest.raises(ProvisionalRegistrationStorageError, match="^registration_redis_unavailable$"):
        RedisRegistrationStagingRepository(broken).submit(candidate(), str(uuid4()))
