"""Validate mutually exclusive LINE runtimes and production cutover prerequisites."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Any

from subsystems.line.runtime_contracts import LineRuntimeMode


PRODUCTION_ENVIRONMENTS = {"prod", "production"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_PLACEHOLDER_PREFIXES = ("replace_with_", "your_")


class LineRuntimeCutoverError(RuntimeError):
    """Raised when runtime selection could cause dual processing or insecure production."""


@dataclass(frozen=True, slots=True)
class LineRuntimeSelection:
    app_environment: str
    webhook_mode: LineRuntimeMode
    worker_mode: LineRuntimeMode
    rollback_mode: bool

    @property
    def is_production(self) -> bool:
        return self.app_environment in PRODUCTION_ENVIRONMENTS


@dataclass(frozen=True, slots=True)
class LineCutoverRelease:
    release_id: str
    migration_manifests: tuple[str, ...]
    required_restart_targets: tuple[str, ...]
    post_cutover_smoke_ids: tuple[str, ...]
    retired_route_prefixes: tuple[str, ...]


def load_line_cutover_release(payload: dict[str, Any]) -> LineCutoverRelease:
    _validate_cutover_release_shape(payload)
    _validate_cutover_modes(payload)
    return LineCutoverRelease(
        _required_text(payload["release_id"], "release_id"),
        _text_tuple(payload["migration_manifests"], "migration_manifests"),
        _text_tuple(payload["required_restart_targets"], "required_restart_targets"),
        _text_tuple(payload["post_cutover_smoke_ids"], "post_cutover_smoke_ids"),
        _text_tuple(payload["retired_route_prefixes"], "retired_route_prefixes"),
    )


def _validate_cutover_release_shape(payload: dict[str, Any]) -> None:
    expected_keys = {
        "contract",
        "migration_manifests",
        "post_cutover_smoke_ids",
        "release_id",
        "required_restart_targets",
        "retired_route_prefixes",
        "rollback_contract",
        "target_runtime",
    }
    if set(payload) != expected_keys:
        raise LineRuntimeCutoverError("LINE cutover release keys do not match contract")
    if payload["contract"] != "line-runtime-cutover-release/v1":
        raise LineRuntimeCutoverError("unsupported LINE cutover release contract")


def resolve_line_runtime_selection(
    environment: Mapping[str, str],
) -> LineRuntimeSelection:
    app_environment = environment.get("APP_ENV", "development").strip().lower()
    webhook_mode = _runtime_mode(environment, "LINE_WEBHOOK_RUNTIME_MODE")
    worker_mode = _runtime_mode(environment, "LINE_WORKER_RUNTIME_MODE")
    rollback_mode = _is_true(environment.get("LINE_LEGACY_ROLLBACK_MODE", "false"))
    selection = LineRuntimeSelection(
        app_environment,
        webhook_mode,
        worker_mode,
        rollback_mode,
    )
    _validate_runtime_pair(selection)
    return selection


def validate_line_api_runtime(environment: Mapping[str, str]) -> LineRuntimeSelection:
    selection = resolve_line_runtime_selection(environment)
    if not selection.is_production:
        return selection
    _require_enabled(environment, "ENABLE_ADMIN_AUTH")
    _require_enabled(environment, "LIFF_REQUIRE_ID_TOKEN")
    _require_secret(environment, "INTERNAL_API_KEY")
    _require_secret(environment, "LINE_CHANNEL_SECRET")
    _require_secret(environment, "LINE_LOGIN_CHANNEL_ID")
    _require_liff_entrypoint(environment)
    return selection


def validate_line_worker_runtime(environment: Mapping[str, str]) -> LineRuntimeSelection:
    selection = resolve_line_runtime_selection(environment)
    if selection.is_production or selection.worker_mode is LineRuntimeMode.CANONICAL:
        _require_secret(environment, "LINE_CHANNEL_ACCESS_TOKEN")
    return selection


def production_readiness_report(environment: Mapping[str, str]) -> dict[str, object]:
    selection = validate_line_api_runtime(environment)
    validate_line_worker_runtime(environment)
    optional_workers = _validate_optional_workers(environment)
    _require_positive_integer(environment, "LINE_REVIEW_STALE_HOURS", default="24")
    return {
        "status": "ready",
        "app_environment": selection.app_environment,
        "webhook_mode": selection.webhook_mode.value,
        "worker_mode": selection.worker_mode.value,
        "rollback_mode": selection.rollback_mode,
        "optional_workers": optional_workers,
    }


def _validate_runtime_pair(selection: LineRuntimeSelection) -> None:
    if selection.webhook_mode is LineRuntimeMode.COMPATIBILITY:
        raise LineRuntimeCutoverError("compatibility mode is worker-only")
    if selection.worker_mode is LineRuntimeMode.COMPATIBILITY:
        if selection.is_production:
            raise LineRuntimeCutoverError("compatibility mode is forbidden in production")
        return
    if selection.webhook_mode is not selection.worker_mode:
        raise LineRuntimeCutoverError("LINE webhook and worker runtime modes must match")
    if not selection.is_production:
        return
    if selection.webhook_mode is LineRuntimeMode.CANONICAL:
        return
    if not selection.rollback_mode:
        raise LineRuntimeCutoverError(
            "production legacy runtime requires explicit rollback setting "
            "LINE_LEGACY_ROLLBACK_MODE=true"
        )


def _validate_cutover_modes(payload: dict[str, Any]) -> None:
    target = payload.get("target_runtime")
    rollback = payload.get("rollback_contract")
    if target != {"webhook_mode": "canonical", "worker_mode": "canonical"}:
        raise LineRuntimeCutoverError("LINE cutover target must be canonical")
    if rollback != {
        "legacy_flag": "LINE_LEGACY_ROLLBACK_MODE=true",
        "webhook_mode": "legacy",
        "worker_mode": "legacy",
    }:
        raise LineRuntimeCutoverError("LINE rollback contract is invalid")


def _text_tuple(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise LineRuntimeCutoverError(f"{name} must be a non-empty list")
    normalized = tuple(_required_text(item, name) for item in value)
    if len(normalized) != len(set(normalized)):
        raise LineRuntimeCutoverError(f"{name} must be unique")
    return normalized


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LineRuntimeCutoverError(f"{name} must contain text")
    return value.strip()


def _runtime_mode(environment: Mapping[str, str], name: str) -> LineRuntimeMode:
    value = environment.get(name, "legacy").strip().lower()
    try:
        return LineRuntimeMode(value)
    except ValueError as error:
        raise LineRuntimeCutoverError(f"invalid {name}") from error


def _validate_optional_workers(environment: Mapping[str, str]) -> dict[str, bool]:
    knowledge_enabled = _is_true(
        environment.get("KNOWLEDGE_RETRIEVAL_RUNTIME_ENABLED", "false")
    )
    if knowledge_enabled:
        _require_nonempty(environment, "KNOWLEDGE_CHROMA_PATH")
    return {"knowledge_retrieval": knowledge_enabled}


def _require_liff_entrypoint(environment: Mapping[str, str]) -> None:
    liff_id = environment.get("LINE_LIFF_ID", "").strip()
    public_url = environment.get("LINE_PUBLIC_BASE_URL", "").strip()
    if _usable_value(liff_id) or _usable_https_url(public_url):
        return
    raise LineRuntimeCutoverError(
        "production requires LINE_LIFF_ID or an HTTPS LINE_PUBLIC_BASE_URL"
    )


def _require_enabled(environment: Mapping[str, str], name: str) -> None:
    if environment.get(name, "true").strip().lower() in _FALSE_VALUES:
        raise LineRuntimeCutoverError(f"{name} cannot be disabled in production")


def _require_secret(environment: Mapping[str, str], name: str) -> None:
    if not _usable_value(environment.get(name, "")):
        raise LineRuntimeCutoverError(f"{name} is missing or still a placeholder")


def _require_nonempty(environment: Mapping[str, str], name: str) -> None:
    if not environment.get(name, "").strip():
        raise LineRuntimeCutoverError(f"{name} is required when its runtime is enabled")


def _require_json_object(environment: Mapping[str, str], name: str) -> None:
    _require_nonempty(environment, name)
    try:
        value = json.loads(environment[name])
    except json.JSONDecodeError as error:
        raise LineRuntimeCutoverError(f"{name} must be valid JSON") from error
    if not isinstance(value, dict) or not value:
        raise LineRuntimeCutoverError(f"{name} must be a non-empty JSON object")


def _require_positive_integer(
    environment: Mapping[str, str],
    name: str,
    *,
    default: str,
) -> None:
    try:
        value = int(environment.get(name, default))
    except ValueError as error:
        raise LineRuntimeCutoverError(f"{name} must be a positive integer") from error
    if value < 1:
        raise LineRuntimeCutoverError(f"{name} must be a positive integer")


def _usable_value(value: str) -> bool:
    normalized = value.strip().lower()
    return bool(normalized) and not normalized.startswith(_PLACEHOLDER_PREFIXES)


def _usable_https_url(value: str) -> bool:
    return _usable_value(value) and value.strip().lower().startswith("https://")


def _is_true(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


__all__ = [
    "LineRuntimeCutoverError",
    "LineCutoverRelease",
    "LineRuntimeSelection",
    "load_line_cutover_release",
    "production_readiness_report",
    "resolve_line_runtime_selection",
    "validate_line_api_runtime",
    "validate_line_worker_runtime",
]
