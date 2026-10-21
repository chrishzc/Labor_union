"""Automatic, non-destructive startup for the single-project NAS preview image."""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket

from dotenv import dotenv_values

from scripts import nas_test_runtime

SETTINGS = Path("/settings")
DATA = Path("/data")
SERVER_TLS = Path("/server-tls")
MYSQL_SECRETS = Path("/mysql-secrets")
BOOTSTRAP = Path("/bootstrap")


def initialize() -> None:
    marker = SETTINGS / "prepared.json"
    expected = (SETTINGS / "app.env", SETTINGS / "worker.env", DATA / "nas-ca.pem",
                DATA / "admin-entry-target-state.json", SERVER_TLS / "ca.pem",
                SERVER_TLS / "server-cert.pem", SERVER_TLS / "server-key.pem",
                MYSQL_SECRETS / "root-password", MYSQL_SECRETS / "app-password",
                BOOTSTRAP / "10-fresh-schema.sql", BOOTSTRAP / "20-restrict-app.sql", BOOTSTRAP / "99-ready.sh")
    if marker.is_file():
        if json.loads(marker.read_text()) != {"format": "nas-web-setup/v1"} or not all(p.is_file() for p in expected):
            raise ValueError("installation state incomplete; no files changed")
        print("Existing NAS installation preserved.")
        return
    if any(any(folder.iterdir()) for folder in (SETTINGS, DATA, SERVER_TLS, MYSQL_SECRETS, BOOTSTRAP)):
        raise ValueError("existing or partial installation; refusing to overwrite")
    os.umask(0o022)
    SETTINGS.chmod(0o700)
    nas_test_runtime.prepare()
    database = dotenv_values(SETTINGS / "mysql.env")
    for name, value in (("root-password", database["MYSQL_ROOT_PASSWORD"]),
                        ("app-password", database["MYSQL_PASSWORD"])):
        target = MYSQL_SECRETS / name
        nas_test_runtime._write(target, value, 0o400)
        os.chown(target, 999, -1)
    for name in ("ca.pem", "server-cert.pem", "server-key.pem"):
        target = SERVER_TLS / name
        shutil.copyfile(SETTINGS / "tls" / name, target)
        target.chmod(0o400 if name == "server-key.pem" else 0o444)
        os.chown(target, 999, -1)
    shutil.copyfile(SETTINGS / "tls/ca.pem", DATA / "nas-ca.pem")
    os.chown(DATA / "nas-ca.pem", 1000, -1)
    (DATA / "nas-ca.pem").chmod(0o444)
    config = SETTINGS / "app.env"
    config.write_text(config.read_text().replace("/run/nas-ca.pem", "/data/nas-ca.pem"), encoding="utf-8")
    config.chmod(0o600)
    # These generated staging copies have no remaining consumer. The API never
    # receives the database root password or the database server private key.
    (SETTINGS / "mysql.env").unlink()
    (SETTINGS / "tls/server-key.pem").unlink()
    for name in ("10-fresh-schema.sql", "20-restrict-app.sql", "99-ready.sh"):
        target = BOOTSTRAP / name
        shutil.copyfile(Path("/opt/nas/init") / name, target)
        target.chmod(0o444)
    nas_test_runtime._write(marker, json.dumps({"format": "nas-web-setup/v1"}) + "\n")
    print("NAS installation initialized. Open the configured HTTPS management URL.")


def _drop_privileges() -> None:
    os.setgroups([])
    os.setgid(1000)
    os.setuid(1000)
    os.environ["HOME"] = "/home/app"


def _trusted_proxies() -> str:
    # DSM connects from the host's bridge gateway. Do not trust forwarded
    # headers from every container or from arbitrary LAN clients.
    addresses = {"127.0.0.1"}
    # Only explicit connector addresses; never trust a whole LAN or '*'.
    configured = os.getenv("NAS_TRUSTED_PROXY_IPS", "").strip()
    if configured:
        for value in configured.split(","):
            try:
                address = ipaddress.ip_address(value.strip())
            except ValueError:
                raise ValueError("NAS_TRUSTED_PROXY_IPS requires literal proxy IP addresses") from None
            if address.is_unspecified or address.is_multicast:
                raise ValueError("NAS_TRUSTED_PROXY_IPS requires unicast proxy IP addresses")
            addresses.add(str(address))
    for line in Path("/proc/net/route").read_text().splitlines()[1:]:
        fields = line.split()
        if fields[1] == "00000000" and fields[2] != "00000000":
            addresses.add(socket.inet_ntoa(bytes.fromhex(fields[2])[::-1]))
    return ",".join(sorted(addresses))


def serve() -> None:
    for key, value in dotenv_values(SETTINGS / "app.env").items():
        if value is not None:
            os.environ[key] = value
    proxies = _trusted_proxies()
    _drop_privileges()
    nas_test_runtime.require_login_mode()
    nas_test_runtime.verify_schema()
    os.execvp("python", ["python", "-m", "uvicorn", "api.routes.nas_setup:create_app", "--factory",
        "--host", "0.0.0.0", "--port", "8080", "--workers", "1",
        "--timeout-keep-alive", "5", "--proxy-headers", "--forwarded-allow-ips", proxies])


def line_check() -> None:
    # Load the existing worker and CLI only; no credentials, handshake or cycle.
    _drop_privileges()
    os.execvp("python", ["python", "-m", "scripts.run_line_worker", "--help"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("initialize", "serve", "line-check"), default="serve", nargs="?")
    command = parser.parse_args().command
    try:
        {"initialize": initialize, "serve": serve, "line-check": line_check}[command]()
    except Exception as error:
        print(f"NAS startup blocked ({type(error).__name__}). Check configuration; no credentials displayed.")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
