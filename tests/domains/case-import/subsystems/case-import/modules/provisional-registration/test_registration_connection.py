from unittest.mock import patch

import pytest

from infrastructure.redis.registration_connection import registration_redis_client


@pytest.mark.parametrize("role", ["intake", "admin"])
@pytest.mark.parametrize("environment", [
    {},
    {"APP_ENV": "production"},
    {"APP_ENV": " PROD "},
    {"APP_ENV": "nas"},
    {"APP_ENV": "development", "DEPLOYMENT_PROFILE": "nas"},
    {"APP_ENV": "development", "ACCESS_CONTROL_PROFILE": "production"},
])
def test_formal_registration_rejects_generic_redis_before_constructing_client(role, environment):
    settings = {"REDIS_URL": "redis://127.0.0.1:16479/4", **environment}
    with patch.dict("os.environ", settings, clear=True):
        with patch("infrastructure.redis.registration_connection.Redis") as constructor:
            with pytest.raises(RuntimeError, match=f"registration_redis_{role}_credential_required"):
                registration_redis_client(role=role)
            assert constructor.mock_calls == []


@pytest.mark.parametrize("role", ["intake", "admin"])
@pytest.mark.parametrize("empty_file", [False, True])
def test_formal_registration_rejects_missing_or_blank_role_credential(role, empty_file, tmp_path):
    secret_file = tmp_path / "synthetic"
    if empty_file:
        secret_file.write_text("  \n", encoding="utf-8")
    settings = {
        "APP_ENV": "production",
        "REDIS_URL": "redis://127.0.0.1:16479/4",
        f"REGISTRATION_REDIS_{role.upper()}_PASSWORD_FILE": str(secret_file),
    }
    with patch.dict("os.environ", settings, clear=True):
        with patch("infrastructure.redis.registration_connection.Redis") as constructor:
            with pytest.raises(RuntimeError, match=f"registration_redis_{role}_credential_required"):
                registration_redis_client(role=role)
            assert constructor.mock_calls == []


@pytest.mark.parametrize("role", ["intake", "admin"])
def test_dedicated_role_credentials_take_priority_in_production(role, tmp_path):
    secret_file = tmp_path / "synthetic"
    secret_file.write_text("synthetic-test-password", encoding="utf-8")
    settings = {
        "APP_ENV": "production",
        "REDIS_URL": "redis://127.0.0.1:16479/4",
        "REGISTRATION_REDIS_HOST": "registration-redis",
        f"REGISTRATION_REDIS_{role.upper()}_PASSWORD_FILE": str(secret_file),
    }
    with patch.dict("os.environ", settings, clear=True):
        client = registration_redis_client(role=role)
    options = client.connection_pool.connection_kwargs
    assert options["host"] == "registration-redis"
    assert options["username"] == f"registration-{role}"
    assert options["password"] == "synthetic-test-password"


@pytest.mark.parametrize("role", ["intake", "admin"])
@pytest.mark.parametrize("environment", ["development", "test"])
def test_local_registration_can_still_use_generic_redis(role, environment):
    settings = {
        "APP_ENV": environment,
        "ACCESS_CONTROL_PROFILE": "local_auth",
        "REDIS_URL": "redis://127.0.0.1:16479/4",
    }
    with patch.dict("os.environ", settings, clear=True):
        client = registration_redis_client(role=role)
    options = client.connection_pool.connection_kwargs
    assert (options["host"], options["port"], options["db"]) == ("127.0.0.1", 16479, 4)


@pytest.mark.parametrize("role", ["intake", "admin"])
@pytest.mark.parametrize("invalid_port", [None, "not-a-port", "65536"])
def test_registration_entrypoint_returns_typed_unavailable_for_invalid_configuration(role, invalid_port, tmp_path):
    from fastapi import HTTPException
    from api.dependencies.registration_applications import get_registration_review_application
    from api.registration_intake import get_staging

    entrypoint = get_staging if role == "intake" else get_registration_review_application
    settings = {"APP_ENV": "production", "REDIS_URL": "redis://127.0.0.1:16479/4"}
    if invalid_port is not None:
        secret_file = tmp_path / "synthetic"
        secret_file.write_text("synthetic-test-password", encoding="utf-8")
        settings[f"REGISTRATION_REDIS_{role.upper()}_PASSWORD_FILE"] = str(secret_file)
        settings["REGISTRATION_REDIS_PORT"] = invalid_port
    with patch.dict("os.environ", settings, clear=True):
        with (
            patch("infrastructure.redis.registration_connection.Redis") as constructor,
            patch("api.dependencies.registration_applications.get_line_identity_application") as formal_application,
        ):
            with pytest.raises(HTTPException) as exc:
                entrypoint.__wrapped__()
            assert constructor.mock_calls == []
            formal_application.assert_not_called()
    assert exc.value.status_code == 503
    assert exc.value.detail["error"]["code"] == "registration_storage_not_configured"
