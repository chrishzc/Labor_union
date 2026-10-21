"""Online SQL snapshot, private permanent archives and failed-job isolation."""
import gzip
import importlib.util
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[7]
SCRIPT = ROOT / "deployment/nas/backup-database.sh"
DB_SCRIPT = SCRIPT.read_text(encoding="utf-8").split("<<'DB_SCRIPT'\n", 1)[1].split("\nDB_SCRIPT\n", 1)[0]


@pytest.fixture
def host(tmp_path, monkeypatch):
    if os.name == "nt" or os.getuid() != 0:
        pytest.skip("DSM host contract runs in Linux as root")
    project = tmp_path / "project"
    project.mkdir()
    script = project / "backup-database.sh"
    script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    (project / ".env").write_text("COMPOSE_PROJECT_NAME=lu-nas-life-backup\nUNUSED=$(touch SHOULD_NOT_EXIST)\n")
    destination = tmp_path / "archives"
    destination.mkdir(mode=0o700)
    tools = tmp_path / "tools"
    tools.mkdir()
    fake = tools / "docker"
    fake.write_text("""#!/usr/bin/env python3
import os, sys, time
a = sys.argv[3:]
with open(os.environ['DOCKER_TRACE'], 'a') as out: out.write(a[0]+'\\n')
if a[0] == 'ps': print('fixture-id')
elif a[0] == 'volume': print('wrong' if os.getenv('FAULT') == 'owner' else 'lu-nas-life-backup')
elif a[0] == 'inspect':
    fmt = a[2]
    if 'State.Status' in fmt: print('lu-nas-life-backup|db|running')
    elif '.Name' in fmt: print('lu-nas-life-backup_mysql-data')
    else: print(os.environ['MOUNT_SOURCE'])
elif a[0] == 'exec':
    sys.stdin.read()
    if a[-1] == 'check':
        print('BAD_ENGINE' if os.getenv('FAULT') == 'engine' else 'INNODB_OK')
        print('database=lu_test_fixture')
    else:
        print('-- synthetic SQL; no real data')
        if os.getenv('FAULT') == 'dump': sys.exit(7)
        if os.getenv('FAULT') == 'timeout': time.sleep(10)
        if os.getenv('FAULT') != 'truncated': print('-- Dump completed on 2026-10-20')
else: sys.exit(90)
""", encoding="utf-8")
    fake.chmod(0o700)
    monkeypatch.setenv("PATH", str(tools) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("DOCKER_TRACE", str(tmp_path / "trace"))
    monkeypatch.setenv("MOUNT_SOURCE", str(project))

    def run(mode="--backup", limit=20):
        return subprocess.run(["bash", str(script), mode, "--backup-dir", str(destination),
                               "--timeout-seconds", str(limit)], capture_output=True, text=True, timeout=limit + 15)
    return destination, project, run


def test_host_snapshot_is_private_complete_permanent_and_does_not_stop_services(host):
    destination, project, run = host
    old = destination / "old-permanent.sql.gz"
    old.write_bytes(b"old backup")
    assert run("--check").returncode == 0
    assert not list(destination.glob("*/COMPLETE"))
    result = run()
    assert result.returncode == 0, result.stdout
    archive = next(destination.glob("*/COMPLETE")).parent
    assert "Dump completed" in gzip.decompress((archive / "database.sql.gz").read_bytes()).decode()
    assert (archive / "database.sql.gz").stat().st_mode & 0o777 == 0o600
    assert archive.stat().st_mode & 0o777 == 0o700
    assert old.read_bytes() == b"old backup"
    assert not (project / "SHOULD_NOT_EXIST").exists()
    assert set((destination.parent / "trace").read_text().splitlines()) <= {"ps", "inspect", "volume", "exec"}


@pytest.mark.parametrize("fault", ["owner", "engine", "dump", "truncated", "timeout"])
def test_host_failures_never_publish_complete_archive_or_remove_previous(host, monkeypatch, fault):
    destination, _, run = host
    old = destination / "old.sql.gz"
    old.write_bytes(b"keep")
    monkeypatch.setenv("FAULT", fault)
    result = run(limit=1 if fault == "timeout" else 20)
    assert result.returncode != 0
    assert not list(destination.glob("*/COMPLETE"))
    assert old.read_bytes() == b"keep"


def test_host_rejects_backup_folder_readable_by_application(host, monkeypatch):
    destination, _, run = host
    monkeypatch.setenv("MOUNT_SOURCE", str(destination.parent))
    result = run()
    assert result.returncode == 2
    assert "backup_exposed_to_application" in result.stdout


def test_host_rejects_backup_folder_with_public_permissions(host):
    destination, _, run = host
    destination.chmod(0o755)
    assert run().returncode == 2
    assert not list(destination.glob("*/COMPLETE"))


@pytest.mark.skipif(os.getenv("NAS_SQL_BACKUP_DOCKER_TEST") != "1", reason="local isolated Docker opt-in")
def test_mysql_online_snapshot_restore_programs_and_concurrent_business_writes():
    spec = importlib.util.spec_from_file_location("nas_backup_docker", Path(__file__).with_name("test_nas_compose_lifecycle.py"))
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    docker = helpers.LocalDocker()
    identifier = uuid4().hex[:10]
    project = "lu-nas-life-sql-" + identifier
    directory = ROOT / "scratch" / ("nas-sql-backup-" + identifier)
    directory.mkdir()
    secret = directory / "secrets"
    secret.mkdir()
    (secret / "root-password").write_text(secrets.token_urlsafe(40), encoding="utf-8")
    containers = []
    database = "lu_test_sql_backup"

    def sql(container, statement):
        return docker.run("exec", "-i", container, "bash", "-c",
            'mysql --defaults-extra-file=<(printf "[client]\\nuser=root\\npassword=%s\\n" "$(cat /run/mysql-secrets/root-password)") --protocol=SOCKET --batch --skip-column-names',
            source=statement)

    def dbscript(container, action):
        # Windows subprocess text pipes send CRLF; the delivered .sh is strict LF.
        result = docker.run("exec", "-i", container, "timeout", "-s", "TERM", "-k", "5", "30", "bash", "-c",
                           'tr -d "\\r" | bash -s -- "$1"', "_", action, source=DB_SCRIPT, success=False)
        # This server contains only the synthetic fixture; still redact its credential.
        assert result.returncode == 0, result.stderr.replace((secret / "root-password").read_text(), "[redacted]")
        return result.stdout

    def start(suffix):
        name = project + suffix
        docker.run("run", "-d", "--name", name, "--label", "labor-union.sql-backup-test=1", "--network", "none", "--memory", "512m",
            "--mount", f"type=bind,source={secret},target=/run/mysql-secrets,readonly",
            "-e", "MYSQL_ROOT_PASSWORD_FILE=/run/mysql-secrets/root-password", "-e", f"MYSQL_DATABASE={database}",
            "mysql:8.0.46", "--innodb-buffer-pool-size=64M", "--skip-log-bin", "--max-connections=20")
        containers.append(name)
        for _ in range(60):
            try:
                if sql(name, "SELECT 1;").strip() == "1": return name
            except AssertionError:
                pass
            time.sleep(1)
        raise AssertionError("isolated MySQL readiness timeout")

    try:
        source = start("-source")
        restore = start("-restore")
        sql(source, f"""USE {database};
CREATE TABLE balances (id INT PRIMARY KEY, amount INT, note VARCHAR(30)) ENGINE=InnoDB;
INSERT INTO balances VALUES (1,100,'測試甲'),(2,200,'測試乙');
CREATE VIEW current_balance AS SELECT SUM(amount) AS total FROM balances;
CREATE PROCEDURE read_balance() SELECT total FROM current_balance;
CREATE FUNCTION add_one(value INT) RETURNS INT DETERMINISTIC RETURN value+1;
CREATE TRIGGER positive_amount BEFORE INSERT ON balances FOR EACH ROW SET NEW.amount=ABS(NEW.amount);
CREATE EVENT inert_event ON SCHEDULE EVERY 1 DAY DO SELECT 1;
""")
        before = dbscript(source, "check")
        assert before.startswith("INNODB_OK\n")
        errors = []
        def writer():
            try:
                sql(source, f"USE {database}; BEGIN; UPDATE balances SET amount=amount+100 WHERE id=1; SELECT SLEEP(8); UPDATE balances SET amount=amount+100 WHERE id=2; COMMIT;")
            except Exception as error:
                errors.append(type(error).__name__)
        thread = threading.Thread(target=writer)
        thread.start()
        for _ in range(30):
            if int(sql(source, "SELECT COUNT(*) FROM information_schema.PROCESSLIST WHERE STATE='User sleep';").strip()) > 0: break
            time.sleep(0.1)
        else: raise AssertionError("writer did not enter test transaction")
        started = time.monotonic()
        dump = dbscript(source, "dump")
        assert time.monotonic() - started < 7, "dump must not wait for the writer to commit"
        assert sql(source, f"SELECT total FROM {database}.current_balance;").strip() == "300"
        thread.join(timeout=15)
        assert not thread.is_alive() and not errors
        assert sql(source, f"SELECT total FROM {database}.current_balance;").strip() == "500"
        assert "Dump completed on" in dump
        sql(restore, dump)
        assert sql(restore, f"USE {database}; CALL read_balance();").strip() == "300"
        assert "測試甲" in sql(restore, f"SELECT note FROM {database}.balances WHERE id=1;")
        assert sql(restore, f"SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='{database}';").strip() == "1"
        assert sql(restore, f"SELECT COUNT(*) FROM information_schema.EVENTS WHERE EVENT_SCHEMA='{database}';").strip() == "1"
        assert sql(restore, f"SELECT {database}.add_one(8);").strip() == "9"
        sql(restore, f"INSERT INTO {database}.balances VALUES (3,-7,'trigger');")
        assert sql(restore, f"SELECT amount FROM {database}.balances WHERE id=3;").strip() == "7"
        sql(source, f"CREATE TABLE {database}.unsupported (id INT) ENGINE=MyISAM;")
        unsupported = dbscript(source, "check")
        assert unsupported.startswith("UNSUPPORTED_TABLE_ENGINE\n")
    finally:
        for name in containers:
            docker.run("stop", "--time", "20", name, success=False)
