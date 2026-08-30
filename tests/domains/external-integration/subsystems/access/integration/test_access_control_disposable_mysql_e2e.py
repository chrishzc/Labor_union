"""
File: test_access_control_disposable_mysql_e2e.py
Description: 在明確指定的 disposable MySQL 驗證帳號中心安全狀態與 MFA 登入閉環。
"""

from __future__ import annotations

import asyncio
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pymysql
import pytest
from cryptography.fernet import Fernet

DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


@pytest.fixture(autouse=True)
def _disposable_access_control_database(monkeypatch):
    """Use an already bootstrapped disposable schema and an ephemeral TOTP encryption key."""
    assert DATABASE is not None and DATABASE.startswith("lu_test_")
    monkeypatch.setenv("ACCESS_CONTROL_TOTP_KEYRING", f"v1:{Fernet.generate_key().decode('ascii')}")
    monkeypatch.setenv("ACCESS_CONTROL_TOTP_ACTIVE_KEY_VERSION", "v1")
    from subsystems.access import authentication_session

    monkeypatch.setattr(authentication_session, "get_connection", _connection)


def test_account_center_security_transitions_are_atomic_and_root_is_protected(monkeypatch) -> None:
    from subsystems.access import authentication_session

    run_id = secrets.token_hex(6)
    root_username = f"root-{run_id}"
    child_username = f"child-{run_id}"
    root, root_secret, root_token = _bootstrap_and_enroll(root_username)
    from api.routes import admin_auth

    assert admin_auth.me(root).data.username == root_username
    assert asyncio.run(admin_auth.logout(f"Bearer {root_token}", root)).data.logged_out
    assert authentication_session.get_admin_session(root_token) is None
    replay_challenge = authentication_session.issue_password_login_challenge(
        root_username, "Root-password-123"
    )
    assert isinstance(replay_challenge, authentication_session.PasswordLoginChallenge)
    from subsystems.access.totp import _totp_code

    assert authentication_session.complete_password_login_challenge(
        challenge_id=replay_challenge.challenge_id,
        challenge_token=replay_challenge.challenge_token,
        factor_code=_totp_code(root_secret, _last_factor_step(root.id)),
    ) is None
    wrong_factor_challenge = authentication_session.issue_password_login_challenge(
        root_username, "Root-password-123"
    )
    assert isinstance(wrong_factor_challenge, authentication_session.PasswordLoginChallenge)
    assert authentication_session.complete_password_login_challenge(
        challenge_id=wrong_factor_challenge.challenge_id,
        challenge_token=wrong_factor_challenge.challenge_token,
        factor_code="000000",
    ) is None
    expired_challenge = authentication_session.issue_password_login_challenge(
        root_username, "Root-password-123"
    )
    assert isinstance(expired_challenge, authentication_session.PasswordLoginChallenge)
    original_now = authentication_session._utc_now_naive
    monkeypatch.setattr(
        authentication_session,
        "_utc_now_naive",
        lambda: expired_challenge.expires_at.replace(tzinfo=None) + timedelta(seconds=1),
    )
    assert authentication_session.complete_password_login_challenge(
        challenge_id=expired_challenge.challenge_id,
        challenge_token=expired_challenge.challenge_token,
        factor_code="000000",
    ) is None
    monkeypatch.setattr(authentication_session, "_utc_now_naive", original_now)
    child = authentication_session.create_account_center_user(
        actor=root,
        username=child_username,
        password="Child-password-123",
        display_name="Child",
        reason="E2E create",
        idempotency_key="create-child",
    )
    child_principal, child_secret, child_token = _enroll_and_login(child_username, "Child-password-123")
    assert child_principal.id == child.id

    authentication_session.set_account_center_enabled(
        actor=root, account_id=child.id, enabled=False, reason="E2E disable",
        expected_version=1, idempotency_key="disable-child",
    )
    assert authentication_session.get_admin_session(child_token) is None
    assert _user_state(child.id) == (False, 2)
    assert authentication_session.issue_password_login_challenge(
        child_username, "Child-password-123", source_identifier="disabled-account-e2e"
    ) is None
    from subsystems.access.security_alert_outbox import consume_security_alert_outbox
    from subsystems.anomalies.system_alert_projection import upsert_system_alert

    projection_connection = _connection()
    try:
        projection = consume_security_alert_outbox(
            projection_connection,
            project_alert=upsert_system_alert,
        )
    finally:
        projection_connection.close()
    assert projection.delivered_count >= 3
    assert projection.failed_count == 0
    assert _security_alert_counts() == (projection.delivered_count, projection.delivered_count)

    authentication_session.set_account_center_enabled(
        actor=root, account_id=child.id, enabled=True, reason="E2E enable",
        expected_version=2, idempotency_key="enable-child",
    )
    password_reset_token = _seed_active_session(child.id)
    authentication_session.reset_account_center_password(
        actor=root, account_id=child.id, password="Child-password-456", reason="E2E password",
        expected_version=3, idempotency_key="password-child",
    )
    assert authentication_session.get_admin_session(password_reset_token) is None
    assert authentication_session.issue_password_login_challenge(child_username, "Child-password-123") is None
    mfa_reset_token = _seed_active_session(child.id)

    authentication_session.reset_account_center_mfa(
        actor=root, account_id=child.id, reason="E2E MFA lost", expected_version=4,
        idempotency_key="mfa-child",
    )
    assert authentication_session.get_admin_session(mfa_reset_token) is None
    enrollment = authentication_session.issue_password_login_challenge(child_username, "Child-password-456")
    assert isinstance(enrollment, authentication_session.MfaEnrollmentChallenge)
    with pytest.raises(ValueError, match="root 帳號受保護"):
        authentication_session.set_account_center_enabled(
            actor=root, account_id=root.id, enabled=False, reason="must fail",
            expected_version=1, idempotency_key="root-disable",
        )

    before = _user_state(child.id)
    original_audit_recorder = authentication_session._record_admin_audit_with_cursor
    monkeypatch.setattr(
        authentication_session, "_record_admin_audit_with_cursor",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("audit unavailable")),
    )
    with pytest.raises(RuntimeError, match="audit unavailable"):
        authentication_session.set_account_center_enabled(
            actor=root, account_id=child.id, enabled=False, reason="must rollback",
            expected_version=5, idempotency_key="audit-rollback",
    )
    assert _user_state(child.id) == before
    monkeypatch.setattr(authentication_session, "_record_admin_audit_with_cursor", original_audit_recorder)
    for _ in range(5):
        assert authentication_session.issue_password_login_challenge(
            f"unknown-{run_id}", "incorrect-password", source_identifier="e2e-rate-limit"
        ) is None
    with pytest.raises(authentication_session.AdminLoginRateLimitedError):
        authentication_session.issue_password_login_challenge(
            f"unknown-{run_id}", "incorrect-password", source_identifier="e2e-rate-limit"
        )
    assert root_secret


