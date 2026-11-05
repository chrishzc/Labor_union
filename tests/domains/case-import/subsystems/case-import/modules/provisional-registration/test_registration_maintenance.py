from types import SimpleNamespace

from subsystems.case_import.registration_maintenance import RegistrationMaintenanceRunner
from subsystems.case_import.registration_staging import RegistrationRecoveryResult


def test_sql_recovery_failure_does_not_block_expiry_or_hourly_aof_cleanup():
    calls = []
    clock = [0.0]
    def fail(**_):
        calls.append("recovery")
        raise RuntimeError("synthetic SQL unavailable")
    runner = RegistrationMaintenanceRunner(
        SimpleNamespace(expire_due=lambda **_: calls.append("expiry")),
        SimpleNamespace(recover=fail), SimpleNamespace(run_once=lambda: calls.append("rewrite")),
        monotonic=lambda: clock[0])
    assert not runner.tick() and calls == ["expiry", "recovery", "rewrite"]
    clock[0] = 3599
    assert not runner.tick() and calls.count("rewrite") == 1
    clock[0] = 3600
    assert not runner.tick() and calls.count("rewrite") == 2


def test_recovered_approval_reuses_original_worker_wakeup():
    calls = []
    runner = RegistrationMaintenanceRunner(SimpleNamespace(expire_due=lambda **_: None),
        SimpleNamespace(recover=lambda **_: RegistrationRecoveryResult(1, 0)),
        SimpleNamespace(run_once=lambda: None), after_recovery=lambda: calls.append("wake"))
    assert runner.tick() and calls == ["wake"]


def test_unconfigured_internal_lifecycle_leaves_other_features_available(monkeypatch):
    from api.dependencies.registration_runtime import registration_maintenance_runtime
    monkeypatch.delenv("REGISTRATION_REDIS_ADMIN_PASSWORD_FILE", raising=False)
    with registration_maintenance_runtime():
        pass
