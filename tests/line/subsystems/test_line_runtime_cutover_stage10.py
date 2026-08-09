"""Stage 10 production cutover and rollback guard contracts."""

from __future__ import annotations

import pytest

from subsystems.line.runtime_contracts import LineRuntimeMode
from subsystems.line.runtime_cutover import (
    LineRuntimeCutoverError,
    load_line_cutover_release,
    production_readiness_report,
    resolve_line_runtime_selection,
)


def test_production_requires_canonical_unless_explicit_rollback() -> None:
    with pytest.raises(LineRuntimeCutoverError, match="rollback"):
        resolve_line_runtime_selection(_environment(webhook="legacy", worker="legacy"))

    rollback = _environment(webhook="legacy", worker="legacy")
    rollback["LINE_LEGACY_ROLLBACK_MODE"] = "true"

    assert resolve_line_runtime_selection(rollback).rollback_mode is True


def test_production_rejects_dual_or_compatibility_runtime() -> None:
    with pytest.raises(LineRuntimeCutoverError, match="must match"):
        resolve_line_runtime_selection(_environment(webhook="canonical", worker="legacy"))
    with pytest.raises(LineRuntimeCutoverError, match="forbidden"):
        resolve_line_runtime_selection(
            _environment(webhook="canonical", worker="compatibility")
        )


def test_development_compatibility_is_explicitly_allowed() -> None:
    environment = _environment(webhook="legacy", worker="compatibility")
    environment["APP_ENV"] = "development"

    result = resolve_line_runtime_selection(environment)

    assert result.worker_mode is LineRuntimeMode.COMPATIBILITY


def test_production_readiness_reports_modes_without_secrets() -> None:
    environment = _environment(webhook="canonical", worker="canonical")

    report = production_readiness_report(environment)

    assert report == {
        "status": "ready",
        "app_environment": "production",
        "webhook_mode": "canonical",
        "worker_mode": "canonical",
        "rollback_mode": False,
        "optional_workers": {
            "knowledge_retrieval": False,
        },
    }
    assert "access-token" not in str(report)


def test_production_readiness_fails_closed_on_auth_bypass_or_placeholder() -> None:
    bypass = _environment(webhook="canonical", worker="canonical")
    bypass["ENABLE_ADMIN_AUTH"] = "false"
    with pytest.raises(LineRuntimeCutoverError, match="ENABLE_ADMIN_AUTH"):
        production_readiness_report(bypass)

    placeholder = _environment(webhook="canonical", worker="canonical")
    placeholder["LINE_CHANNEL_ACCESS_TOKEN"] = "your_line_channel_access_token_here"
    with pytest.raises(LineRuntimeCutoverError, match="ACCESS_TOKEN"):
        production_readiness_report(placeholder)


def test_production_readiness_validates_operational_configuration() -> None:
    invalid_stale_window = _environment(webhook="canonical", worker="canonical")
    invalid_stale_window["LINE_REVIEW_STALE_HOURS"] = "zero"
    with pytest.raises(LineRuntimeCutoverError, match="LINE_REVIEW_STALE_HOURS"):
        production_readiness_report(invalid_stale_window)

    missing_index_path = _environment(webhook="canonical", worker="canonical")
    missing_index_path["KNOWLEDGE_RETRIEVAL_RUNTIME_ENABLED"] = "true"
    with pytest.raises(LineRuntimeCutoverError, match="KNOWLEDGE_CHROMA_PATH"):
        production_readiness_report(missing_index_path)


def test_production_legacy_rollback_still_requires_access_token() -> None:
    rollback = _environment(webhook="legacy", worker="legacy")
    rollback["LINE_LEGACY_ROLLBACK_MODE"] = "true"
    del rollback["LINE_CHANNEL_ACCESS_TOKEN"]

    with pytest.raises(LineRuntimeCutoverError, match="ACCESS_TOKEN"):
        production_readiness_report(rollback)


def test_stage10_cutover_release_names_full_migration_chain() -> None:
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    path = root / "db/cutover_releases/labor_union_2026_08_09_line_stage10_v1.json"
    release = load_line_cutover_release(json.loads(path.read_text(encoding="utf-8")))

    assert release.migration_manifests == (
        "labor_union_2026_08_09_v9.json",
    )
    assert "legacy-writer-gone" in release.post_cutover_smoke_ids
    assert set(release.required_restart_targets) == {
        "api",
        "background-worker",
        "file-watcher",
        "knowledge-retrieval-worker",
        "line-worker",
        "runtime-monitor",
        "streamlit",
    }


def _environment(*, webhook: str, worker: str) -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "LINE_WEBHOOK_RUNTIME_MODE": webhook,
        "LINE_WORKER_RUNTIME_MODE": worker,
        "LINE_LEGACY_ROLLBACK_MODE": "false",
        "ENABLE_ADMIN_AUTH": "true",
        "LIFF_REQUIRE_ID_TOKEN": "true",
        "INTERNAL_API_KEY": "internal-secret",
        "LINE_CHANNEL_SECRET": "channel-secret",
        "LINE_CHANNEL_ACCESS_TOKEN": "access-token",
        "LINE_LOGIN_CHANNEL_ID": "1234567890",
        "LINE_LIFF_ID": "1234567890-AbCdEf",
        "KNOWLEDGE_RETRIEVAL_RUNTIME_ENABLED": "false",
    }
    load_line_cutover_release,
