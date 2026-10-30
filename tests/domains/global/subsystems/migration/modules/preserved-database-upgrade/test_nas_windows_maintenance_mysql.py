"""Opt-in real MySQL: full fresh source → SQL backup → restore → upgrade.

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


def test_sql_backup_restore_and_canonical_upgrade_keep_source_accounts_and_neighbour_data(tmp_path, monkeypatch):
    name = "lu-test-nas-maintenance-" + uuid4().hex[:12]
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
        backup = nas.backup(settings)
        assert backup.suffixes == [".sql", ".gz"]
        assert backup.with_suffix(".gz.sha256").is_file()
        assert not list(settings["backup_root"].glob("????-??/*.sql"))
        source_before = nas.migration._table_evidence(nas.reader(settings), source_db)
        nas.restore(settings, backup)
        restored = dotenv_values(runtime)["DB_DATABASE"]
        assert restored.startswith("lu_nas_restore_")
        assert nas.migration._table_evidence(nas.writer(settings), restored) == source_before
        assert nas.migration._table_evidence(nas.reader(settings), source_db) == source_before
        # The original application and backup credentials both work on the copy.
        for user, password in (("fixture_app", app_password), ("fixture_reader", read_password)):
            probe = pymysql.connect(host="127.0.0.1", port=port, user=user, password=password, database=restored)
            with probe.cursor() as cursor:
                cursor.execute("SELECT note,payload FROM nas_maintenance_probe WHERE id=1")
                assert cursor.fetchone() == ("中文備份測試", b"\x00\xfffixture")
            probe.close()
        settings["database"], settings["runtime"] = restored, dotenv_values(runtime)
        nas.upgrade(settings)
        upgraded = dotenv_values(runtime)["DB_DATABASE"]
        assert upgraded.startswith("lu_nas_upgrade_")
        assert nas.migration._table_evidence(nas.reader(settings), restored) == source_before
        assert nas.migration._table_evidence(nas.writer(settings), source_db) == source_before
        connection = pymysql.connect(**base, autocommit=True)
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM lu_test_neighbour.sentinel")
            assert cursor.fetchall() == ((7,),)
            cursor.execute(f"SELECT note,payload FROM `{upgraded}`.nas_maintenance_probe WHERE id=1")
            assert cursor.fetchone() == ("中文備份測試", b"\x00\xfffixture")
        connection.close()
    finally:
        if created:
            info = json.loads(docker("inspect", name))[0]
            assert info["Config"]["Labels"].get("labor-union.nas-maintenance-test") == "1"
            docker("rm", "-f", "-v", name)
