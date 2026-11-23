"""Opt-in real MySQL: fresh source → SQL backup → restore → current no-op.

Only a uniquely named container created by this test may be destroyed. Never
uses the workstation .env, an existing container/volume, or a NAS connection.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
from uuid import uuid4

from dotenv import dotenv_values
import pymysql
import pytest

from scripts import initialize_nas_schema as fresh
from scripts import nas_database_maintenance as nas

pytestmark = pytest.mark.skipif(os.getenv("NAS_WINDOWS_MAINTENANCE_MYSQL_TEST") != "1", reason="explicit isolated Docker opt-in")


def test_sql_backup_restore_and_current_upgrade_noop_keep_source_accounts_and_neighbour_data(tmp_path, monkeypatch):
    name = "lu-test-nas-maintenance-" + uuid4().hex[:12]
    run_id = os.getenv("NAS_WINDOWS_MAINTENANCE_TEST_RUN_ID", name)
    source_db = "lu_test_nas_source"
    secret = tmp_path / "secrets"
    secret.mkdir()
    root_password, app_password, read_password = [secrets.token_urlsafe(40) for _ in range(3)]
    (secret / "root-password").write_text(root_password, encoding="utf-8")
    (secret / "app-password").write_text(app_password, encoding="utf-8")

    def docker(*args, **kwargs):
        result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=120, **kwargs)
        assert result.returncode == 0, "isolated test Docker operation failed: " + args[0]
        return result.stdout.strip()

    created = False
    try:
        docker("run", "--pull", "never", "-d", "--name", name, "--label", "labor-union.nas-maintenance-test=1",
               "--label", "labor-union.nas-maintenance-run=" + run_id,
               "--publish", "127.0.0.1::3306", "--memory", "768m",
               "--mount", f"type=bind,source={secret},target=/run/mysql-secrets,readonly",
               "-e", "MYSQL_ROOT_PASSWORD_FILE=/run/mysql-secrets/root-password", "-e", "MYSQL_ROOT_HOST=%",
               "-e", "MYSQL_PASSWORD_FILE=/run/mysql-secrets/app-password", "-e", "MYSQL_USER=fixture_app",
               "-e", "MYSQL_DATABASE=" + source_db, "mysql:8.0.46", "--innodb-buffer-pool-size=96M", "--skip-log-bin")
        created = True
        port = int(json.loads(docker("inspect", name))[0]["NetworkSettings"]["Ports"]["3306/tcp"][0]["HostPort"])
        base = {"host": "127.0.0.1", "port": port, "user": "root", "password": root_password, "charset": "utf8mb4"}
        for _ in range(90):
            try:
                pymysql.connect(**base, connect_timeout=1).close()
                break
            except pymysql.MySQLError:
                time.sleep(1)
        else:
            pytest.fail("isolated MySQL did not become ready")
        plan = fresh.schema_plan()
        result = fresh.initialize({**base, "database": source_db}, plan, apply=True, receipt_root=tmp_path / "fresh")
        assert result["status"] == "passed"
        connection = pymysql.connect(**base, autocommit=True)
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE TABLE `{source_db}`.nas_maintenance_probe(id INT PRIMARY KEY,note VARCHAR(50),payload BLOB) ENGINE=InnoDB")
            cursor.execute(f"INSERT INTO `{source_db}`.nas_maintenance_probe VALUES (1,%s,%s)", ("中文備份測試", b"\x00\xfffixture"))
            cursor.execute("CREATE DATABASE lu_test_neighbour")
            cursor.execute("CREATE TABLE lu_test_neighbour.sentinel(id INT PRIMARY KEY)")
            cursor.execute("INSERT INTO lu_test_neighbour.sentinel VALUES (7)")
            cursor.execute("CREATE USER 'fixture_reader'@'%%' IDENTIFIED BY %s", (read_password,))
            cursor.execute(f"GRANT SELECT,SHOW VIEW,TRIGGER,EVENT ON `{source_db}`.* TO 'fixture_reader'@'%'")
            cursor.execute("GRANT SHOW_ROUTINE ON *.* TO 'fixture_reader'@'%'")
        connection.close()
        runtime = tmp_path / ".env.fixture"
        runtime.write_text(f"DB_HOST=127.0.0.1\nDB_PORT={port}\nDB_DATABASE={source_db}\nDB_USER=fixture_app\nDB_PASSWORD={app_password}\n", encoding="utf-8")
        settings = {"host": "127.0.0.1", "port": port, "database": source_db, "tls": {}, "tls_files": {}, "ssl_mode": "DISABLED",
                    "environment_file": runtime, "backup_root": tmp_path / nas.BACKUP_FOLDER, "runtime": dotenv_values(runtime),
                    "values": {"NAS_BACKUP_USER": "fixture_reader", "NAS_BACKUP_PASSWORD": read_password,
                               "NAS_MAINTENANCE_USER": "root", "NAS_MAINTENANCE_PASSWORD": root_password}}
        monkeypatch.setattr(nas, "private_directory", lambda p: (Path(p).mkdir(parents=True, exist_ok=True) or Path(p)))
        settings["backup_root"].mkdir()
        monkeypatch.setattr(nas, "is_nas_destination", lambda _: True)
        monkeypatch.setattr(nas.ConnectionConfig, "client_prefix", lambda *_: ["docker"])
        def client_command(config, executable, **_):
            return ["docker", "exec", "-i", "-e", "MYSQL_PWD", name, executable, "--protocol=SOCKET", "--user", config.user,
                    "--default-character-set=utf8mb4"]
        monkeypatch.setattr(nas.migration, "_mysql_base", client_command)
        runtime_before = runtime.read_bytes()
        with pymysql.connect(**base, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SHOW DATABASES")
                schemas_before_backup = cursor.fetchall()
            backup = nas.backup(settings)
            with connection.cursor() as cursor:
                cursor.execute("SHOW DATABASES")
                assert cursor.fetchall() == schemas_before_backup
        assert runtime.read_bytes() == runtime_before
        assert backup.suffix == ".zip"
        assert not list(settings["backup_root"].glob("????-??/*.sql"))
        assert not list(settings["backup_root"].glob("????-??/*.sql.gz"))
        assert not (settings["backup_root"] / "_receipts").exists()
        source_before = nas.migration._table_evidence(nas.reader(settings), source_db)
        backup_sha256 = nas.digest(backup)
        connection = pymysql.connect(**base, autocommit=True)
        with connection.cursor() as cursor:
            cursor.execute("SHOW DATABASES")
            schemas_before = cursor.fetchall()
            for _ in range(2):
                cursor.execute(f"UPDATE `{source_db}`.nas_maintenance_probe SET note='changed before replacement' WHERE id=1")
                run = nas.restore(settings, backup)
                assert dotenv_values(runtime)["DB_DATABASE"] == source_db
                assert runtime.read_bytes() == runtime_before
                assert nas.digest(backup) == backup_sha256
                assert not list(run.rglob("*.zip"))
                assert not list(run.rglob("*.sql.gz"))
                assert list(settings["backup_root"].rglob("*.zip")) == [backup]
                assert nas.migration._table_evidence(nas.reader(settings), source_db) == source_before
                cursor.execute("SHOW DATABASES")
                assert cursor.fetchall() == schemas_before
                cursor.execute("SELECT id FROM lu_test_neighbour.sentinel")
                assert cursor.fetchall() == ((7,),)
                for user in ("fixture_app", "fixture_reader"):
                    cursor.execute("SHOW GRANTS FOR %s@'%%'", (user,))
                    assert not any("restore" in row[0] for row in cursor.fetchall())
        connection.close()
        upgrade_run = nas.upgrade(settings)
        assert upgrade_run == settings["backup_root"] / "_maintenance" / "direct_upgrade"
        assert json.loads((upgrade_run / "result.json").read_text(encoding="utf-8")) == {"status": "completed", "database": source_db}
        assert runtime.read_bytes() == runtime_before
        assert list(settings["backup_root"].glob("????-??/*.zip")) == [backup]
        for user, password in (("fixture_app", app_password), ("fixture_reader", read_password)):
            probe = pymysql.connect(host="127.0.0.1", port=port, user=user, password=password, database=source_db)
            with probe.cursor() as cursor:
                cursor.execute("SELECT note,payload FROM nas_maintenance_probe WHERE id=1")
                assert cursor.fetchone() == ("中文備份測試", b"\x00\xfffixture")
            probe.close()
        connection = pymysql.connect(**base, autocommit=True)
        with connection.cursor() as cursor:
            cursor.execute("SHOW DATABASES")
            assert not any(row[0].startswith("lu_nas_upgrade_") for row in cursor.fetchall())
            cursor.execute("SELECT id FROM lu_test_neighbour.sentinel")
            assert cursor.fetchall() == ((7,),)
        connection.close()
    finally:
        if created:
            info = json.loads(docker("inspect", name))[0]
            assert info["Config"]["Labels"].get("labor-union.nas-maintenance-test") == "1"
            assert info["Config"]["Labels"].get("labor-union.nas-maintenance-run") == run_id
            docker("rm", "-f", "-v", name)
