"""GUI-managed NAS runtime with isolated API identities and machine TLS."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import ipaddress
import os
from pathlib import Path
import re
import secrets
import sys

from dotenv import dotenv_values

from infrastructure.mysql.nas_permissions import account_names, PROFILES
from infrastructure.runtime.worker_credentials import prepare_credentials, SERVICES
from scripts import nas_appliance, nas_test_runtime


SETTINGS = Path("/settings")
LINE_SETTINGS = Path("/line-settings")
PROFILES_ROOT = Path("/profiles")
WORKERS = Path("/workers")
API_TLS = Path("/api-tls")
CA = Path("/private-ca")
DB_CA = Path("/db-ca")
LINE_CONFIG = Path("/line-config")
FILE_ROOTS = (Path("/controlled-files"), Path("/line-media"), Path("/knowledge-data"))


def _write(path, value, mode=0o400):
    nas_test_runtime._write(path, value, mode)
    os.chown(path, 1000, -1)


def _management_certificate_names():
    from cryptography import x509
    names = [x509.DNSName("management-api")]
    hostname = os.getenv("NAS_MANAGEMENT_HOSTNAME", "").strip()
    if hostname:
        if (len(hostname) > 253 or not all(re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
                                         for label in hostname.split("."))):
            raise ValueError("NAS_MANAGEMENT_HOSTNAME must be a hostname without scheme, port or path")
        if hostname != "management-api":
            names.append(x509.DNSName(hostname))
    address = os.getenv("NAS_BIND_IP", "").strip()
    if address:
        parsed = ipaddress.IPv4Address(address)
        if parsed.is_unspecified or parsed.is_multicast:
            raise ValueError("NAS_BIND_IP must be a specific NAS IPv4 address")
        names.append(x509.IPAddress(parsed))
    return names


def _prepare_api_tls(management_names=None):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    management_names = management_names if management_names is not None else _management_certificate_names()
    now = datetime.now(timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Labor Union private API CA")])
    ca_cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=90)).add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
            encipher_only=None, decipher_only=None), critical=True)
        .sign(ca_key, hashes.SHA256()))
    _write(CA / "ca.pem", ca_cert.public_bytes(serialization.Encoding.PEM), 0o444)
    for service in ("management-api", "line-api"):
        key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, service)])
        cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=90))
            .add_extension(x509.SubjectAlternativeName(management_names if service == "management-api"
                                                      else [x509.DNSName(service)]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))
        _write(API_TLS / service / "server-cert.pem", cert.public_bytes(serialization.Encoding.PEM), 0o444)
        _write(API_TLS / service / "server-key.pem", key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))


def initialize():
    from scripts.compact_fresh_schema import load_compact_plan
    from subsystems.line.configuration_store import CONFIG_FILES
    # A stale generated baseline must stop before creating files or database volumes.
    load_compact_plan()
    marker = SETTINGS / "security-prepared.json"
    if marker.exists():
        expected = [SETTINGS / "security.json", LINE_SETTINGS / "app.env", CA / "ca.pem", DB_CA / "ca.pem",
                    nas_appliance.BOOTSTRAP / "00-client-charset.cnf",
                    *(LINE_CONFIG / filename for filename in CONFIG_FILES.values()),
                    WORKERS / "api/verifiers.json", *(PROFILES_ROOT / p / "password" for p in PROFILES),
                    *(WORKERS / s / "token" for s in SERVICES),
                    *(API_TLS / s / file for s in ("management-api", "line-api") for file in ("server-cert.pem", "server-key.pem"))]
        if json.loads(marker.read_text()) != {"format": "nas-security/v1"} or not all(p.is_file() for p in expected):
            raise ValueError("partial NAS security settings; existing files preserved")
        print("Existing NAS security settings preserved.")
        return
    if (SETTINGS / "prepared.json").exists() or any(any(p.iterdir()) for p in
        [LINE_SETTINGS, *PROFILES_ROOT.glob("*"), *WORKERS.glob("*"), *API_TLS.glob("*"), CA, DB_CA,
         LINE_CONFIG, *FILE_ROOTS] if p.is_dir()):
        raise ValueError("existing installation requires preserve-data security upgrade; refusing to overwrite")
    management_names = _management_certificate_names()
    nas_appliance.initialize()
    # Docker's mysql CLI otherwise chooses its charset from the image locale.
    # The same bootstrap volume is mounted into /etc/mysql/conf.d before DB init.
    _write(nas_appliance.BOOTSTRAP / "00-client-charset.cnf",
           Path("/opt/nas/init/mysql-client.cnf").read_bytes(), 0o444)
    for filename in CONFIG_FILES.values():
        _write(LINE_CONFIG / filename, (Path("/app/config") / filename).read_bytes(), 0o640)
    os.chown(LINE_CONFIG, 1000, -1)
    LINE_CONFIG.chmod(0o750)
    for folder in FILE_ROOTS:
        os.chown(folder, 1000, -1)
        folder.chmod(0o750)
    _write(DB_CA / "ca.pem", (nas_appliance.SERVER_TLS / "ca.pem").read_bytes(), 0o444)
    names = account_names(nas_test_runtime.DATABASE)
    for profile in PROFILES:
        _write(PROFILES_ROOT / profile / "password", secrets.token_urlsafe(40) + "\n")
    prepare_credentials(WORKERS, services=SERVICES)
    for path in WORKERS.rglob("*"):
        os.chown(path, 1000, -1)
    _prepare_api_tls(management_names)
    _write(nas_appliance.DATA / "management-api-ca.crt", (CA / "ca.pem").read_bytes(), 0o444)
    common = ("APP_ENV=production\nDEPLOYMENT_PROFILE=nas\nACCESS_CONTROL_PROFILE=production\nENABLE_ADMIN_AUTH=true\n"
        "LINE_WEBHOOK_RUNTIME_MODE=canonical\nLINE_WORKER_RUNTIME_MODE=canonical\nLIFF_REQUIRE_ID_TOKEN=true\n"
        f"DB_HOST=db\nDB_PORT=3306\nDB_DATABASE={nas_test_runtime.DATABASE}\nDB_SSL_MODE=verify_identity\n"
        "DB_SSL_CA=/run/db-ca/ca.pem\nREDIS_URL=redis://redis:6379/0\n"
        "INTERNAL_SERVICE_AUTH_MODE=nas_service_token\nINTERNAL_SERVICE_CREDENTIALS_FILE=/run/worker-verifiers/verifiers.json\n"
        "CONTROLLED_FILE_STORAGE_ROOT=/data/controlled-files\nMEDIA_STORAGE_ROOT=/data/media\n")
    common += "LINE_CONFIG_ROOT=/run/line-config\nKNOWLEDGE_CHROMA_PATH=/data/knowledge\n"
    old = dotenv_values(SETTINGS / "app.env")
    retained = {key: value for key, value in old.items() if key.startswith(("ACCESS_CONTROL_TOTP_", "ANOMALY_ISSUE_"))
                or key in {"ADMIN_ENTRY_TARGET_STATE_PATH", "CONTRACT_DOCUMENT_ARCHIVE_ROOT"}}
    (SETTINGS / "app.env").write_text(common + f"DB_USER={names['management']}\nDB_PASSWORD_FILE=/run/db-management/password\n"
        f"DB_ACCESS_USER={names['access']}\nDB_ACCESS_PASSWORD_FILE=/run/db-access/password\n"
        f"DB_MAINTENANCE_USER={names['maintenance']}\nDB_MAINTENANCE_PASSWORD_FILE=/run/db-maintenance/password\n"
        f"CONTRACT_FINAL_PREVIEW_TOKEN_SECRET={secrets.token_urlsafe(40)}\n"
        + "".join(f"{key}={value}\n" for key, value in retained.items()), encoding="utf-8")
    _write(LINE_SETTINGS / "app.env", common + f"DB_USER={names['line']}\nDB_PASSWORD_FILE=/run/db-line/password\n")
    _write(SETTINGS / "security.json", json.dumps({"format": "nas-db-security-settings/v1", "host": "db",
        "database": nas_test_runtime.DATABASE, "admin_user": "root", "admin_password_file": "/mysql-secrets/root-password",
        "ca_file": "/run/db-ca/ca.pem", "password_files": {p: str(PROFILES_ROOT / p / "password") for p in PROFILES}}))
    _write(marker, json.dumps({"format": "nas-security/v1"}) + "\n")
    print("NAS service credentials and private TLS prepared; no secrets displayed.")


def serve(service):
    settings = SETTINGS if service == "management-api" else LINE_SETTINGS
    for key, value in dotenv_values(settings / "app.env").items():
        if value is not None:
            os.environ[key] = value
    nas_appliance._drop_privileges()
    nas_test_runtime.require_login_mode()
    from scripts.compact_fresh_schema import load_compact_plan
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.nas_permissions import verify_runtime_permissions
    schema_plan = load_compact_plan()
    checks = ((None, "management"), ("access", "access"), ("maintenance", "maintenance")) if service == "management-api" else ((None, "line"),)
    for connection_profile, permission_profile in checks:
        connection = get_connection(connection_profile)
        try:
            verify_runtime_permissions(connection, permission_profile, nas_test_runtime.DATABASE,
                expected_tables=schema_plan["expected"]["tables"], expected_views=schema_plan["expected"]["views"])
        finally:
            connection.close()
    factory = "api.nas_apps:management_app" if service == "management-api" else "api.nas_apps:line_app"
    os.execvp("python", ["python", "-m", "uvicorn", factory, "--factory", "--host", "0.0.0.0", "--port", "8443",
        "--workers", "1", "--ssl-certfile", "/run/api-tls/server-cert.pem", "--ssl-keyfile", "/run/api-tls/server-key.pem",
        "--proxy-headers", "--forwarded-allow-ips", nas_appliance._trusted_proxies()])


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "management-api"
    try:
        if command == "initialize":
            initialize()
        elif command in {"management-api", "line-api"}:
            serve(command)
        else:
            raise ValueError("unknown NAS runtime operation")
        return 0
    except Exception as error:
        print(f"NAS security startup blocked ({type(error).__name__}); existing state preserved.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
