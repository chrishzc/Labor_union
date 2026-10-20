"""NAS preview-only setup and login-enforced runtime; never runs LINE work cycles."""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import getpass
import os
from pathlib import Path
import secrets


DATABASE = "lu_test_nas_preview"


def _write(path: Path, content: str | bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(content.encode("utf-8") if isinstance(content, str) else content)
    path.chmod(mode)


def prepare(settings: Path = Path("/settings"), data: Path = Path("/data")) -> None:
    # Never replace credentials, keys, entry state or an existing installation.
    if any(settings.iterdir()) or any(data.iterdir()):
        raise ValueError("settings/data are not empty; refusing to overwrite")
    from cryptography import x509
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from infrastructure.file.admin_entry_target_store import FileAdminEntryTargetStore
    from subsystems.access.admin_entry_target_control import make_initial_state

    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Union NAS preview CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=90))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
          .sign(ca_key, hashes.SHA256()))
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    server = (x509.CertificateBuilder()
              .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "db")]))
              .issuer_name(ca_name).public_key(server_key.public_key())
              .serial_number(x509.random_serial_number())
              .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=90))
              .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
              .add_extension(x509.SubjectAlternativeName([x509.DNSName("db")]), critical=False)
              .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
              .sign(ca_key, hashes.SHA256()))
    _write(settings / "tls/ca.pem", ca.public_bytes(serialization.Encoding.PEM), 0o644)
    _write(settings / "tls/server-cert.pem", server.public_bytes(serialization.Encoding.PEM), 0o644)
    # Parent settings is root-only on the NAS; only MySQL mounts this key directory.
    _write(settings / "tls/server-key.pem", server_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()), 0o644)
    password = secrets.token_urlsafe(32)
    _write(settings / "mysql.env", f"MYSQL_DATABASE={DATABASE}\nMYSQL_USER=nas_app\n"
           f"MYSQL_PASSWORD={password}\nMYSQL_ROOT_PASSWORD={secrets.token_urlsafe(40)}\n")
    _write(settings / "app.env", "APP_ENV=production\nACCESS_CONTROL_PROFILE=production\n"
           "ENABLE_ADMIN_AUTH=true\nDB_HOST=db\nDB_PORT=3306\nDB_USER=nas_app\n"
           f"DB_DATABASE={DATABASE}\nDB_PASSWORD={password}\nDB_SSL_MODE=verify_identity\n"
           "DB_SSL_CA=/run/nas-ca.pem\nREDIS_URL=redis://redis:6379/0\n"
           f"ACCESS_CONTROL_TOTP_KEYRING=v1:{Fernet.generate_key().decode()}\n"
           "ACCESS_CONTROL_TOTP_ACTIVE_KEY_VERSION=v1\n"
           f"ANOMALY_ISSUE_IDENTITY_KEY_V1={secrets.token_urlsafe(32)}\n"
           "ADMIN_ENTRY_TARGET_STATE_PATH=/data/admin-entry-target-state.json\n"
           "CONTROLLED_FILE_STORAGE_ROOT=/data/controlled-files\n"
           "MEDIA_STORAGE_ROOT=/data/media\nCONTRACT_DOCUMENT_ARCHIVE_ROOT=/data/contracts\n"
           "INTERNAL_SERVICE_AUTH_MODE=nas_service_token\n"
           "INTERNAL_SERVICE_CREDENTIALS_FILE=/run/worker-verifiers/verifiers.json\n")
    _write(settings / "worker.env", "INTERNAL_API_BASE_URL=https://management-api:8443\n"
           "INTERNAL_SERVICE_AUTH_MODE=nas_service_token\n"
           "INTERNAL_SERVICE_TOKEN_FILE=/run/worker/token\n"
           "INTERNAL_API_CA_FILE=/run/private-ca/ca.pem\n")
    for name in ("controlled-files", "media", "contracts"):
        (data / name).mkdir()
    # Exact canonical entry-state owner; no invented/relaxed artifact state.
    FileAdminEntryTargetStore(data / "admin-entry-target-state.json").create(make_initial_state())
    for item in (data, *data.rglob("*")):
        os.chown(item, 1000, -1)
    print("Preview settings prepared. No secrets printed. TLS certificates expire in 90 days.")


