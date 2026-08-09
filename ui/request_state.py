"""Session-state request generations for Streamlit read models."""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Literal


RequestStatus = Literal[
    "idle",
    "loading",
    "refreshing",
    "success",
    "empty",
    "warning",
    "error",
    "stale",
]


@dataclass(frozen=True, slots=True)
class RequestSnapshot:
    generation: int
    status: RequestStatus
    error_message: str | None = None


def begin_request(
    state: MutableMapping[str, object],
    request_key: str,
) -> RequestSnapshot:
    previous = _snapshot(state.get(request_key))
    snapshot = RequestSnapshot(
        generation=previous.generation + 1,
        status=_next_loading_status(previous),
    )
    state[request_key] = _as_record(snapshot)
    return snapshot


def accept_request_result(
    state: MutableMapping[str, object],
    request_key: str,
    request: RequestSnapshot,
    *,
    item_count: int,
    error_message: str | None = None,
    warning_message: str | None = None,
) -> bool:
    current = _snapshot(state.get(request_key))
    if current.generation != request.generation:
        state[f"{request_key}:stale_generation"] = request.generation
        return False
    state.pop(f"{request_key}:stale_generation", None)
    state[request_key] = _as_record(
        _completed_snapshot(item_count, error_message, warning_message, request)
    )
    return True


def request_snapshot(
    state: MutableMapping[str, object], request_key: str
) -> RequestSnapshot:
    return _snapshot(state.get(request_key))


def stale_request_generation(
    state: MutableMapping[str, object], request_key: str
) -> int | None:
    generation = state.get(f"{request_key}:stale_generation")
    return generation if isinstance(generation, int) else None


def mark_request_stale(
    state: MutableMapping[str, object], request_key: str
) -> RequestSnapshot:
    """Retain the latest result while its backing projection is being refreshed."""
    current = _snapshot(state.get(request_key))
    if current.status not in {"success", "warning", "refreshing"}:
        return current
    stale = RequestSnapshot(current.generation, "stale", current.error_message)
    state[request_key] = _as_record(stale)
    return stale


def _completed_snapshot(
    item_count: int,
    error_message: str | None,
    warning_message: str | None,
    request: RequestSnapshot,
) -> RequestSnapshot:
    if error_message:
        return RequestSnapshot(request.generation, "error", error_message)
    if warning_message:
        return RequestSnapshot(request.generation, "warning", warning_message)
    return RequestSnapshot(request.generation, "success" if item_count else "empty")


def _next_loading_status(previous: RequestSnapshot) -> RequestStatus:
    if previous.status in {"success", "warning", "stale"}:
        return "refreshing"
    return "loading"


def _snapshot(value: object) -> RequestSnapshot:
    if not isinstance(value, dict):
        return RequestSnapshot(0, "idle")
    generation = value.get("generation")
    status = value.get("status")
    if not isinstance(generation, int) or status not in {
        "idle", "loading", "refreshing", "success", "empty", "warning", "error", "stale",
    }:
        return RequestSnapshot(0, "idle")
    error = value.get("error_message")
    return RequestSnapshot(generation, status, error if isinstance(error, str) else None)


def _as_record(snapshot: RequestSnapshot) -> dict[str, object]:
    return {
        "generation": snapshot.generation,
        "status": snapshot.status,
        "error_message": snapshot.error_message,
    }
