"""
File: react_admin_artifact.py
Description: 驗證並唯讀提供 React 管理端 artifact、瀏覽器私有快取資格證明與健康檢查。
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping

from starlette.responses import FileResponse, JSONResponse, Response
from starlette.types import Receive, Scope, Send

from infrastructure.runtime.react_admin_api_compatibility import (
    ReactAdminApiCompatibilityError,
    ReactAdminApiCompatibilityRegistry,
    load_react_admin_api_compatibility_registry,
    validate_closed_identity,
)


MANIFEST_NAME = "artifact-manifest.json"
ROOT_ENTRY = "index.html"
ASSET_ELIGIBILITY_HEADER = "X-React-Admin-Asset-Eligibility"
PRIVATE_IMMUTABLE_CACHE_CONTROL = "private, max-age=31536000, immutable"
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'self'; object-src 'none'; "
        "frame-ancestors 'none'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_IMMUTABLE_ASSET_FILENAME_PATTERN = re.compile(
    r"^[A-Za-z0-9._-]+-[A-Za-z0-9_-]{8,}\.(?:js|css)$"
)
_REQUIRED_MANIFEST_KEYS = frozenset(
    {
        "contract",
        "artifact_version",
        "source_ref",
        "build_tools",
        "api_compatibility_revision",
        "root_entry",
        "files",
        "artifact_digest",
    }
)
_OPTIONAL_MANIFEST_KEYS = frozenset({"immutable_assets"})
_CONDITIONAL_REQUEST_HEADERS = frozenset({b"if-none-match", b"if-modified-since"})
_PRODUCTION_ENVIRONMENTS = frozenset({"prod", "production"})


class ReactAdminArtifactError(RuntimeError):
    """Reject an artifact or selector that cannot be proven safe and exact."""


@dataclass(frozen=True, slots=True)
class ArtifactFile:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ValidatedReactAdminArtifact:
    root: Path
    artifact_version: str
    source_ref: str
    api_compatibility_revision: str
    artifact_digest: str
    manifest_digest: str
    files: Mapping[str, ArtifactFile]
    immutable_assets: frozenset[str] = frozenset()

    def resolve_manifest(self) -> Path:
        """Return the original manifest only while its bytes remain immutable."""
        candidate = self.root / MANIFEST_NAME
        if candidate.is_symlink():
            raise ReactAdminArtifactError("react admin artifact manifest cannot be a symlink")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_file() or not resolved.is_relative_to(self.root):
            raise ReactAdminArtifactError("react admin artifact manifest escapes its root")
        if _digest_file(resolved) != self.manifest_digest:
            raise ReactAdminArtifactError("react admin artifact manifest digest changed")
        return resolved

    def resolve_file(self, relative_path: str) -> Path:
        normalized = _canonical_relative_path(relative_path)
        if normalized not in self.files:
            raise ReactAdminArtifactError("react admin artifact path is not listed")
        candidate = (self.root / PurePosixPath(normalized)).resolve(strict=True)
        if not candidate.is_relative_to(self.root):
            raise ReactAdminArtifactError("react admin artifact path escapes its root")
        return candidate

    def health_attestation(self, selector: str) -> dict[str, object]:
        self.resolve_manifest()
        root_entry = self.files[ROOT_ENTRY]
        if _digest_file(self.resolve_file(ROOT_ENTRY)) != root_entry.sha256:
            raise ReactAdminArtifactError("react admin root entry digest changed")
        checked = next(
            (item for path, item in sorted(self.files.items()) if path != ROOT_ENTRY),
            root_entry,
        )
        if _digest_file(self.resolve_file(checked.path)) != checked.sha256:
            raise ReactAdminArtifactError("react admin checked asset digest changed")
        return {
            "active_selector": selector,
            "artifact_version": self.artifact_version,
            "artifact_digest": self.artifact_digest,
            "manifest_digest": self.manifest_digest,
            "api_compatibility_revision": self.api_compatibility_revision,
            "root_marker_checked": True,
            "checked_asset_digest": checked.sha256,
            "healthy": True,
        }


@dataclass(frozen=True, slots=True)
class ReactAdminArtifactRuntime:
    active_selector: str
    current: ValidatedReactAdminArtifact
    previous: ValidatedReactAdminArtifact

    @property
    def active(self) -> ValidatedReactAdminArtifact:
        return self.current if self.active_selector == "current" else self.previous

    def health_attestation(self) -> dict[str, object]:
        return self.active.health_attestation(self.active_selector)


class ReactAdminStaticApplication:
    """Serve only files proven by the active artifact manifest."""

    def __init__(self, artifact: ValidatedReactAdminArtifact) -> None:
        self._artifact = artifact

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await Response(status_code=404)(scope, receive, send)
            return
        method = str(scope.get("method", "GET")).upper()
        no_store_headers = {**SECURITY_HEADERS, "Cache-Control": "no-store"}
        if method not in {"GET", "HEAD"}:
            await Response(status_code=405, headers=no_store_headers)(scope, receive, send)
            return
        raw_path = str(scope.get("path", ""))
        root_path = str(scope.get("root_path", ""))
        if root_path and raw_path.startswith(root_path):
            raw_path = raw_path[len(root_path) :]
        raw_path = raw_path.lstrip("/")
        relative_path = ROOT_ENTRY if raw_path in {"", "/"} else raw_path
        try:
            if relative_path == MANIFEST_NAME:
                target = self._artifact.resolve_manifest()
                cache_control = "no-store"
                eligibility_header: str | None = None
            else:
                target = self._artifact.resolve_file(relative_path)
                expected_file = self._artifact.files[relative_path]
                if target.stat().st_size != expected_file.size:
                    raise ReactAdminArtifactError("react admin artifact file size changed")
                if relative_path in self._artifact.immutable_assets:
                    cache_control = PRIVATE_IMMUTABLE_CACHE_CONTROL
                    eligibility_header = (
                        f"v1;artifact={self._artifact.artifact_digest};sha256={expected_file.sha256}"
                    )
                else:
                    cache_control = "no-store"
                    eligibility_header = None
        except (OSError, ReactAdminArtifactError, ValueError):
            await JSONResponse(
                {"detail": "Not Found"}, status_code=404, headers=no_store_headers
            )(scope, receive, send)
            return
        if relative_path == MANIFEST_NAME:
            media_type: str | None = "application/json"
        elif target.suffix.lower() == ".js":
            media_type = "text/javascript"
        elif target.suffix.lower() == ".css":
            media_type = "text/css"
        else:
            media_type = mimetypes.guess_type(target.name)[0]
        headers = {**SECURITY_HEADERS, "Cache-Control": cache_control}
        if eligibility_header is not None:
            headers[ASSET_ELIGIBILITY_HEADER] = eligibility_header
        raw_headers = scope.get("headers")
        if raw_headers:
            filtered_headers = [
                item
                for item in raw_headers
                if item[0].lower() not in _CONDITIONAL_REQUEST_HEADERS
            ]
            if len(filtered_headers) != len(raw_headers):
                scope = {**scope, "headers": filtered_headers}
        await FileResponse(target, media_type=media_type, headers=headers)(scope, receive, send)


def load_react_admin_runtime_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    workspace_root: Path | None = None,
    compatibility_registry: ReactAdminApiCompatibilityRegistry | None = None,
) -> ReactAdminArtifactRuntime | None:
    values = os.environ if environment is None else environment
    current_value = values.get("REACT_ADMIN_CURRENT_ARTIFACT_DIR", "").strip()
    previous_value = values.get("REACT_ADMIN_PREVIOUS_ARTIFACT_DIR", "").strip()
    selector_value = values.get("REACT_ADMIN_ACTIVE_SELECTOR", "").strip()
    app_environment = values.get("APP_ENV", "development").strip().lower()
    configured = bool(current_value or previous_value or selector_value)
    if not configured and app_environment not in _PRODUCTION_ENVIRONMENTS:
        return None
    registry = compatibility_registry or _load_compatibility_registry()
    if not current_value or not previous_value or selector_value not in {"current", "previous"}:
        raise ReactAdminArtifactError("react admin artifact bindings are incomplete or invalid")
    current_binding = Path(current_value)
    previous_binding = Path(previous_value)
    try:
        if _is_link_like_directory(current_binding) or _is_link_like_directory(previous_binding):
            raise ReactAdminArtifactError(
                "current or previous react admin artifact cannot be a symlink or junction"
            )
        current_path = current_binding.resolve(strict=True)
        previous_path = previous_binding.resolve(strict=True)
    except OSError as error:
        raise ReactAdminArtifactError(
            "current or previous react admin artifact is unavailable"
        ) from error
    if current_path == previous_path:
        raise ReactAdminArtifactError("current and previous react admin artifacts must differ")
    current = validate_react_admin_artifact(
        current_binding,
        workspace_root=workspace_root,
        compatibility_registry=registry,
    )
    previous = validate_react_admin_artifact(
        previous_binding,
        workspace_root=workspace_root,
        compatibility_registry=registry,
    )
    if (
        current.artifact_version == previous.artifact_version
        or current.artifact_digest == previous.artifact_digest
    ):
        raise ReactAdminArtifactError("current and previous react admin identities must differ")
    return ReactAdminArtifactRuntime(selector_value, current, previous)


def validate_react_admin_artifact(
    artifact_root: Path,
    *,
    workspace_root: Path | None = None,
    compatibility_registry: ReactAdminApiCompatibilityRegistry | None = None,
) -> ValidatedReactAdminArtifact:
    if _is_link_like_directory(artifact_root):
        raise ReactAdminArtifactError("react admin artifact root must be a real directory")
    root = artifact_root.resolve(strict=True)
    if not root.is_dir():
        raise ReactAdminArtifactError("react admin artifact root must be a real directory")
    if workspace_root is not None and root == workspace_root.resolve(strict=True):
        raise ReactAdminArtifactError("workspace root cannot be a react admin artifact")
    manifest_path = root / MANIFEST_NAME
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReactAdminArtifactError("react admin artifact manifest is unreadable") from error
    manifest_keys = set(manifest) if isinstance(manifest, dict) else set()
    if (
        not isinstance(manifest, dict)
        or not _REQUIRED_MANIFEST_KEYS.issubset(manifest_keys)
        or not manifest_keys.issubset(_REQUIRED_MANIFEST_KEYS | _OPTIONAL_MANIFEST_KEYS)
    ):
        raise ReactAdminArtifactError("react admin artifact manifest shape is invalid")
    if manifest["contract"] != "react-admin-artifact/v1" or manifest["root_entry"] != ROOT_ENTRY:
        raise ReactAdminArtifactError("react admin artifact manifest contract is invalid")
    try:
        artifact_version = validate_closed_identity(
            manifest["artifact_version"], "artifact version"
        )
        source_ref = validate_closed_identity(manifest["source_ref"], "source ref")
        registry = compatibility_registry or load_react_admin_api_compatibility_registry()
        api_revision = registry.require_accepted(manifest["api_compatibility_revision"])
    except ReactAdminApiCompatibilityError as error:
        raise ReactAdminArtifactError(
            "react admin artifact compatibility identity is invalid"
        ) from error
    if not isinstance(manifest["build_tools"], dict) or not manifest["build_tools"]:
        raise ReactAdminArtifactError("react admin build tool identity is invalid")
    if not isinstance(manifest["files"], list) or not manifest["files"]:
        raise ReactAdminArtifactError("react admin artifact file inventory is empty")
    files: dict[str, ArtifactFile] = {}
    for raw in manifest["files"]:
        if not isinstance(raw, dict) or set(raw) != {"path", "size", "sha256"}:
            raise ReactAdminArtifactError("react admin artifact file row is invalid")
        path = _canonical_relative_path(raw["path"])
        size = raw["size"]
        digest = raw["sha256"]
        if path == MANIFEST_NAME or path in files:
            raise ReactAdminArtifactError("react admin artifact file inventory is duplicated")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ReactAdminArtifactError("react admin artifact file size is invalid")
        if not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None:
            raise ReactAdminArtifactError("react admin artifact file digest is invalid")
        files[path] = ArtifactFile(path, size, digest)
    if ROOT_ENTRY not in files:
        raise ReactAdminArtifactError("react admin artifact root entry is missing")
    immutable_assets: set[str] = set()
    if "immutable_assets" in manifest:
        raw_immutable = manifest["immutable_assets"]
        if not isinstance(raw_immutable, list):
            raise ReactAdminArtifactError("react admin immutable asset inventory is invalid")
        for raw_asset_path in raw_immutable:
            normalized_asset = _canonical_relative_path(raw_asset_path)
            if (
                normalized_asset in immutable_assets
                or normalized_asset not in files
                or normalized_asset in {ROOT_ENTRY, MANIFEST_NAME}
                or not is_immutable_asset_path(normalized_asset)
            ):
                raise ReactAdminArtifactError("react admin immutable asset entry is invalid")
            immutable_assets.add(normalized_asset)
    actual_paths: set[str] = set()
    for candidate in root.rglob("*"):
        if candidate.is_symlink():
            raise ReactAdminArtifactError("react admin artifact cannot contain symlinks")
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(root).as_posix()
        if relative != MANIFEST_NAME:
            actual_paths.add(relative)
    if actual_paths != set(files):
        raise ReactAdminArtifactError("react admin artifact contains missing or extra files")
    for relative, expected in files.items():
        candidate = (root / PurePosixPath(relative)).resolve(strict=True)
        if not candidate.is_relative_to(root):
            raise ReactAdminArtifactError("react admin artifact file escapes its root")
        if candidate.stat().st_size != expected.size or _digest_file(candidate) != expected.sha256:
            raise ReactAdminArtifactError("react admin artifact file does not match its manifest")
    root_text = (root / ROOT_ENTRY).read_text(encoding="utf-8")
    if '<div id="root"></div>' not in root_text:
        raise ReactAdminArtifactError("react admin artifact root marker is missing")
    artifact_digest = manifest["artifact_digest"]
    if not isinstance(artifact_digest, str) or _SHA256_PATTERN.fullmatch(artifact_digest) is None:
        raise ReactAdminArtifactError("react admin artifact digest is invalid")
    canonical_payload = dict(manifest)
    canonical_payload.pop("artifact_digest")
    if _digest_bytes(_canonical_json(canonical_payload)) != artifact_digest:
        raise ReactAdminArtifactError("react admin artifact digest does not match its manifest")
    return ValidatedReactAdminArtifact(
        root=root,
        artifact_version=artifact_version,
        source_ref=source_ref,
        api_compatibility_revision=api_revision,
        artifact_digest=artifact_digest,
        manifest_digest=_digest_bytes(manifest_bytes),
        files=files,
        immutable_assets=frozenset(immutable_assets),
    )


def is_immutable_asset_path(relative_path: str) -> bool:
    if ".." in relative_path:
        return False
    path = PurePosixPath(relative_path)
    return (
        path.parent == PurePosixPath("assets")
        and _IMMUTABLE_ASSET_FILENAME_PATTERN.fullmatch(path.name) is not None
    )


def _canonical_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ReactAdminArtifactError("react admin artifact path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ReactAdminArtifactError("react admin artifact path is invalid")
    return path.as_posix()


def _is_link_like_directory(path: Path) -> bool:
    junction_checker = getattr(path, "is_junction", None)
    is_junction = bool(junction_checker()) if junction_checker is not None else False
    return path.is_symlink() or is_junction


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_compatibility_registry() -> ReactAdminApiCompatibilityRegistry:
    try:
        return load_react_admin_api_compatibility_registry()
    except ReactAdminApiCompatibilityError as error:
        raise ReactAdminArtifactError(
            "react admin api compatibility registry is unavailable"
        ) from error


__all__ = [
    "ASSET_ELIGIBILITY_HEADER",
    "ArtifactFile",
    "PRIVATE_IMMUTABLE_CACHE_CONTROL",
    "ReactAdminArtifactError",
    "ReactAdminArtifactRuntime",
    "ReactAdminStaticApplication",
    "ValidatedReactAdminArtifact",
    "is_immutable_asset_path",
    "load_react_admin_runtime_from_environment",
    "validate_react_admin_artifact",
]
