"""DSM cold-copy adapter for the existing local preserve-data updater.

The operational MySQL volume is never mounted in the upgrade helper. Only a
verified, stopped cold-backup copy is eligible for the local replacement runner.
The Docker socket belongs solely to this operator-invoked maintenance tool.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import stat
import struct
import sys
import tarfile
import time
from urllib.parse import quote


class UpgradeBlocked(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise UpgradeBlocked(code)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def emit(status, **fields):
    print(json.dumps({"status": status, **fields}), flush=True)


def save(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".pending")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def env_value(path, key):
    # Do not source/eval deployment settings or parse unrelated secret values.
    values = re.findall(r"(?m)^" + re.escape(key) + r"=([^\r\n]*)$", Path(path).read_text("utf-8"))
    require(len(values) == 1, "missing_or_duplicate_" + key.lower())
    return values[0].strip().strip("\"'")


class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect("/var/run/docker.sock")


class Docker:
    def request(self, method, path, payload=None, *, timeout=30, stream=False):
        connection = UnixConnection("localhost", timeout=timeout)
        body = None if payload is None else json.dumps(payload).encode()
        connection.request(method, "/v1.41/" + path, body, {"Content-Type": "application/json"})
        response = connection.getresponse()
        if response.status >= 300:
            response.read()
            connection.close()
            raise UpgradeBlocked("docker_api_" + str(response.status))
        if stream:
            return connection, response
        raw = response.read()
        connection.close()
        return json.loads(raw) if raw else None

    def inspect(self, name):
        return self.request("GET", "containers/" + quote(name, safe="") + "/json")

    def run(self, name, image, command, mounts, *, network="none", environment=(), labels=None, memory=384*1024*1024):
        payload = {"Image": image, "Cmd": command, "Entrypoint": [], "Env": list(environment),
                   "Labels": labels or {}, "User": "0", "HostConfig": {
                       "NetworkMode": network, "Mounts": mounts, "Memory": memory,
                       "ReadonlyRootfs": True, "Tmpfs": {"/tmp": "rw,exec,nosuid,size=128m", "/var/run/mysqld": "rw,nosuid,size=8m,mode=1777"},
                       "SecurityOpt": ["no-new-privileges:true"]}}
        identifier = self.request("POST", "containers/create?name=" + quote(name), payload)["Id"]
        self.request("POST", "containers/" + identifier + "/start")
        return identifier

    def wait(self, identifier, timeout=900, progress_directory=None):
        if progress_directory is not None:
            started, last_report = time.monotonic(), 0
            while True:
                state = self.inspect(identifier)["State"]
                if not state["Running"]:
                    require(state["ExitCode"] == 0, "maintenance_container_failed")
                    return
                elapsed = time.monotonic() - started
                require(elapsed < timeout, "copy_upgrade_timeout")
                if elapsed - last_report >= 30:
                    receipts = list(Path(progress_directory).glob("receipts/*/operation.receipt.json"))
                    progress = json.loads(receipts[0].read_text()) if receipts else {}
                    emit("upgrading_copy", elapsed_seconds=int(elapsed), phase=progress.get("phase", "plan_or_backup"),
                         schema_steps=len(progress.get("schema_steps", [])))
                    last_report = elapsed
                time.sleep(2)
        result = self.request("POST", "containers/" + identifier + "/wait", timeout=timeout)
        require(result["StatusCode"] == 0, "maintenance_container_failed")

    def stop(self, identifier):
        if self.inspect(identifier)["State"]["Running"]:
            self.request("POST", "containers/" + identifier + "/stop?t=20", timeout=30)

    def execute(self, identifier, command, *, environment=(), output=None, error=None):
        created = self.request("POST", "containers/" + identifier + "/exec", {
            "Cmd": command, "Env": list(environment), "AttachStdout": True,
            "AttachStderr": True, "AttachStdin": False, "Tty": False, "User": "0"})["Id"]
        connection, response = self.request("POST", "exec/" + created + "/start", {"Detach": False, "Tty": False}, timeout=900, stream=True)
        try:
            while header := response.read(8):
                require(len(header) == 8, "docker_stream_truncated")
                channel, size = header[0], struct.unpack(">I", header[4:])[0]
                target = output if channel == 1 else error
                while size:
                    chunk = response.read(min(size, 65536))
                    require(bool(chunk), "docker_stream_truncated")
                    if target is not None:
                        target.write(chunk)
                    size -= len(chunk)
        finally:
            connection.close()
        result = self.request("GET", "exec/" + created + "/json")
        require(not result["Running"], "docker_exec_still_running")
        return result["ExitCode"]


def mount(source, target, kind="bind", readonly=False):
    return {"Type": kind, "Source": str(source), "Target": target, "ReadOnly": readonly}


def guarded_helper(docker, context):
    info = docker.inspect(context["helper"])
    require(info["Config"].get("Labels", {}).get("labor-union.upgrade") == context["run_id"], "wrong_upgrade_helper")
    require(info["HostConfig"]["NetworkMode"] == "none" and not info["HostConfig"].get("PortBindings"), "helper_network_not_isolated")
    data = [m for m in info["Mounts"] if m["Destination"] == "/var/lib/mysql"]
    require(len(data) == 1 and data[0]["Name"] == context["new_volume"] and data[0]["Name"] != context["old_volume"], "helper_not_using_new_volume")
    return info


def mysql_client_proxy(arguments):
    # Exactly the docker-exec shape used by canonical _mysql_base. No general CLI.
    context = json.loads(Path("/upgrade/context.json").read_text("utf-8"))
    require(arguments[:4] == ["exec", "-i", "-e", "MYSQL_PWD"], "unsupported_client_command")
    require(len(arguments) >= 7 and arguments[4] == context["helper"] and arguments[5] in {"mysql", "mysqldump"}, "foreign_client_target")
    docker = Docker()
    guarded_helper(docker, context)
    command = arguments[5:]
    temporary = None
    if command[0] == "mysql":
        descriptor = os.readlink("/proc/self/fd/0")
        if descriptor.startswith("/upgrade/") and stat.S_ISREG(os.fstat(0).st_mode):
            source = descriptor
        else:
            temporary = Path("/upgrade/client-input.sql")
            with temporary.open("wb") as target:
                os.chmod(temporary, 0o600)
                shutil.copyfileobj(sys.stdin.buffer, target)
            source = str(temporary)
        command = ["/bin/bash", "-c", 'exec "$@" < "$INPUT_FILE"', "nas-mysql", *command]
        environment = ["INPUT_FILE=" + source]
    else:
        environment = []
    environment.append("MYSQL_PWD=" + os.environ["MYSQL_PWD"])
    try:
        return docker.execute(context["helper"], command, environment=environment, output=sys.stdout.buffer, error=sys.stderr.buffer)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run_copy_upgrade():
    context = json.loads(Path("/upgrade/context.json").read_text("utf-8"))
    require(re.fullmatch(r"lu_test_[a-z0-9_]+", context["candidate"]), "candidate_namespace_invalid")
    from scripts import update_local_database as updater
    from infrastructure.mysql.nas_permissions import PROFILES, install_permissions, verify_runtime_permissions
    import pymysql

    docker = Docker()
    guarded_helper(docker, context)
    # This is the copied, unexposed MySQL server, never the operational server.
    os.environ.update(APP_ENV="development", DB_HOST="127.0.0.1", DB_PORT="3306", DB_USER="root",
                      DB_PASSWORD=Path("/mysql-secrets/root-password").read_text().strip(), DB_DATABASE=context["database"])
    bin_dir = Path("/tmp/nas-upgrade-bin")
    bin_dir.mkdir(mode=0o700)
    proxy = bin_dir / "docker"
    proxy.write_text('#!/bin/sh\nexec python /opt/nas-upgrade.py --client "$@"\n', encoding="utf-8")
    proxy.chmod(0o700)
    os.environ["PATH"] = str(bin_dir) + ":" + os.environ["PATH"]
    missing_env = Path("/upgrade/no-runtime-env")
    require(not missing_env.exists(), "unexpected_clone_environment_file")
    options = dict(environment_file=missing_env, receipt_root=Path("/upgrade/receipts"),
                   candidate=context["candidate"], mysql_container=context["helper"], strategy="replacement", allow_long_run=True)
    emit("upgrading_backup_copy")
    result = updater.update_local_database(**options, apply=True, confirm_database=context["database"])
    require(result["status"] == "completed", "copy_upgrade_not_completed")
    # Verify the same database name the unmodified production runtime will use.
    from scripts.compact_fresh_schema import load_compact_plan
    from scripts.verify_validation_schema_manifest import verify_database_objects
    expected = load_compact_plan()["expected"]
    connection = pymysql.connect(host="127.0.0.1", port=3306, user="root", password=os.environ["DB_PASSWORD"],
                                 database=context["database"], autocommit=True, charset="utf8mb4", connect_timeout=5)
    try:
        with connection.cursor() as cursor:
            require(not verify_database_objects(cursor, context["database"], expected), "copy_schema_not_current")
        passwords = {p: Path("/profiles", p, "password").read_text().strip() for p in PROFILES}
        permissions = install_permissions(connection, context["database"], passwords)
    finally:
        connection.close()
    # Verify the original CA over this private loopback namespace. Hostname
    # verification belongs to the unchanged production API's strict TLS gate.
    tls = {"ca": "/tls/ca.pem", "check_hostname": False}
    for profile in PROFILES:
        probe = pymysql.connect(host="127.0.0.1", user=permissions["accounts"][profile], password=passwords[profile],
                                database=context["database"], ssl=tls, connect_timeout=5)
        try:
            verify_runtime_permissions(probe, profile, context["database"], expected_tables=expected["tables"], expected_views=expected["views"])
        finally:
            probe.close()
    save("/upgrade/verified.json", {"status": "verified", "run_id": context["run_id"],
                                    "database": context["database"], "release": updater.migration.RELEASE_MANIFEST.release_id,
                                    "new_volume": context["new_volume"], "runtime_profiles": list(PROFILES)})
    emit("verified", original_database_modified=False)


def verify_backup(backup, project, deployment, archive_name="mysql-data.tar.gz"):
    require(backup.is_dir() and not backup.is_symlink() and (backup / "COMPLETE").is_file(), "complete_backup_required")
    require((backup / "project-name.txt").read_text().strip() == project, "backup_project_mismatch")
    require((backup / "project-directory.txt").read_text().strip() == deployment, "backup_path_mismatch")
    checks = {}
    for line in (backup / "SHA256SUMS").read_text().splitlines():
        match = re.fullmatch(r"([a-f0-9]{64}) [ *]([^/\\]+)", line)
        require(match is not None and match[2] not in {".", ".."}, "invalid_backup_checksums")
        require(not (backup / match[2]).is_symlink() and digest(backup / match[2]) == match[1], "backup_checksum_mismatch")
        checks[match[2]] = match[1]
    require({"compose.yaml", ".env", "database.sql", archive_name} <= checks.keys(), "full_backup_required")
    return checks


def original_stopped(docker, project, context=None):
    containers = docker.request("GET", "containers/json?all=true&filters=" + quote(json.dumps({"label": ["com.docker.compose.project=" + project]})))
    require(containers and all(c["State"] == "exited" for c in containers), "original_project_must_remain_stopped")
    db = docker.inspect(project + "-db-1")
    require(db["State"]["ExitCode"] == 0 and not db["State"].get("OOMKilled"), "original_db_not_cleanly_stopped")
    require(db["Config"]["Labels"].get("com.docker.compose.project") == project, "wrong_original_project")
    data = [m for m in db["Mounts"] if m["Destination"] == "/var/lib/mysql"]
    require(len(data) == 1 and data[0]["Type"] == "volume", "original_db_volume_required")
    if context:
        require(data[0]["Name"] == context["old_volume"] and db["Image"] == context["mysql_image"], "original_database_identity_changed")
        require(db["Id"] == context["original_db_id"] and db["State"]["StartedAt"] == context["original_started_at"]
                and db["State"]["FinishedAt"] == context["original_finished_at"], "original_database_restarted_during_upgrade")
    return db, data[0]["Name"]


def extract_copy(archive_name="mysql-data.tar.gz"):
    # The backup checksum has already been verified. Do not restore runtime sockets.
    root = Path("/clone-data")
    require(not any(root.iterdir()), "clone_volume_not_empty")
    require(re.fullmatch(r"[A-Za-z0-9_-]+\.tar\.gz", archive_name), "invalid_archive_name")
    with tarfile.open(Path("/backup") / archive_name) as archive:
        for member in archive:
            if member.name.lstrip("./") in {"mysql.sock", "mysql.sock.lock"}:
                continue
            archive.extract(member, root, filter="data")
    for folder, directories, files in os.walk(root):
        os.chown(folder, 999, 999)
        for name in directories + files:
            os.chown(Path(folder, name), 999, 999, follow_symlinks=False)


def prepare(args):
    docker, deployment = Docker(), Path("/deployment")
    project = env_value(deployment / ".env", "COMPOSE_PROJECT_NAME")
    require(re.fullmatch(r"[a-z0-9][a-z0-9_-]+", project), "invalid_project_name")
    emit("checking_backup")
    db, old_volume = original_stopped(docker, project)
    require(old_volume.startswith(project + "_"), "unexpected_source_volume_name")
    archive_name = old_volume[len(project) + 1:] + ".tar.gz"
    checks = verify_backup(Path("/backup"), project, args.project_dir, archive_name)
    require(digest(deployment / ".env") == checks[".env"] and digest(deployment / "compose.yaml") == checks["compose.yaml"], "deployment_changed_since_backup")
    finished = datetime.fromisoformat(db["State"]["FinishedAt"].replace("Z", "+00:00"))
    require(finished.timestamp() <= (Path("/backup/COMPLETE").stat().st_mtime), "database_restarted_after_backup")
    volume = docker.request("GET", "volumes/" + quote(old_volume))
    require(volume.get("Labels", {}).get("com.docker.compose.project") == project, "foreign_source_volume")
    image = docker.request("GET", "images/" + quote(args.image, safe="") + "/json")["Id"]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = deployment / "database-upgrades" / run_id
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(directory.parent, 0o700)
    new_volume = project + "_mysql-upgrade-" + run_id.lower()
    helper = project + "-upgrade-db-" + run_id.lower()
    context = {"run_id": run_id, "project": project, "project_dir": args.project_dir, "image": image, "image_tag": args.image,
               "old_volume": old_volume, "new_volume": new_volume, "mysql_image": db["Image"], "helper": helper,
               "original_db_id": db["Id"], "original_started_at": db["State"]["StartedAt"], "original_finished_at": db["State"]["FinishedAt"],
               "database": next(x.split("=", 1)[1] for x in db["Config"]["Env"] if x.startswith("MYSQL_DATABASE=")),
               "candidate": "lu_test_nas_candidate_" + run_id.lower(), "before_env": checks[".env"], "before_compose": checks["compose.yaml"],
               "backup_host": args.backup_dir, "directory_host": args.project_dir + "/database-upgrades/" + run_id}
    require(re.fullmatch(r"[A-Za-z0-9_]+", context["database"]), "invalid_source_database")
    save(directory / "context.json", context)
    for name in ("compose.yaml", ".env"):
        shutil.copyfile(deployment / name, directory / (name + ".before"))
        os.chmod(directory / (name + ".before"), 0o600)
    labels = {"labor-union.upgrade": run_id}
    for profile in ("management", "line", "access", "maintenance"):
        info = docker.request("GET", "volumes/" + quote(project + "_" + profile + "-db"))
        require(info.get("Labels", {}).get("com.docker.compose.project") == project, "profile_volume_owner_mismatch")
    created = []
    try:
        docker.request("POST", "volumes/create", {"Name": new_volume, "Labels": {**labels, "com.docker.compose.project": project, "com.docker.compose.volume": "mysql-data"}})
        script_mount = mount(args.script_path, "/opt/nas-upgrade.py", readonly=True)
        emit("copying_cold_backup")
        identifier = docker.run(helper + "-restore", image, ["python", "/opt/nas-upgrade.py", "extract", "--archive-name", archive_name],
                                [script_mount, mount(args.backup_dir, "/backup", readonly=True), mount(new_volume, "/clone-data", "volume")], labels=labels)
        created.append(identifier)
        docker.wait(identifier)
        mounts = [mount(new_volume, "/var/lib/mysql", "volume"), mount(context["directory_host"], "/upgrade")]
        for target in ("/run/mysql-secrets", "/tls"):
            source = next(m for m in db["Mounts"] if m["Destination"] == target)
            require(source["Type"] == "volume", "expected_existing_secret_volume")
            mounts.append(mount(source["Name"], target, "volume", True))
        command = [c for c in db["Config"]["Cmd"] if not c.startswith(("--require-secure-transport", "--bind-address"))]
        if command and command[0] == "mysqld":
            command = command[1:]
        command = ["mysqld", "--user=mysql", *command, "--require-secure-transport=OFF", "--bind-address=127.0.0.1"]
        identifier = docker.run(helper, db["Image"], command, mounts, labels=labels, memory=512*1024*1024)
        created.append(identifier)
        emit("starting_isolated_copy", maximum_wait_seconds=180)
        deadline = time.monotonic() + 180
        while True:
            require(docker.inspect(helper)["State"]["Running"], "copy_mysql_exited")
            if docker.execute(helper, ["mysqladmin", "--host=127.0.0.1", "--connect-timeout=3", "ping", "--silent"]) == 0:
                break
            require(time.monotonic() < deadline, "copy_mysql_start_timeout")
            time.sleep(2)
        runner_mounts = [script_mount, mount("/var/run/docker.sock", "/var/run/docker.sock"), mount(context["directory_host"], "/upgrade")]
        secrets_mount = next(m for m in db["Mounts"] if m["Destination"] == "/run/mysql-secrets")
        runner_mounts.append(mount(secrets_mount["Name"], "/mysql-secrets", "volume", True))
        tls_mount = next(m for m in db["Mounts"] if m["Destination"] == "/tls")
        runner_mounts.append(mount(tls_mount["Name"], "/tls", "volume", True))
        for profile in ("management", "line", "access", "maintenance"):
            runner_mounts.append(mount(project + "_" + profile + "-db", "/profiles/" + profile, "volume", True))
        emit("running_existing_preserve_data_updater", maximum_wait_seconds=args.upgrade_timeout)
        identifier = docker.run(helper + "-runner", image, ["python", "/opt/nas-upgrade.py", "run-copy"], runner_mounts,
                                network="container:" + helper, labels=labels, environment=["PYTHONPATH=/app"])
        created.append(identifier)
        try:
            docker.wait(identifier, timeout=args.upgrade_timeout, progress_directory=directory)
        except UpgradeBlocked:
            if (directory / "failure.json").is_file():
                failure = json.loads((directory / "failure.json").read_text("utf-8"))
                emit("copy_upgrade_failed", error_code=failure.get("error_code"), cause_types=failure.get("cause_types"))
            raise
        require((directory / "verified.json").is_file(), "verified_receipt_missing")
        original_stopped(docker, project, context)
    finally:
        cleanup_failed = False
        for identifier in reversed(created):
            try:
                docker.stop(identifier)
            except Exception:
                cleanup_failed = True
                emit("cleanup_required", scope="upgrade_helpers_only")
        require(not cleanup_failed, "upgrade_helpers_not_stopped")
    emit("prepared", run_id=run_id, original_database_modified=False, next_step="switch")


def switch(args):
    import yaml
    docker, deployment = Docker(), Path("/deployment")
    require(re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", args.run_id or ""), "run_id_required")
    directory = deployment / "database-upgrades" / args.run_id
    context = json.loads((directory / "context.json").read_text())
    verified = json.loads((directory / "verified.json").read_text())
    require(verified["run_id"] == context["run_id"] and verified["new_volume"] == context["new_volume"] and verified["status"] == "verified", "verification_identity_mismatch")
    require(context["project_dir"] == args.project_dir and context["image_tag"] == args.image, "switch_target_mismatch")
    original_stopped(docker, context["project"], context)
    require(not guarded_helper(docker, context)["State"]["Running"], "copy_mysql_must_be_stopped")
    require(not (directory / "switched.json").exists(), "already_switched")
    env_path, compose_path = deployment / ".env", deployment / "compose.yaml"
    require(digest(env_path) == context["before_env"] and digest(compose_path) == context["before_compose"], "configuration_changed_after_prepare")
    model = yaml.safe_load(compose_path.read_text("utf-8"))
    require("mysql-data" in model["volumes"], "mysql_volume_mapping_missing")
    model["volumes"]["mysql-data"] = {"external": True, "name": context["new_volume"]}
    compose_after = yaml.safe_dump(model, allow_unicode=True, sort_keys=False).encode("utf-8")
    env_before = env_path.read_bytes()
    require(len(re.findall(rb"(?m)^NAS_IMAGE=[^\r\n]*", env_before)) == 1, "unique_image_setting_required")
    env_after = re.sub(rb"(?m)^NAS_IMAGE=[^\r\n]*", lambda _: b"NAS_IMAGE=" + args.image.encode("ascii"), env_before)
    # Persist both intended hashes before modifying either file; interruption is explicit.
    save(directory / "switch-plan.json", {"env_before": context["before_env"], "compose_before": context["before_compose"],
                                          "env_after": hashlib.sha256(env_after).hexdigest(), "compose_after": hashlib.sha256(compose_after).hexdigest()})
    for path, content in ((compose_path, compose_after), (env_path, env_after)):
        pending = path.with_name(path.name + ".upgrade-pending")
        with pending.open("xb") as stream:
            os.chmod(pending, 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        previous_stat = path.stat()
        shutil.copystat(path, pending, follow_symlinks=False)
        if hasattr(os, "chown"):
            os.chown(pending, previous_stat.st_uid, previous_stat.st_gid)
        os.replace(pending, path)
    save(directory / "switched.json", {"status": "configuration_switched", "run_id": args.run_id, "old_volume_retained": context["old_volume"]})
    emit("configuration_switched", run_id=args.run_id, services_started=False, old_volume_retained=True)


def main():
    os.umask(0o077)
    if len(sys.argv) > 1 and sys.argv[1] == "--client":
        return mysql_client_proxy(sys.argv[2:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "switch", "extract", "run-copy"))
    parser.add_argument("--project-dir")
    parser.add_argument("--backup-dir")
    parser.add_argument("--script-path")
    parser.add_argument("--run-id")
    parser.add_argument("--archive-name", default="mysql-data.tar.gz")
    parser.add_argument("--upgrade-timeout", type=int, default=900)
    parser.add_argument("--image", default="chris23144638/cecec:nas-secure-20261027-r2")
    args = parser.parse_args()
    require(60 <= args.upgrade_timeout <= 86400, "invalid_upgrade_timeout")
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(UpgradeBlocked("maintenance_interrupted")))
    try:
        if args.mode == "prepare": prepare(args)
        elif args.mode == "switch": switch(args)
        elif args.mode == "extract": extract_copy(args.archive_name)
        else: run_copy_upgrade()
        return 0
    except Exception as error:
        # Driver / restore errors may contain SQL or data. Keep them off task logs.
        code = str(error) if isinstance(error, UpgradeBlocked) else "upgrade_failed"
        cause_types = []
        locations = []
        database_error_code = None
        cause = error
        while cause is not None and len(cause_types) < 5:
            cause_types.append(type(cause).__name__)
            if cause.args and isinstance(cause.args[0], int):
                database_error_code = cause.args[0]
            if cause.__traceback__ is not None:
                import traceback
                locations.extend({"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                                 for frame in traceback.extract_tb(cause.__traceback__)[-3:])
            cause = cause.__cause__
        failure = {"status": "blocked", "error_code": code, "error_type": type(error).__name__, "cause_types": cause_types,
                   "database_error_code": database_error_code, "locations": locations}
        if args.mode == "run-copy":
            save("/upgrade/failure.json", failure)
        emit("blocked", error_code=code, error_type=type(error).__name__, cause_types=cause_types)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
