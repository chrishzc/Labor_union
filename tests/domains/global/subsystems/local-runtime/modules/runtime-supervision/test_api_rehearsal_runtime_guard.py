"""FastAPI lifespan must never hide independently supervised workers."""

from __future__ import annotations

import asyncio
import inspect

from api import main


def test_api_lifespan_runs_bounded_seeds_then_validates_runtime_without_workers(monkeypatch) -> None:
    from api.dependencies import knowledge_retrieval

    calls: list[str] = []
    monkeypatch.setattr(knowledge_retrieval, "ensure_builtin_knowledge_catalog", lambda: calls.append("knowledge_seed"))
    monkeypatch.setattr(main, "ensure_development_line_configuration", lambda: calls.append("line_seed"))
    monkeypatch.setattr(main, "line_webhook_runtime_mode", lambda: calls.append("validated"))

    async def exercise_lifespan() -> None:
        async with main.lifespan(main.app):
            calls.append("running")

    asyncio.run(exercise_lifespan())

    assert calls == ["knowledge_seed", "line_seed", "validated", "running"]


import pytest


def test_api_main_has_no_embedded_worker_startup() -> None:
    source = inspect.getsource(main)

    assert "start_architecture_outbox_worker" not in source
    assert "start_security_audit_retention_worker" not in source


@pytest.mark.parametrize("environment", ["production", "development"])
def test_startup_backfills_five_baseline_line_configs_in_all_environments(monkeypatch, environment) -> None:
    from api.dependencies.admin_auth import ensure_development_line_configuration
    from domains.line.configuration import LineConfigurationKind
    from subsystems.line import configuration_application

    captured: dict[str, object] = {}

    class StubApplication:
        def __init__(self, _unit_of_work_factory) -> None:
            pass

        def bootstrap_missing(self, definitions, actor, *, reason, correlation_id) -> dict[object, int]:
            captured["definitions"] = definitions
            captured["actor"] = actor
            captured["reason"] = reason
            captured["correlation_id"] = correlation_id
            return {}

    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setattr(configuration_application, "LineConfigurationApplication", StubApplication)

    ensure_development_line_configuration()

    assert set(captured["definitions"]) == {
        LineConfigurationKind.MESSAGE_TEMPLATES,
        LineConfigurationKind.MESSAGE_SCHEDULES,
        LineConfigurationKind.RICH_MENUS,
        LineConfigurationKind.LIFF,
        LineConfigurationKind.NOTIFICATION_RULES,
    }
