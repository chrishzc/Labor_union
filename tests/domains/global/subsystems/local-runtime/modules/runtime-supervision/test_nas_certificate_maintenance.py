"""Expiry, trust handover and interrupted certificate maintenance regressions."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import ssl
import socket
import threading
import os
import subprocess

import pytest
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from scripts.nas_certificate_maintenance import Certificates, MaintenanceError, Policy, _issued_by

ROOT = Path(__file__).resolve().parents[7]
NOW = datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture(autouse=True)
def windows_posix_fixture(monkeypatch):
    # Windows chmod(0400) sets a DOS read-only flag which blocks rename/unlink;
    # POSIX allows the directory owner to replace such files. Linux tests below
    # verify actual private-file modes/owners, without changing production code.
    if os.name == "nt":
        monkeypatch.setattr(Path, "chmod", lambda self, mode, **kwargs: None)


def legacy(mounts, group, services):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, group + " legacy")])
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(NOW - timedelta(days=1))
          .not_valid_after(NOW + timedelta(days=90)).add_extension(x509.BasicConstraints(True, 0), True)
          .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
          .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), False)
          .sign(key, hashes.SHA256()))
    def put(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    put(mounts / ("private-ca" if group == "api" else "db-ca") / "ca.pem", ca.public_bytes(serialization.Encoding.PEM))
    if group == "db":
        put(mounts / "server-tls/ca.pem", ca.public_bytes(serialization.Encoding.PEM))
    for name, host in services:
        leaf_key = ec.generate_private_key(ec.SECP256R1())
        names = [x509.DNSName(host)]
        if name == "management-tls":
            import ipaddress
            names += [x509.DNSName("admin.test.invalid"), x509.IPAddress(ipaddress.ip_address("192.168.1.100"))]
        cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)]))
                .issuer_name(ca.subject).public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(NOW - timedelta(days=1)).not_valid_after(NOW + timedelta(days=90))
                .add_extension(x509.SubjectAlternativeName(names), False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), False)
                .sign(key, hashes.SHA256()))
        put(mounts / name / "server-cert.pem", cert.public_bytes(serialization.Encoding.PEM))
        put(mounts / name / "server-key.pem", leaf_key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))


@pytest.fixture
def installation(tmp_path):
    mounts = tmp_path / "certificates"
    legacy(mounts, "api", [("management-tls", "management-api"), ("line-tls", "line-api")])
    legacy(mounts, "db", [("server-tls", "db")])
    return Certificates(tmp_path / "maintenance", mounts, now=NOW)


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def finish(job):
    job.prepare()
    job.trust()
    job.activate()
    return job.commit(verified=True)


def test_adopt_legacy_installation_preserves_other_data_and_identity(installation):
    job = installation
    business = job.root.parent / "business"
    business.mkdir()
    for name in ("root-account", "MFA-key", "DB-password", "worker-token", "resume", "baby-photo"):
        (business / name).write_text("retained-" + name)
    before = snapshot(business)
    original = job._load_leaf("management")
    result = finish(job)
    assert result == {"status": "committed", "groups": ["api", "db"]}
    assert snapshot(business) == before
    assert job.inspect()["managed"] is True
    assert job._load_leaf("management").extensions.get_extension_for_class(x509.SubjectAlternativeName) == original.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    assert job.targets["db-ca"].read_bytes() == job.targets["db-server-ca"].read_bytes()
    assert len(x509.load_pem_x509_certificates(job.targets["api-ca"].read_bytes())) == 2
    assert not (job.mounts / "private-ca/ca-key.pem").exists()


def test_not_due_is_zero_mutation(installation):
    finish(installation)
    before = snapshot(installation.root.parent)
    assert installation.prepare() == {"status": "unchanged"}
    assert snapshot(installation.root.parent) == before


def test_leaf_renewal_keeps_issuer_and_rotates_keys(installation):
    finish(installation)
    root = installation.root
    issuers = snapshot(root / "issuers")
    serial = installation.serial("db")
    job = Certificates(root, installation.mounts, now=NOW + timedelta(days=61))
    finish(job)
    assert snapshot(root / "issuers") == issuers
    assert job.serial("db") != serial
    assert job._load_leaf("db").not_valid_after_utc == NOW + timedelta(days=151)


def test_ca_rotation_trusts_both_before_changing_leaf(installation):
    finish(installation)
    old = installation._load_leaf("management")
    job = Certificates(installation.root, installation.mounts, now=NOW + timedelta(days=1650))
    job.prepare()
    job.trust()
    assert job.serial("management") == format(old.serial_number, "x")
    roots = x509.load_pem_x509_certificates(job.targets["api-ca"].read_bytes())
    assert len(roots) == 2
    assert any(_issued_by(old, ca) for ca in roots)
    job.activate()
    assert any(_issued_by(job._load_leaf("management"), ca) for ca in roots)
    job.commit(verified=True)
    assert job.inspect()["groups"]["api"]["rotate"] is False


def test_retire_old_trust_after_overlap_does_not_replace_leaf(installation):
    finish(installation)
    serial = installation.serial("management")
    job = Certificates(installation.root, installation.mounts, now=NOW + timedelta(days=31))
    finish(job)
    assert job.serial("management") == serial
    assert len(x509.load_pem_x509_certificates(job.targets["api-ca"].read_bytes())) == 1


def test_failed_activation_can_restore_exact_previous_certificate_files(installation):
    before = snapshot(installation.mounts)
    installation.prepare()
    installation.trust()
    installation.activate()
    assert snapshot(installation.mounts) != before
    assert installation.rollback() == {"status": "rolled_back"}
    assert snapshot(installation.mounts) == before
    assert not (installation.root / "state.json").exists()
    assert not (installation.root / "pending.json").exists()


def test_resume_does_not_generate_different_candidate_or_hide_missing_verification(installation):
    job = installation
    job.prepare()
    directory, _ = job._transaction()
    candidate = snapshot(directory / "candidate")
    job.trust()
    job.activate()
    resumed = Certificates(job.root, job.mounts, now=NOW)
    assert resumed.prepare() == {"status": "pending", "phase": "activated"}
    assert snapshot(directory / "candidate") == candidate
    with pytest.raises(MaintenanceError, match="verification_required"):
        resumed.commit()
    resumed.trust()
    resumed.activate()
    resumed.commit(verified=True)


def test_expired_certificates_recover_without_application_but_cannot_fake_rollback(installation):
    job = Certificates(installation.root, installation.mounts, now=NOW + timedelta(days=95))
    job.prepare()
    job.trust()
    job.activate()
    with pytest.raises(MaintenanceError, match="rollback_certificate_expired"):
        job.rollback()
    assert (job.root / "pending.json").exists()
    job.commit(verified=True)
    assert job._load_leaf("db").not_valid_after_utc > job.now


@pytest.mark.parametrize("days", [0, 95])
def test_partial_live_key_pair_replacement_resumes_even_after_legacy_ca_expires(installation, days):
    job = Certificates(installation.root, installation.mounts, now=NOW + timedelta(days=days))
    job.prepare(); job.trust()
    directory, _ = job._transaction()
    job._install("management-cert", (directory / "candidate/management-cert").read_bytes())
    with pytest.raises(MaintenanceError, match="invalid_existing_service_identity"):
        job._load_leaf("management")
    resumed = Certificates(job.root, job.mounts, now=job.now)
    assert resumed.prepare() == {"status": "pending", "phase": "trusted"}
    resumed.trust(); resumed.activate(); resumed.commit(verified=True)
    assert resumed.inspect()["managed"]
    assert resumed._load_leaf("management").not_valid_after_utc > resumed.now


def test_corrupt_candidate_does_not_modify_live_certificates(installation):
    job = installation
    before = snapshot(job.mounts)
    job.prepare()
    directory, _ = job._transaction()
    (directory / "candidate/management-key").write_bytes((directory / "candidate/line-key").read_bytes())
    with pytest.raises(MaintenanceError, match="invalid_candidate_certificate"):
        job.trust()
    assert snapshot(job.mounts) == before


def test_missing_managed_signer_is_not_silently_recreated(installation):
    finish(installation)
    (installation.root / "issuers/api/ca-key.pem").unlink()
    with pytest.raises(FileNotFoundError):
        installation.prepare()


def test_linux_private_signer_and_service_key_ownership(installation):
    if os.name == "nt":
        pytest.skip("actual POSIX mode/UID contract is exercised in the Linux run")
    import stat
    finish(installation)
    assert stat.S_IMODE(installation.root.stat().st_mode) == 0o700
    for group in ["api", "db"]:
        key = installation.root / "issuers" / group / "ca-key.pem"
        assert stat.S_IMODE(key.stat().st_mode) == 0o400
        assert key.stat().st_uid == 0
    assert installation.targets["db-key"].stat().st_uid == 999
    assert installation.targets["management-key"].stat().st_uid == 1000


@pytest.mark.parametrize("policy", [dict(renew_before_days=90), dict(rotate_before_days=89), dict(ca_days=90), dict(overlap_days=0)])
def test_invalid_policy_rejected(policy):
    with pytest.raises(MaintenanceError, match="invalid_certificate_policy"):
        Policy(**policy)


def test_actual_tls_accepts_old_and_new_during_handover_and_rejects_wrong_hostname(installation):
    job = installation
    old_cert = job.targets["management-cert"].read_bytes()
    old_key = job.targets["management-key"].read_bytes()
    job.prepare(); job.trust(); job.activate()
    context = ssl.create_default_context(cafile=str(job.targets["api-ca"]))
    def handshake(cert, key, hostname):
        temporary = job.root / "test-server"
        temporary.mkdir(exist_ok=True)
        (temporary / "cert.pem").write_bytes(cert)
        (temporary / "key.pem").write_bytes(key)
        server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server.load_cert_chain(str(temporary / "cert.pem"), str(temporary / "key.pem"))
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0)); listener.listen(1); listener.settimeout(5)
        port = listener.getsockname()[1]
        def serve():
            try:
                raw, _ = listener.accept()
                with raw:
                    with server.wrap_socket(raw, server_side=True) as stream:
                        stream.sendall(b"ok")
            except ssl.SSLError:
                pass  # Client correctly rejects the negative hostname control.
            finally:
                listener.close()
        thread = threading.Thread(target=serve)
        thread.start()
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
                with context.wrap_socket(raw, server_hostname=hostname) as stream:
                    assert stream.recv(2) == b"ok"
        finally:
            thread.join(timeout=6)
            assert not thread.is_alive()
    handshake(old_cert, old_key, "management-api")
    handshake(job.targets["management-cert"].read_bytes(), job.targets["management-key"].read_bytes(), "management-api")
    with pytest.raises(ssl.SSLCertVerificationError):
        handshake(job.targets["management-cert"].read_bytes(), job.targets["management-key"].read_bytes(), "wrong.invalid")


def test_maintenance_has_no_business_credentials_or_docker_socket_and_is_not_default():
    model = yaml.safe_load((ROOT / "deployment/nas/compose.yaml").read_text(encoding="utf-8"))
    service = model["services"]["certificate-maintenance"]
    assert service["profiles"] == ["certificates"]
    assert service["network_mode"] == "none" and service["restart"] == "no"
    mounts = service["volumes"]
    assert {m.split(":")[0] for m in mounts if isinstance(m, str)} == {
        "private-ca", "management-tls", "line-tls", "db-ca", "server-tls"}
    assert not any("docker.sock" in str(m) or "app-data" in str(m) or "mysql-data" in str(m) for m in mounts)
    assert "depends_on" not in service and "ports" not in service
    assert all("certificate-maintenance" not in s.get("depends_on", {}) for s in model["services"].values())


def test_coordinator_is_local_bounded_and_failure_still_notifies_after_rollback():
    text = (ROOT / "deployment/nas/maintain-certificates.sh").read_text(encoding="utf-8")
    assert "unix:///var/run/docker.sock" in text
    assert "flock -n" in text and "-k 30 600" in text
    assert "ALTER INSTANCE RELOAD TLS" in text
    assert "NO ROLLBACK ON ERROR" not in text
    assert 'exec -i --user "$uid"' in text
    recovery = text.split("on_failure()", 1)[1].split("trap on_failure", 1)[0]
    assert "exit 2" in recovery and "verify_live" in recovery


@pytest.fixture
def coordinator(tmp_path):
    if os.name == "nt":
        pytest.skip("DSM host coordinator is verified in the Linux test container")
    project = tmp_path / "project"
    project.mkdir()
    state = project / "certificate-maintenance"
    state.mkdir(mode=0o700)
    data = project / "storage"
    for name in ["app-data", "controlled-files", "line-media", "knowledge"]:
        (data / name).mkdir(parents=True)
    name = "lu-test-cert-coordinator"
    (project / ".env").write_text(f"COMPOSE_PROJECT_NAME={name}\nNAS_DATA_ROOT={data}\nNAS_IMAGE=fixture:local\n")
    (project / "compose.yaml").write_text("services: {}")
    (project / "nas_certificate_maintenance.py").write_text("# fixture input only")
    script = project / "maintain-certificates.sh"
    script.write_bytes((ROOT / "deployment/nas/maintain-certificates.sh").read_bytes())
    binary = tmp_path / "bin"
    binary.mkdir()
    fake = binary / "docker"
    fake.write_text('''#!/usr/bin/env python
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
assert args[:2]==['--host','unix:///var/run/docker.sock']
args=args[2:]
root=Path(os.environ['TEST_PROJECT'])
state=root/'certificate-maintenance'
name='lu-test-cert-coordinator'
with (root/'calls.jsonl').open('a') as stream: stream.write(json.dumps(args)+'\\n')
def injected(stage):
    marker=root/'failure-consumed'
    if stage=='probe' and os.environ.get('TEST_FAIL')=='probe' and not (root/'rolled-back').exists():
        sys.exit(2)
    if os.environ.get('TEST_FAIL')==stage and not marker.exists():
        marker.touch(); sys.exit(2)
if args[0]=='volume':
    print('wrong-owner' if os.environ.get('TEST_OWNER_FAIL') else name)
elif args[0]=='ps':
    container=next(a[7:-1] for a in args if a.startswith('name=^/'))
    if container in [name+'-db-1',name+'-management-api-1']: print(container)
elif args[0]=='inspect':
    if '.State.Status' in args[2]:
        if args[-1] in [name+'-db-1',name+'-management-api-1']: print('running')
        else: sys.exit(1)
    else:
        print(name+'/'+('management-api' if 'management-api' in args[-1] else 'db'))
elif args[0]=='compose':
    action=args[args.index('certificate-maintenance')+1]
    if action=='status': print('{"managed":false}')
    elif action=='prepare':
        (state/'pending.json').write_text('{}'); print('{"status":"prepared"}')
    elif action=='serial': print('abc123')
    elif action=='commit':
        (state/'pending.json').unlink(); print('{"status":"committed"}')
    elif action=='rollback':
        (state/'pending.json').unlink(); (root/'rolled-back').touch(); print('{"status":"rolled_back"}')
    else:
        injected(action); print(json.dumps({'status':action}))
elif args[0]=='exec':
    if 'probe' in args: sys.stdin.read(); injected('probe')
    else: injected('reload')
elif args[0]=='restart':
    assert args[-1]==name+'-management-api-1'
elif args[0]=='run':
    assert '--user' in args and args[args.index('--user')+1]=='1000:1000'
    assert not any('issuers' in a or 'docker.sock' in a for a in args)
else: raise AssertionError('unexpected Docker operation')
''', encoding="utf-8")
    fake.chmod(0o700)
    sleep = binary / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n")
    sleep.chmod(0o700)
    env = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"], "TEST_PROJECT": str(project)}
    def run(*, check=False, failure=None, wrong_owner=False):
        values = {**env}
        if failure: values["TEST_FAIL"] = failure
        if wrong_owner: values["TEST_OWNER_FAIL"] = "1"
        return subprocess.run(["/bin/bash", str(script), "--check" if check else "--apply"],
                              env=values, text=True, capture_output=True, timeout=20)
    return project, state, run


def test_coordinator_executes_only_its_project_and_preserves_disabled_services(coordinator):
    project, state, run = coordinator
    result = run()
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert '"status":"completed"' in result.stdout
    calls = [json.loads(line) for line in (project / "calls.jsonl").read_text().splitlines()]
    assert [a[-1] for a in calls if a[0] == "restart"] == ["lu-test-cert-coordinator-management-api-1"]
    assert all(a[0] not in {"stop", "rm", "prune", "system"} for a in calls)
    assert not (state / "pending.json").exists()


@pytest.mark.parametrize("failure", ["activate", "reload", "probe"])
def test_coordinator_rollback_keeps_nonzero_exit_for_DSM_notification(coordinator, failure):
    _, state, run = coordinator
    result = run(failure=failure)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert '"recovery":"verified_previous_certificates"' in result.stdout
    assert '"status":"completed"' not in result.stdout
    assert not (state / "pending.json").exists()


def test_coordinator_wrong_volume_owner_is_rejected_before_any_certificate_change(coordinator):
    project, state, run = coordinator
    result = run(wrong_owner=True)
    assert result.returncode == 2 and "certificate_volume_owner_mismatch" in result.stdout
    assert not (state / "pending.json").exists()
    calls = [json.loads(line) for line in (project / "calls.jsonl").read_text().splitlines()]
    assert not any(a[0] == "compose" for a in calls)


def test_coordinator_readonly_check_and_overlapping_job_lock(coordinator):
    import fcntl
    project, state, run = coordinator
    result = run(check=True)
    assert result.returncode == 0 and '"managed":false' in result.stdout
    assert not (state / "pending.json").exists()
    before = (project / "calls.jsonl").read_bytes()
    with (state / "task.lock").open("w") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = run()
        assert result.returncode == 2 and "maintenance_already_running" in result.stdout
    assert (project / "calls.jsonl").read_bytes() == before
