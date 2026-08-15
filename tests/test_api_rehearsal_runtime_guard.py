"""FastAPI lifespan must never hide independently supervised workers."""

from __future__ import annotations

import asyncio
import inspect

from api import main


def test_api_lifespan_only_validates_line_runtime(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(main, "line_webhook_runtime_mode", lambda: calls.append("validated"))

    async def exercise_lifespan() -> None:
        async with main.lifespan(main.app):
            calls.append("running")

    asyncio.run(exercise_lifespan())

    assert calls == ["validated", "running"]


def test_api_main_has_no_embedded_worker_startup() -> None:
    source = inspect.getsource(main)

    assert "start_architecture_outbox_worker" not in source
    assert "start_security_audit_retention_worker" not in source
