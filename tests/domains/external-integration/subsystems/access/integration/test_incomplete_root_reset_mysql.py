"""Real MySQL: reset only unused root facts, preserve business data, then start over."""
import hashlib
import os
import secrets
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pymysql
import pytest
from cryptography.fernet import Fernet

from subsystems.access import authentication_session as auth
from subsystems.access.incomplete_root_reset import (
    IncompleteRootResetError, preview_incomplete_root_reset, reset_incomplete_root_setup,
)

pytestmark = pytest.mark.skipif(not os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE"), reason="requires a fresh explicit disposable MySQL database")


def connection():
    database = os.environ["LABOR_UNION_TEST_MYSQL_DATABASE"]
    host = os.environ["LABOR_UNION_TEST_MYSQL_HOST"]
    assert host in {"127.0.0.1", "localhost"} and database.startswith("lu_test_")
    return pymysql.connect(host=host, port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"], password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=database, charset="utf8mb4", autocommit=False, cursorclass=pymysql.cursors.DictCursor)


def execute(sql, parameters=None):
    conn = connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, parameters)
            result = cursor.fetchall() if cursor.description else cursor.lastrowid
        conn.commit()
        return result
    finally:
        conn.close()


def business_snapshot(*, include_auth=False):
    conn = connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT TABLE_NAME AS name FROM information_schema.tables WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE'")
            tables = [row["name"] for row in cursor.fetchall() if include_auth or row["name"] not in {
                "admin_users", "admin_root_account", "admin_totp_factors", "admin_mfa_enrollment_challenges",
                "admin_password_login_challenges", "admin_audit_logs"}]
            snapshot = {}
            for table in tables:
                cursor.execute(f"SELECT * FROM `{table}`")
                snapshot[table] = hashlib.sha256(repr(sorted(repr(row) for row in cursor.fetchall())).encode()).hexdigest()
            return snapshot
    finally:
        conn.close()


def test_reset_legacy_and_pending_root_then_protect_used_accounts(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ACCESS_CONTROL_TOTP_KEYRING", "v1:" + Fernet.generate_key().decode())
    monkeypatch.setenv("ACCESS_CONTROL_TOTP_ACTIVE_KEY_VERSION", "v1")
    database = os.environ["LABOR_UNION_TEST_MYSQL_DATABASE"]
    assert not execute("SELECT id FROM admin_users")
    from scripts import reset_incomplete_root_setup as cli
    monkeypatch.setattr(cli, "_database_config_from_environment", lambda: {"host": "127.0.0.1", "database": database})
    monkeypatch.setattr(cli, "get_access_control_connection_factory", lambda: connection)
    password = secrets.token_urlsafe(24)

    def unchanged_after_refusal(code, operation):
        before = business_snapshot(include_auth=True)
        with pytest.raises(IncompleteRootResetError, match=code):
            operation()
        assert before == business_snapshot(include_auth=True)

    for legacy in (True, False):
        root = auth.bootstrap_root_admin(connection_factory=connection, username="reset-initial-root", password=password, display_name="Test root")
        if legacy:
            execute("DELETE FROM admin_mfa_enrollment_challenges WHERE admin_user_id=%s", (root.admin_user_id,))
            execute("DELETE FROM admin_totp_factors WHERE admin_user_id=%s", (root.admin_user_id,))
        before = business_snapshot()
        preview = preview_incomplete_root_reset(connection_factory=connection, target_database=database)
        assert preview.account_id == root.admin_user_id
        untouched = business_snapshot(include_auth=True)
        assert cli.main([]) == 0
        assert cli.main(["--apply"], confirm=lambda _: "cancel") == 1
        assert untouched == business_snapshot(include_auth=True)
        assert len(execute("SELECT id FROM admin_users")) == 1
        for target, account_id, version, code in (
            (database, preview.account_id, preview.version + 1, "admin_version_conflict"),
            (database, preview.account_id + 1, preview.version, "admin_version_conflict"),
            ("lu_test_wrong_target", preview.account_id, preview.version, "database_mismatch"),
        ):
            unchanged_after_refusal(code, lambda: reset_incomplete_root_setup(
                connection_factory=connection, target_database=target,
                expected_account_id=account_id, expected_version=version))
        assert cli.main(["--apply"], confirm=lambda _: f"RESET ROOT {database} {root.admin_user_id}") == 0
        assert not execute("SELECT id FROM admin_users")
        assert not execute("SELECT admin_user_id FROM admin_root_account")
        assert not execute("SELECT id FROM admin_totp_factors")
        assert not execute("SELECT id FROM admin_mfa_enrollment_challenges")
        assert before == business_snapshot()
        assert execute("SELECT id FROM admin_audit_logs WHERE action='admin.root.incomplete_setup_reset'")

    root = auth.bootstrap_root_admin(connection_factory=connection, username="correct-new-root", password=password, display_name="New root")
    # An account with prior credential/security changes is not a pristine install.
    execute("UPDATE admin_users SET access_control_version=2 WHERE id=%s", (root.admin_user_id,))
    unchanged_after_refusal("root_already_used", lambda: reset_incomplete_root_setup(
        connection_factory=connection, target_database=database,
        expected_account_id=root.admin_user_id, expected_version=2))
    execute("UPDATE admin_users SET access_control_version=1 WHERE id=%s", (root.admin_user_id,))
    execute("UPDATE admin_users SET last_login_at=UTC_TIMESTAMP() WHERE id=%s", (root.admin_user_id,))
    unchanged_after_refusal("root_already_used", lambda: reset_incomplete_root_setup(
        connection_factory=connection, target_database=database,
        expected_account_id=root.admin_user_id, expected_version=1))
    execute("UPDATE admin_users SET last_login_at=NULL WHERE id=%s", (root.admin_user_id,))

    # The CLI must re-read after confirmation; a concurrent security change wins.
    after_confirmation = {}
    def change_during_confirmation(_):
        execute("UPDATE admin_users SET access_control_version=2 WHERE id=%s", (root.admin_user_id,))
        after_confirmation.update(business_snapshot(include_auth=True))
        return f"RESET ROOT {database} {root.admin_user_id}"
    assert cli.main(["--apply"], confirm=change_during_confirmation) == 2
    assert after_confirmation == business_snapshot(include_auth=True)
    execute("UPDATE admin_users SET access_control_version=1 WHERE id=%s", (root.admin_user_id,))
    child = execute("INSERT INTO admin_users (username,password_hash,display_name,role) VALUES (%s,%s,%s,'system_admin')",
                    ("other-test-admin", auth.hash_admin_password(password), "Other"))
    unchanged_after_refusal("other_admins_exist", lambda: reset_incomplete_root_setup(
        connection_factory=connection, target_database=database,
        expected_account_id=root.admin_user_id, expected_version=1))
    execute("DELETE FROM admin_users WHERE id=%s", (child,))
    session = execute("INSERT INTO admin_sessions (admin_user_id,session_token_hash,expires_at) VALUES (%s,%s,DATE_ADD(UTC_TIMESTAMP(),INTERVAL 1 HOUR))",
                      (root.admin_user_id, "a" * 64))
    unchanged_after_refusal("root_already_used", lambda: reset_incomplete_root_setup(
        connection_factory=connection, target_database=database,
        expected_account_id=root.admin_user_id, expected_version=1))
    execute("DELETE FROM admin_sessions WHERE id=%s", (session,))
    execute("INSERT INTO knowledge_items (source_uri,source_trust_tier,title,content,content_digest,created_by_admin_user_id) "
            "VALUES ('test:initial-root-reference','internal_policy','Test','Test',%s,%s)", ("b" * 64, root.admin_user_id))
    unchanged_after_refusal("root_has_business_references", lambda: reset_incomplete_root_setup(
        connection_factory=connection, target_database=database,
        expected_account_id=root.admin_user_id, expected_version=1))
    from subsystems.access.totp import _totp_code, totp_step
    secret = parse_qs(urlparse(root.enrollment.provisioning_uri).query)["secret"][0]
    auth.complete_mfa_enrollment(connection_factory=connection, challenge_id=root.enrollment.challenge_id,
        challenge_token=root.enrollment.challenge_token, totp_code=_totp_code(secret, totp_step(datetime.now(timezone.utc))))
    # Binding legitimately creates recovery codes and a committed security alert.
    # The rejected reset must preserve the state after that owner operation.
    unchanged_after_refusal("root_already_enrolled", lambda: reset_incomplete_root_setup(
        connection_factory=connection, target_database=database,
        expected_account_id=root.admin_user_id, expected_version=1))
    before = business_snapshot(include_auth=True)
    def must_not_prompt(_):
        raise AssertionError("an enrolled root must be refused before confirmation")
    assert cli.main(["--apply"], confirm=must_not_prompt) == 2
    assert before == business_snapshot(include_auth=True)
    execute("UPDATE admin_totp_factors SET factor_state='revoked',revoked_at=UTC_TIMESTAMP(6) WHERE admin_user_id=%s", (root.admin_user_id,))
    unchanged_after_refusal("root_already_enrolled", lambda: reset_incomplete_root_setup(
        connection_factory=connection, target_database=database,
        expected_account_id=root.admin_user_id, expected_version=1))
