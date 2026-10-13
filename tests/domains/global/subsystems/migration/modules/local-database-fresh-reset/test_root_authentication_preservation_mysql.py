"""Real MySQL reset: root, random MFA and consumed recovery facts survive."""
import os
import secrets
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pymysql
import pytest
from cryptography.fernet import Fernet

from scripts import reset_fake_database as resetter
from scripts import reset_root_authentication as preservation
from subsystems.access import authentication_session as auth
from subsystems.access.totp import _totp_code, totp_step

pytestmark = pytest.mark.skipif(not os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE"), reason="requires disposable MySQL")


def test_root_and_authenticator_survive_real_schema_reset(monkeypatch, tmp_path):
    config = {"host": os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
              "port": int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
              "database": os.environ["LABOR_UNION_TEST_MYSQL_DATABASE"],
              "user": os.environ["LABOR_UNION_TEST_MYSQL_USER"],
              "password": os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
              "charset": "utf8mb4", "autocommit": False}
    assert config["host"] in {"127.0.0.1", "localhost"} and config["database"].startswith("lu_test_")
    connect = lambda: pymysql.connect(**config, cursorclass=pymysql.cursors.DictCursor)
    monkeypatch.setenv("ACCESS_CONTROL_TOTP_KEYRING", "random:" + Fernet.generate_key().decode())
    monkeypatch.setenv("ACCESS_CONTROL_TOTP_ACTIVE_KEY_VERSION", "random")
    username, password = "reset-root-" + secrets.token_hex(4), secrets.token_urlsafe(24)
    assembly, manifest = resetter._canonical_bootstrap_contract()
    resetter.rebuild_schema(assembly, manifest, config["database"], config=config)
    root_id = auth.bootstrap_root_admin(connection_factory=connect, username=username, password=password, display_name="Synthetic reset root")
    auth.create_admin_user(connection_factory=connect, username="synthetic-non-root", password=secrets.token_urlsafe(24), display_name="Not retained")
    challenge = auth.issue_password_login_challenge(username, password, connection_factory=connect)
    assert isinstance(challenge, auth.MfaEnrollmentChallenge)
    seed = parse_qs(urlparse(challenge.provisioning_uri).query)["secret"][0]
    step = totp_step(datetime.now(timezone.utc))
    recovery = auth.complete_mfa_enrollment(connection_factory=connect, challenge_id=challenge.challenge_id,
                                          challenge_token=challenge.challenge_token, totp_code=_totp_code(seed, step))
    login = auth.issue_password_login_challenge(username, password, connection_factory=connect)
    recovery_code = recovery[0]
    auth.complete_password_login_challenge(connection_factory=connect, challenge_id=login.challenge_id,
                                          challenge_token=login.challenge_token, factor_code=recovery_code)
    # Required FK parent and unrelated data are explicit disposable fixtures.
    c = connect()
    try:
        with c.cursor() as cursor:
            cursor.execute("INSERT INTO line_users(line_user_id) VALUES ('synthetic-root-parent')")
            cursor.execute("UPDATE admin_users SET linked_line_user_id='synthetic-root-parent' WHERE id=%s", (root_id,))
            cursor.execute("CREATE TABLE reset_business_sentinel(id INT PRIMARY KEY)")
            cursor.execute("INSERT INTO reset_business_sentinel VALUES (1)")
        c.commit()
    finally:c.close()
    c = connect()
    try:
        with pytest.raises(preservation.RootPreservationError, match="stop API"):
            preservation.capture_root_authentication(config)
    finally:c.close()
    before = preservation.capture_root_authentication(config)
    backup = tmp_path / "root.encrypted.json"
    preservation.save_root_authentication(before, config, backup)
    resetter.rebuild_schema(assembly, manifest, config["database"], config=config)
    # The durable artifact alone can recover authentication after destructive DDL.
    recovered = preservation.load_root_authentication(backup, config)
    result = preservation.restore_root_authentication(recovered, config)
    assert result["status"] == "preserved"
    if preservation.capture_root_authentication(config) != before:
        pytest.fail("root facts changed across reset", pytrace=False)
    c = connect()
    try:
        with c.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM admin_sessions")
            assert cursor.fetchone()["count"] == 0
            cursor.execute("SELECT COUNT(*) AS count FROM admin_users")
            assert cursor.fetchone()["count"] == 1
            cursor.execute("SHOW TABLES LIKE 'reset_business_sentinel'")
            assert cursor.fetchone() is None
    finally:c.close()
    login = auth.issue_password_login_challenge(username, password, connection_factory=connect)
    assert isinstance(login, auth.PasswordLoginChallenge)
    rejected = auth.complete_password_login_challenge(connection_factory=connect, challenge_id=login.challenge_id,
                                                     challenge_token=login.challenge_token, factor_code=recovery_code)
    assert rejected is None
    valid_code = _totp_code(seed, max(step + 1, totp_step(datetime.now(timezone.utc))))
    verified = auth.complete_password_login_challenge(connection_factory=connect, challenge_id=login.challenge_id,
                                                     challenge_token=login.challenge_token, factor_code=valid_code)
    assert auth.get_admin_session(verified[0], connection_factory=connect).is_root
