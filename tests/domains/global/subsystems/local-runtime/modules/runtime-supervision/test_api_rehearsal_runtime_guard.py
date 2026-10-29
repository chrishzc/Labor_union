"""FastAPI lifespan must never hide independently supervised workers."""

from __future__ import annotations

import asyncio
import inspect

from api import main


def test_api_lifespan_runs_bounded_seeds_then_validates_runtime_without_workers(monkeypatch) -> None:
    from api.dependencies import knowledge_retrieval

    calls: list[str] = []
    monkeypatch.setattr(main, "ensure_development_root_admin", lambda: calls.append("root_seed"))
    monkeypatch.setattr(knowledge_retrieval, "ensure_builtin_knowledge_catalog", lambda: calls.append("knowledge_seed"))
    monkeypatch.setattr(main, "ensure_development_line_configuration", lambda: calls.append("line_seed"))
    monkeypatch.setattr(main, "line_webhook_runtime_mode", lambda: calls.append("validated"))

    async def exercise_lifespan() -> None:
        async with main.lifespan(main.app):
            calls.append("running")

    asyncio.run(exercise_lifespan())

    assert calls == ["root_seed", "knowledge_seed", "line_seed", "validated", "running"]


def test_api_main_has_no_embedded_worker_startup() -> None:
    source = inspect.getsource(main)

    assert "start_architecture_outbox_worker" not in source
    assert "start_security_audit_retention_worker" not in source
