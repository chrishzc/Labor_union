"""Verify development root bootstrap and MFA enrollment on a fresh disposable MySQL DB."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pymysql
import pytest
from cryptography.fernet import Fernet


pytestmark = pytest.mark.skipif(
    not os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE"),
    reason="requires an explicitly configured fresh disposable lu_test_* MySQL database",
)


def _connection():
    host = os.environ["LABOR_UNION_TEST_MYSQL_HOST"]
    database = os.environ["LABOR_UNION_TEST_MYSQL_DATABASE"]
    if host not in {"127.0.0.1", "localhost", "::1"} or not database.startswith("lu_test_"):
        raise ValueError("requires a local disposable database")
    return pymysql.connect(
        host=host,
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=database,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _rows(sql: str):
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()


def _require(condition: bool, message: str) -> None:
    # Report only the failed boundary, never challenge tokens or factor seeds.
    if not condition:
        raise AssertionError(message)


def test_development_root_requires_enrollment_and_preserves_existing_factor(monkeypatch):
    from api.dependencies import admin_auth
    from subsystems.access import authentication_session as auth
    from subsystems.access.totp import _totp_code, totp_step

    _require(not _rows("SELECT id FROM admin_users"), "requires a fresh account database")
    _require(not _rows("SELECT admin_user_id FROM admin_root_account"), "requires no existing root")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "local_auth")
    monkeypatch.setenv("ACCESS_CONTROL_TOTP_KEYRING", "v1:" + Fernet.generate_key().decode("ascii"))
    monkeypatch.setenv("ACCESS_CONTROL_TOTP_ACTIVE_KEY_VERSION", "v1")
    username = "issue358-root-" + secrets.token_hex(6)
    password = secrets.token_urlsafe(24)
    monkeypatch.setenv("DEV_ROOT_USERNAME", username)
    monkeypatch.setenv("DEV_ROOT_PASSWORD", password)
    monkeypatch.setattr(admin_auth, "get_connection", _connection)

    admin_auth.ensure_development_root_admin()
    _require(len(_rows("SELECT id FROM admin_users")) == 1, "bootstrap must create one account")
    _require(len(_rows("SELECT admin_user_id FROM admin_root_account")) == 1, "bootstrap must establish root")
    _require(not _rows("SELECT id FROM admin_totp_factors"), "bootstrap must not provision a factor")
    _require(not _rows("SELECT id FROM admin_sessions"), "bootstrap must not issue a session")

    first = auth.issue_password_login_challenge(username, password, connection_factory=_connection)
    _require(type(first) is auth.MfaEnrollmentChallenge, "first password login must require enrollment")
    first_secret = parse_qs(urlparse(first.provisioning_uri).query)["secret"][0]
    second = auth.issue_password_login_challenge(username, password, connection_factory=_connection)
    _require(type(second) is auth.MfaEnrollmentChallenge, "unconfirmed login must still require enrollment")
    second_secret = parse_qs(urlparse(second.provisioning_uri).query)["secret"][0]
    _require(first_secret != second_secret, "separate enrollments must have independent random seeds")
    _require(_rows("SELECT factor_state FROM admin_totp_factors") == [{"factor_state": "enrollment_pending"}], "factor must remain pending")
    _require(not _rows("SELECT id FROM admin_sessions"), "password login must not issue a session")

    step = totp_step(datetime.now(timezone.utc))
    code = _totp_code(second_secret, step)
    invalid_code = str((int(code) + 1) % 1000000).zfill(6)
    while invalid_code in {_totp_code(second_secret, step + offset) for offset in (-1, 0, 1)}:
        invalid_code = str((int(invalid_code) + 1) % 1000000).zfill(6)
    with pytest.raises(ValueError, match="invalid_credentials_or_factor"):
        auth.complete_mfa_enrollment(
            connection_factory=_connection, challenge_id=second.challenge_id,
            challenge_token=second.challenge_token, totp_code=invalid_code,
        )
    _require(_rows("SELECT factor_state FROM admin_totp_factors") == [{"factor_state": "enrollment_pending"}], "invalid code must not activate factor")
    _require(not _rows("SELECT id FROM admin_sessions"), "invalid code must not issue session")

    auth.complete_mfa_enrollment(
        connection_factory=_connection, challenge_id=second.challenge_id,
        challenge_token=second.challenge_token, totp_code=code,
    )
    _require(_rows("SELECT factor_state FROM admin_totp_factors") == [{"factor_state": "active"}], "confirmation must activate factor")
    _require(not _rows("SELECT id FROM admin_sessions"), "enrollment confirmation alone must not issue session")

    challenge = auth.issue_password_login_challenge(username, password, connection_factory=_connection)
    _require(type(challenge) is auth.PasswordLoginChallenge, "enrolled account must require factor verification")
    result = auth.complete_password_login_challenge(
        connection_factory=_connection, challenge_id=challenge.challenge_id,
        challenge_token=challenge.challenge_token,
        factor_code=_totp_code(second_secret, step + 1),
    )
    _require(result is not None, "valid account TOTP must complete login")
    principal = auth.get_admin_session(result[0], connection_factory=_connection)
    _require(principal is not None and principal.is_root, "verified session must belong to root")

    accounts_before = _rows("SELECT * FROM admin_users")
    factors_before = _rows("SELECT * FROM admin_totp_factors")
    monkeypatch.setenv("DEV_ROOT_PASSWORD", secrets.token_urlsafe(24))
    admin_auth.ensure_development_root_admin()
    _require(_rows("SELECT * FROM admin_users") == accounts_before, "restart must preserve existing account")
    _require(_rows("SELECT * FROM admin_totp_factors") == factors_before, "restart must preserve existing factor")

    for app_env, configured_username, configured_password in (
        ("production", "issue358-uncreated", password),
        ("development", "", password),
        ("development", "issue358-uncreated", ""),
    ):
        monkeypatch.setenv("APP_ENV", app_env)
        monkeypatch.setenv("DEV_ROOT_USERNAME", configured_username)
        monkeypatch.setenv("DEV_ROOT_PASSWORD", configured_password)
        admin_auth.ensure_development_root_admin()
    _require(_rows("SELECT * FROM admin_users") == accounts_before, "disallowed bootstrap must not alter accounts")
    _require(_rows("SELECT * FROM admin_totp_factors") == factors_before, "disallowed bootstrap must not alter factors")
