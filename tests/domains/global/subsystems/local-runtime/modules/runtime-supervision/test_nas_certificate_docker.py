"""Opt-in local, disposable MySQL/API certificate handover; never builds images."""
import importlib.util
import json
import os
from pathlib import Path
import time
import shlex
from uuid import uuid4

import pytest

HERE = Path(__file__).parent
ROOT = HERE.parents[6]
CORE = ROOT / "scripts/nas_certificate_maintenance.py"


@pytest.mark.skipif(os.getenv("NAS_CERT_DOCKER_TEST") != "1", reason="explicit local Docker opt-in required")
def test_mysql_tls_reload_api_authentication_and_certificate_rollback():
    spec = importlib.util.spec_from_file_location("nas_lifecycle_helpers", HERE / "test_nas_compose_lifecycle.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    docker = module.LocalDocker()
    identifier = uuid4().hex[:10]
    root = ROOT / "scratch" / ("nas-cert-docker-" + identifier)
    root.mkdir()
    source = module.IsolatedProject(docker, "lu-nas-life-cert-" + identifier, root / "project")
    state = root / "certificate-maintenance"
    state.mkdir()
    phases = []
    mounts = {"private-ca": "private-ca", "management-tls": "management-tls", "line-tls": "line-tls",
              "db-ca": "db-ca", "server-tls": "server-tls"}

    def helper(action, *args, short=False, rotate=False, fault=False):
        command = ["run", "--rm", "-i", "--network", "none", "--read-only", "--memory", "128m",
                   "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m", "--entrypoint", "python"]
        if short:
            command += ["-e", "NAS_CERT_LEAF_DAYS=2", "-e", "NAS_CERT_RENEW_BEFORE_DAYS=1"]
        if rotate:
            command += ["-e", "NAS_CERT_CA_DAYS=3650", "-e", "NAS_CERT_ROTATE_BEFORE_DAYS=2000"]
        for volume, target in mounts.items():
            command += ["--mount", f"type=volume,source={source.project}_{volume},target=/certificates/{target}"]
        command += ["--mount", f"type=bind,source={state},target=/maintenance", module.IMAGE, "-", action, *args]
        code = CORE.read_text(encoding="utf-8")
        if fault:
            code = "from pathlib import Path; Path('/certificates/server-tls/server-key.pem').write_bytes(b'injected-invalid-key')"
        result = docker.run(*command, source=code, success=False)
        assert result.returncode == 0, result.stdout
        return result.stdout.strip()

    def reload_db(success=True):
        result = docker.run("exec", source.container("db"), "bash", "-c",
            'mysql --defaults-extra-file=<(printf "[client]\\nuser=root\\npassword=%s\\n" "$(cat /run/mysql-secrets/root-password)") --protocol=SOCKET --execute="ALTER INSTANCE RELOAD TLS"',
            success=False)
        assert (result.returncode == 0) == success

    def restart_and_probe():
        docker.run("restart", "--time", "20", source.container("management-api"))
        for _ in range(60):
            if source.metadata("management-api")["health"] == "healthy":
                break
            time.sleep(1)
        else:
            pytest.fail("candidate API failed its strict TLS health check")
        for service, cli_service in [("management-api", "management"), ("db", "db")]:
            serial = helper("serial", "--service", cli_service)
            result = docker.run("exec", "-i", "--user", "0:0" if service == "db" else "1000:1000", source.container("management-api"),
                "python", "-", "probe", "--service", service, "--expected-serial", serial,
                source=CORE.read_text(encoding="utf-8"), success=False)
            assert result.returncode == 0, result.stdout

    # Same business/MFA/file oracle, with only intentionally rotated TLS files excluded.
    business_probe = (HERE / "nas_lifecycle_probe.py").read_text(encoding="utf-8").replace(
        "'/run/api-tls', '/run/private-ca', '/run/db-ca'", "")
    def business(action):
        result = docker.run("exec", "-i", "-e", "NAS_LIFECYCLE_FIXTURE=1", source.container("management-api"),
            "python", "-", action, source=business_probe, success=False)
        assert result.returncode == 0, result.stdout

    def passed(name):
        phases.append(name)
        print("PASS " + name, flush=True)

    try:
        source.up(); source.ready(); business("seed")
        passed("fresh isolated installation; real root/staff MFA and files")
        helper("prepare", "--apply", short=True)
        helper("trust", "--apply")
        helper("activate", "--apply")
        reload_db(); restart_and_probe()
        helper("commit", "--apply", "--verified")
        business("login")
        passed("adopt legacy CAs; MySQL reload; strict fresh DB/API TLS; persisted MFA login")
        helper("prepare", "--apply")
        helper("trust", "--apply"); helper("activate", "--apply")
        helper("status", fault=True)
        reload_db(success=False)
        helper("rollback", "--apply")
        reload_db(); restart_and_probe(); business("verify")
        passed("invalid MySQL candidate reload rejected; certificate rollback restores live service")
        helper("prepare", "--apply", rotate=True)
        helper("trust", "--apply"); helper("activate", "--apply")
        reload_db(); restart_and_probe()
        helper("commit", "--apply", "--verified")
        business("login")
        passed("new CA trust handover and retained business data/MFA/permissions")
        output = docker.run("run", "--rm", "--network", source.project + "_management-control", "--user", "1000:1000",
            "--read-only", "--memory", "128m", "--mount", f"type=volume,source={source.project}_durable-token,target=/run/worker,readonly",
            "--mount", f"type=volume,source={source.project}_private-ca,target=/run/private-ca,readonly",
            "-e", "INTERNAL_SERVICE_AUTH_MODE=nas_service_token", "-e", "INTERNAL_SERVICE_TOKEN_FILE=/run/worker/token",
            "-e", "INTERNAL_API_CA_FILE=/run/private-ca/ca.pem", "-e", "INTERNAL_API_BASE_URL=https://management-api:8443",
            module.IMAGE, "python", "-c", "from infrastructure.http.private_operations_client import PrivateOperationsClient; PrivateOperationsClient('durable-job-worker').check(); print('authenticated')")
        assert output.strip() == "authenticated"
        passed("unchanged Worker machine token authenticates through new private CA; no work cycle")
    finally:
        stopped = source.compose("stop", "--timeout", "30", success=False).returncode == 0
        (root / "result.json").write_text(json.dumps({"phases_passed": phases, "containers_stopped": stopped,
            "nas_accessed": False, "images_built_or_pushed": False, "project": source.project}, indent=2), encoding="utf-8")
        assert stopped


@pytest.mark.skipif(os.getenv("NAS_CERT_DOCKER_TEST") != "1", reason="explicit local Docker opt-in required")
def test_unprivileged_public_ca_writer_replaces_symlink_without_following_it(tmp_path):
    spec = importlib.util.spec_from_file_location("nas_lifecycle_writer_helpers", HERE / "test_nas_compose_lifecycle.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    docker = module.LocalDocker()
    public = tmp_path / "public"
    public.mkdir()
    (public / "api-ca.pem").write_text("public API CA")
    (public / "db-ca.pem").write_text("public DB CA")
    script = (ROOT / "deployment/nas/maintain-certificates.sh").read_text(encoding="utf-8")
    lexer = shlex.shlex(script.split('--entrypoint python "$IMAGE" -c ', 1)[1], posix=True)
    lexer.whitespace_split = True
    writer = next(lexer)
    code = '''import os
from pathlib import Path
assert os.getuid()==1000
Path('/outside/sentinel').write_text('unchanged')
Path('/data/management-api-ca.crt').symlink_to('/outside/sentinel')
''' + writer + '''
assert Path('/outside/sentinel').read_text()=='unchanged'
assert not Path('/data/management-api-ca.crt').is_symlink()
assert Path('/data/management-api-ca.crt').read_text()=='public API CA'
assert Path('/data/nas-ca.pem').read_text()=='public DB CA'
print('public copies preserved boundary')
'''
    output = docker.run("run", "--rm", "-i", "--network", "none", "--read-only", "--user", "1000:1000",
        "--memory", "64m", "--tmpfs", "/data:rw,noexec,nosuid,uid=1000,gid=1000,mode=0700,size=1m",
        "--tmpfs", "/outside:rw,noexec,nosuid,uid=1000,gid=1000,mode=0700,size=1m",
        "--mount", f"type=bind,source={public},target=/cas,readonly", module.IMAGE, "python", "-", source=code)
    assert output.strip() == "public copies preserved boundary"