def _bootstrap_and_enroll(username: str):
    from subsystems.access import authentication_session

    password = "Root-password-123"
    root_id = authentication_session.bootstrap_root_admin(
        username=username, password=password, display_name="Root"
    )
    principal, secret, token = _enroll_and_login(username, password)
    assert principal.id == root_id and principal.is_root
    return principal, secret, token


def _enroll_and_login(username: str, password: str):
    from subsystems.access import authentication_session
    from subsystems.access.totp import _totp_code, totp_step

    enrollment = authentication_session.issue_password_login_challenge(username, password)
    assert isinstance(enrollment, authentication_session.MfaEnrollmentChallenge)
    secret = parse_qs(urlparse(enrollment.provisioning_uri).query)["secret"][0]
    authentication_session.complete_mfa_enrollment(
        challenge_id=enrollment.challenge_id,
        challenge_token=enrollment.challenge_token,
        totp_code=_totp_code(secret, totp_step(datetime.now(timezone.utc))),
    )
    return _login_with_secret(username, password, secret)


def _login_with_secret(username: str, password: str, secret: str, *, step_offset: int = 1):
    from subsystems.access import authentication_session
    from subsystems.access.totp import _totp_code, totp_step

    challenge = authentication_session.issue_password_login_challenge(username, password)
    assert isinstance(challenge, authentication_session.PasswordLoginChallenge)
    result = authentication_session.complete_password_login_challenge(
        challenge_id=challenge.challenge_id,
        challenge_token=challenge.challenge_token,
        factor_code=_totp_code(secret, totp_step(datetime.now(timezone.utc)) + step_offset),
    )
    assert result is not None
    token, _expires_at, principal = result
    return principal, secret, token


def _connection():
    return pymysql.connect(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _user_state(account_id: int) -> tuple[bool, int]:
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT enabled,access_control_version FROM admin_users WHERE id=%s", (account_id,))
            row = cursor.fetchone()
            assert row is not None
            return bool(row["enabled"]), int(row["access_control_version"])
    finally:
        connection.close()


def _seed_active_session(account_id: int) -> str:
    """Create a bearer-like row only to prove the administration command revokes it."""
    from subsystems.access.authentication_session import _token_hash

    token = secrets.token_urlsafe(32)
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO admin_sessions (
                    admin_user_id, session_token_hash, expires_at, absolute_expires_at, last_seen_at
                ) VALUES (%s,%s,DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 30 MINUTE),
                  DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 8 HOUR),UTC_TIMESTAMP(6))""",
                (account_id, _token_hash(token)),
            )
        connection.commit()
        return token
    finally:
        connection.close()


def _last_factor_step(account_id: int) -> int:
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT last_successful_step FROM admin_totp_factors WHERE admin_user_id=%s", (account_id,)
            )
            row = cursor.fetchone()
            assert row is not None and row["last_successful_step"] is not None
            return int(row["last_successful_step"])
    finally:
        connection.close()


def _security_alert_counts() -> tuple[int, int]:
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM admin_security_alert_outbox WHERE processing_status='completed'"
            )
            completed = int(cursor.fetchone()["count"])
            cursor.execute("SELECT COUNT(*) AS count FROM system_alerts WHERE source_domain='ACCESS_CONTROL'")
            projected = int(cursor.fetchone()["count"])
            return completed, projected
    finally:
        connection.close()