def require_login_mode() -> None:
    if (os.getenv("APP_ENV") != "production"
            or os.getenv("ACCESS_CONTROL_PROFILE") != "production"
            or os.getenv("ENABLE_ADMIN_AUTH", "").lower() != "true"):
        raise ValueError("NAS preview requires production/login mode")
    if os.getenv("DB_DATABASE") != DATABASE or os.getenv("DB_HOST") != "db":
        raise ValueError("NAS preview is restricted to its isolated db service/database")
    if os.getenv("DB_SSL_MODE") != "verify_identity":
        raise ValueError("NAS preview requires verified database TLS")


def verify_schema() -> None:
    import pymysql
    from infrastructure.mysql.mysql_adapter import get_connection
    from scripts.compact_fresh_schema import load_compact_plan
    from scripts.verify_validation_schema_manifest import verify_database_objects
    plan = load_compact_plan()
    conn = get_connection()
    try:
        # The manifest verifier consumes tuple rows; the application adapter's
        # default DictCursor is intended for business queries instead.
        with conn.cursor(pymysql.cursors.Cursor) as cursor:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            # The runtime user deliberately lacks TRIGGER/DDL privileges, so
            # MySQL does not expose trigger metadata to this principal.
            visible_expected = {**plan["expected"], "triggers": set()}
            errors = verify_database_objects(cursor, DATABASE, visible_expected)
        if errors:
            raise ValueError("preview schema mismatch; refusing startup")
    finally:
        conn.close()


@asynccontextmanager
async def _management_lifespan(_):
    # Reuse the canonical catalog bootstrap. Production LINE preflight belongs
    # to the full LINE runtime, whose routes are absent from this test entry.
    from api.dependencies.knowledge_retrieval import ensure_builtin_knowledge_catalog
    ensure_builtin_knowledge_catalog()
    yield


def management_preview_app():
    """Management-only NAS entry; no fake LINE credentials or public webhook."""
    require_login_mode()
    from api.main import app, line_router
    line_endpoints = {route.endpoint for route in line_router.routes
                      if hasattr(route, "endpoint")}
    def is_line_route(route):
        # The installed FastAPI retains include_router branches lazily. Inspect
        # their original endpoints before its first request compiles the routes.
        branch = getattr(route, "original_router", None)
        if branch is line_router:
            return True
        return any(getattr(item, "endpoint", None) in line_endpoints
                   or getattr(getattr(item, "endpoint", None), "__module__", "").startswith("api.routes.line_")
                   or getattr(item, "path", "").startswith(("/api/line/", "/api/v1/line/", "/webhook"))
                   for item in (branch.routes if branch is not None else [route]))
    app.router.routes[:] = [route for route in app.router.routes if not is_line_route(route)]
    app.router.lifespan_context = _management_lifespan
    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "serve", "bootstrap-admin"])
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
        return 0
    require_login_mode()
    verify_schema()
    if args.command == "bootstrap-admin":
        from infrastructure.mysql.mysql_adapter import get_connection
        from subsystems.access.authentication_session import bootstrap_root_admin
        username = input("Initial administrator username: ").strip()
        password = getpass.getpass("Password (not displayed): ")
        if len(password) < 16 or password != getpass.getpass("Confirm password: "):
            raise ValueError("passwords must match and contain at least 16 characters")
        bootstrap_root_admin(connection_factory=get_connection, username=username,
                             password=password, display_name="NAS test administrator")
        print("Administrator created. Complete MFA enrollment on first login.")
        return 0
    concurrency = int(os.getenv("API_CONCURRENCY", "8"))
    if not 2 <= concurrency <= 64:
        raise ValueError("API_CONCURRENCY must be between 2 and 64")
    os.execvp("python", ["python", "-m", "uvicorn", "scripts.nas_test_runtime:management_preview_app",
                         "--factory", "--host", "0.0.0.0",
                         "--port", "8080", "--workers", "1", "--limit-concurrency", str(concurrency),
                         "--timeout-keep-alive", "5"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # Provider/DB exceptions may embed connection details; never dump them.
        print(f"NAS preview blocked ({type(error).__name__}); check settings and guide.")
        raise SystemExit(2)
