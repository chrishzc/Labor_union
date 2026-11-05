"""Crash/restart and native AOF rewrite evidence for the exact disposable Redis container."""
from importlib import import_module
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

import pytest
from redis.exceptions import RedisError

from infrastructure.redis.registration_maintenance import RegistrationAofMaintenance
import infrastructure.redis.registration_staging_repository as staging_module

_source = import_module("tests.domains.case-import.subsystems.case-import.modules.provisional-registration.test_registration_redis")
stores = _source.stores
candidate = _source.candidate
PREFIX = staging_module.PREFIX
pytestmark = pytest.mark.skipif(os.getenv("REGISTRATION_REDIS_DURABILITY_TEST") != "1", reason="exact disposable Docker instance required")


def container():
    name = os.environ["REGISTRATION_REDIS_TEST_CONTAINER"]
    assert name == "lu-test-registration-20261105"
    identity = subprocess.check_output(["docker", "inspect", name, "--format", "{{.Id}}"], text=True).strip()
    assert identity == os.environ["REGISTRATION_REDIS_TEST_CONTAINER_ID"]
    return name


def wait_ready(admin):
    for _ in range(50):
        try:
            if admin.client.ping(): return
        except RedisError:
            pass
        time.sleep(0.1)
    pytest.fail("disposable Redis did not restart")


def test_acknowledged_pending_and_high_water_survive_ungraceful_restart(stores):
    admin, intake = stores
    name = container()
    value, key = candidate(), str(uuid4())
    first = intake.submit(value, key)
    subprocess.run(["docker", "kill", "--signal", "KILL", name], check=True, capture_output=True)
    subprocess.run(["docker", "start", name], check=True, capture_output=True)
    wait_ready(admin)
    after = admin.get(first.registration_id)
    assert after.status == "pending" and after.expires_at_utc == first.expires_at_utc
    assert after.candidate.payload_fingerprint == value.payload_fingerprint
    assert int(admin.client.get(PREFIX + "counter")) >= first.registration_id
    assert intake.submit(value, key).registration_id == first.registration_id
    admin.reject(first.registration_id, 1, "synthetic-admin")


def test_native_ttl_deletes_content_and_query_marks_deadline_even_before_worker(stores, monkeypatch):
    admin, intake = stores
    assert staging_module.RETENTION_MS == 14 * 24 * 60 * 60 * 1000
    monkeypatch.setattr(staging_module, "RETENTION_MS", 1200)
    submitted = intake.submit(candidate(), str(uuid4()))
    time.sleep(1.3)
    assert not admin.client.exists(PREFIX + f"content:{submitted.registration_id}")
    assert admin.get(submitted.registration_id).status == "expired"
    assert admin.expire_due() >= 1


def test_small_deletion_batch_is_removed_from_native_aof_after_maintenance(stores, tmp_path):
    admin, intake = stores
    name = container()
    value = candidate()
    submitted = intake.submit(value, str(uuid4()))
    admin.reject(submitted.registration_id, 1, "synthetic-admin")
    maintenance = RegistrationAofMaintenance(admin)
    assert maintenance.run_once() in {"started", "running"}
    # Deletion after the captured generation must not be marked complete by the first rewrite.
    another = intake.submit(candidate(), str(uuid4()))
    admin.reject(another.registration_id, 1, "synthetic-admin")
    for _ in range(100):
        result = maintenance.run_once()
        if result == "clean": break
        time.sleep(0.1)
    assert result == "clean"
    assert int(admin.client.get(PREFIX + "maintenance:completed-generation")) == int(admin.client.get(PREFIX + "deletion-generation"))
    destination = tmp_path / "native-aof"
    subprocess.run(["docker", "cp", f"{name}:/data/appendonlydir", str(destination)], check=True, capture_output=True)
    marker = value.line_user_id.encode("utf-8")
    assert all(marker not in path.read_bytes() for path in destination.iterdir() if path.is_file())
    assert maintenance.run_once() == "clean"
