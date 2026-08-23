"""
File: test_react_admin_api_compatibility.py
Description: 驗證 Option C registry、accepted rollover、closed slug 與 production fail-closed 契約。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from infrastructure.runtime.react_admin_api_compatibility import (
    REGISTRY_PATH,
    ReactAdminApiCompatibilityError,
    load_react_admin_api_compatibility_registry,
    parse_react_admin_api_compatibility_registry,
    validate_closed_identity,
)
from infrastructure.runtime.react_admin_artifact import (
    ReactAdminArtifactError,
    load_react_admin_runtime_from_environment,
)
from scripts.build_react_admin_artifact import build_artifact


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "config" / "react_admin_api_compatibility.schema.json"


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _registry_payload(
    *,
    active: str = "react-admin-api-v1",
    accepted: tuple[str, ...] = ("react-admin-api-v1",),
    statuses: dict[str, str] | None = None,
) -> dict[str, object]:
    unsigned: dict[str, object] = {
        "contract": "react-admin-api-compatibility/v1",
        "registry_revision": "react-admin-api-registry-v1",
        "family": "react-admin-api",
        "active_revision": active,
        "accepted_revisions": list(accepted),
        "revisions": {
            identity: {"status": status}
            for identity, status in (
                statuses or {"react-admin-api-v1": "active"}
            ).items()
        },
    }
    return {
        **unsigned,
        "registry_digest": hashlib.sha256(_canonical_json(unsigned)).hexdigest(),
    }


def _resign(payload: dict[str, object]) -> None:
    unsigned = dict(payload)
    unsigned.pop("registry_digest", None)
    payload["registry_digest"] = hashlib.sha256(_canonical_json(unsigned)).hexdigest()


def _source(root: Path, marker: str) -> Path:
    root.mkdir()
    (root / "index.html").write_text(
        f'<!doctype html><div id="root"></div><p>{marker}</p>', encoding="utf-8"
    )
    return root


def _environment(current: Path, previous: Path) -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "REACT_ADMIN_CURRENT_ARTIFACT_DIR": str(current),
        "REACT_ADMIN_PREVIOUS_ARTIFACT_DIR": str(previous),
        "REACT_ADMIN_ACTIVE_SELECTOR": "current",
    }


def test_checked_in_registry_matches_closed_schema_and_digest() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    Draft202012Validator(schema).validate(payload)
    registry = load_react_admin_api_compatibility_registry()

    assert registry.active_revision == "react-admin-api-v1"
    assert registry.accepted_revisions == ("react-admin-api-v1",)
    assert set(registry.revisions) == {"react-admin-api-v1"}


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update(extra=True),
        lambda payload: payload.update(family="unknown-family"),
        lambda payload: payload.update(accepted_revisions=[]),
        lambda payload: payload.update(
            accepted_revisions=["react-admin-api-v1", "react-admin-api-v1"]
        ),
        lambda payload: payload.update(active_revision="react-admin-api-v2"),
        lambda payload: payload["revisions"]["react-admin-api-v1"].update(extra=True),
    ],
    ids=[
        "top-extra",
        "family",
        "empty-accepted",
        "duplicate-accepted",
        "unknown-active",
        "revision-extra",
    ],
)
def test_registry_shape_and_rollover_drift_fail_closed(mutation) -> None:
    payload = _registry_payload()
    mutation(payload)
    _resign(payload)

    with pytest.raises(ReactAdminApiCompatibilityError):
        parse_react_admin_api_compatibility_registry(payload)


def test_registry_digest_drift_fails_closed() -> None:
    payload = _registry_payload()
    payload["registry_digest"] = "0" * 64

    with pytest.raises(ReactAdminApiCompatibilityError, match="digest does not match"):
        parse_react_admin_api_compatibility_registry(payload)


def test_rollover_accepts_v1_previous_and_v2_current_until_v1_is_closed(
    tmp_path: Path,
) -> None:
    rollover = parse_react_admin_api_compatibility_registry(
        _registry_payload(
            active="react-admin-api-v2",
            accepted=("react-admin-api-v1", "react-admin-api-v2"),
            statuses={
                "react-admin-api-v1": "accepted",
                "react-admin-api-v2": "active",
            },
        )
    )
    previous = tmp_path / "previous"
    current = tmp_path / "current"
    build_artifact(
        previous,
        source=_source(tmp_path / "source-v1", "v1"),
        source_ref="release-v1",
        api_compatibility_revision="react-admin-api-v1",
        compatibility_registry=rollover,
    )
    build_artifact(
        current,
        source=_source(tmp_path / "source-v2", "v2"),
        source_ref="release-v2",
        api_compatibility_revision="react-admin-api-v2",
        compatibility_registry=rollover,
    )

    runtime = load_react_admin_runtime_from_environment(
        _environment(current, previous),
        workspace_root=tmp_path,
        compatibility_registry=rollover,
    )
    assert runtime is not None
    assert runtime.current.api_compatibility_revision == "react-admin-api-v2"
    assert runtime.previous.api_compatibility_revision == "react-admin-api-v1"

    closed_v1 = parse_react_admin_api_compatibility_registry(
        _registry_payload(
            active="react-admin-api-v2",
            accepted=("react-admin-api-v2",),
            statuses={
                "react-admin-api-v1": "closed",
                "react-admin-api-v2": "active",
            },
        )
    )
    with pytest.raises(ReactAdminArtifactError):
        load_react_admin_runtime_from_environment(
            _environment(current, previous),
            workspace_root=tmp_path,
            compatibility_registry=closed_v1,
        )


@pytest.mark.parametrize(
    "unsafe",
    [
        "../release",
        "release/path",
        "release\\path",
        "https:release",
        "release token",
        "Release-v1",
        "release-secret-v1",
        "release-api-key-v1",
        "release-授權",
        "a" * 97,
    ],
)
def test_closed_identity_rejects_path_uri_secret_and_non_ascii_without_echo(
    unsafe: str,
) -> None:
    with pytest.raises(ReactAdminApiCompatibilityError) as captured:
        validate_closed_identity(unsafe, "source ref")
    assert unsafe not in str(captured.value)


def test_production_builder_requires_explicit_safe_identity_and_ignores_env_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path / "source", "production")
    monkeypatch.setenv("APP_RELEASE_VERSION", "release-env")
    monkeypatch.setenv(
        "REACT_ADMIN_API_COMPATIBILITY_REVISION", "react-admin-api-v1"
    )

    with pytest.raises(ReactAdminArtifactError, match="requires explicit"):
        build_artifact(tmp_path / "missing-explicit", source=source, production=True)
    with pytest.raises(ReactAdminArtifactError):
        build_artifact(
            tmp_path / "unknown-revision",
            source=source,
            source_ref="release-v1",
            api_compatibility_revision="react-admin-api-v2",
            production=True,
        )

    result = build_artifact(
        tmp_path / "valid",
        source=source,
        source_ref="release-v1",
        api_compatibility_revision="react-admin-api-v1",
        production=True,
    )
    assert result["api_compatibility_revision"] == "react-admin-api-v1"


def test_missing_and_corrupt_registry_fail_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{", encoding="utf-8")

    for path in (missing, corrupt):
        with pytest.raises(ReactAdminApiCompatibilityError):
            load_react_admin_api_compatibility_registry(path)
