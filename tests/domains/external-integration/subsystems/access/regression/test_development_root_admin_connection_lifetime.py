"""Startup must never create a root from legacy development credentials."""
import asyncio
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize("app_env", ["development", "production"])
def test_startup_ignores_legacy_root_credentials(monkeypatch, app_env):
    from api import main
    from api.dependencies import knowledge_retrieval
    from subsystems.access import authentication_session
    from infrastructure.mysql import mysql_adapter

    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("DEV_ROOT_USERNAME", "legacy-root")
    monkeypatch.setenv("DEV_ROOT_PASSWORD", "synthetic-old-password")
    monkeypatch.setattr(knowledge_retrieval, "ensure_builtin_knowledge_catalog", lambda: None)
    monkeypatch.setattr(main, "ensure_development_line_configuration", lambda: None)
    monkeypatch.setattr(main, "line_webhook_runtime_mode", lambda: None)
    monkeypatch.setattr(mysql_adapter, "get_connection", Mock(side_effect=RuntimeError("no startup DB")))
    monkeypatch.setattr(mysql_adapter, "close_connection_pools", lambda: None)
    bootstrap = Mock()
    monkeypatch.setattr(authentication_session, "bootstrap_root_admin", bootstrap)

    async def startup():
        async with main.lifespan(main.app):
            pass
    asyncio.run(startup())
    bootstrap.assert_not_called()
