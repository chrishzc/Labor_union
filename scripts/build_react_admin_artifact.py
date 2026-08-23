"""
File: build_react_admin_artifact.py
Description: 建立或唯讀檢查 versioned immutable React 管理端 artifact。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

from infrastructure.runtime.react_admin_artifact import (
    MANIFEST_NAME,
    ROOT_ENTRY,
    ReactAdminArtifactError,
    validate_react_admin_artifact,
)
from infrastructure.runtime.react_admin_api_compatibility import (
    ReactAdminApiCompatibilityError,
    ReactAdminApiCompatibilityRegistry,
    load_react_admin_api_compatibility_registry,
    validate_closed_identity,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = PROJECT_ROOT / "ui_react"
DEFAULT_DIST = UI_ROOT / "dist"


def build_artifact(
    output: Path,
    *,
    source: Path = DEFAULT_DIST,
    source_ref: str | None = None,
    api_compatibility_revision: str | None = None,
    run_frontend_build: bool = False,
    production: bool = False,
    compatibility_registry: ReactAdminApiCompatibilityRegistry | None = None,
) -> dict[str, object]:
    output_path = output.resolve(strict=False)
    if output_path.exists():
        raise ReactAdminArtifactError("react admin artifact output already exists")
    if run_frontend_build:
        with tempfile.TemporaryDirectory(prefix="react-admin-frontend-build-") as directory:
            generated_source = Path(directory)
            _run_frontend_build(generated_source)
            return build_artifact(
                output,
                source=generated_source,
                source_ref=source_ref,
                api_compatibility_revision=api_compatibility_revision,
                production=production,
                compatibility_registry=compatibility_registry,
            )
    if source.is_symlink() or source.is_junction():
        raise ReactAdminArtifactError("react admin build source must be a real directory")
    source_root = source.resolve(strict=True)
    if source_root == PROJECT_ROOT.resolve() or source_root == output_path:
        raise ReactAdminArtifactError("react admin artifact source or output is unsafe")
    source_files = _source_files(source_root)
    if ROOT_ENTRY not in {item.relative_to(source_root).as_posix() for item in source_files}:
        raise ReactAdminArtifactError("react admin build source has no index.html")
    registry = compatibility_registry or _load_compatibility_registry()
    if production and (source_ref is None or api_compatibility_revision is None):
        raise ReactAdminArtifactError(
            "production react admin build requires explicit release and compatibility identities"
        )
    try:
        source_identity = validate_closed_identity(
            source_ref if source_ref is not None else "working-tree",
            "source ref",
        )
        api_revision = registry.require_accepted(
            api_compatibility_revision
            if api_compatibility_revision is not None
            else registry.active_revision
        )
    except ReactAdminApiCompatibilityError as error:
        raise ReactAdminArtifactError(
            "react admin artifact identity is invalid"
        ) from error
    output_path.parent.mkdir(parents=True, exist_ok=True)
    parent = output_path.parent.resolve(strict=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_path.name}.", dir=parent))
    try:
        for source_file in source_files:
            relative = source_file.relative_to(source_root)
            destination = temporary / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, destination, follow_symlinks=False)
        inventory = _inventory(temporary)
        content_identity = _digest_bytes(_canonical_json(inventory))[:16]
        manifest: dict[str, object] = {
            "contract": "react-admin-artifact/v1",
            "artifact_version": f"react-admin-{content_identity}",
            "source_ref": source_identity,
            "build_tools": _build_tool_versions(),
            "api_compatibility_revision": api_revision,
            "root_entry": ROOT_ENTRY,
            "files": inventory,
        }
        manifest["artifact_digest"] = _digest_bytes(_canonical_json(manifest))
        (temporary / MANIFEST_NAME).write_bytes(_canonical_json(manifest) + b"\n")
        validate_react_admin_artifact(
            temporary,
            workspace_root=PROJECT_ROOT,
            compatibility_registry=registry,
        )
        temporary.replace(output_path)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    validated = validate_react_admin_artifact(
        output_path,
        workspace_root=PROJECT_ROOT,
        compatibility_registry=registry,
    )
    return validated.health_attestation("current")


def _run_frontend_build(output: Path) -> None:
    node = _node_executable()
    commands = (
        [node, UI_ROOT / "node_modules/typescript/bin/tsc", "-b"],
        [
            node,
            UI_ROOT / "node_modules/vite/bin/vite.js",
            "build",
            "--outDir",
            output,
            "--emptyOutDir",
        ],
    )
    for command in commands:
        if not Path(command[1]).is_file():
            raise ReactAdminArtifactError("react admin frontend build tool is unavailable")
        completed = subprocess.run(
            [str(part) for part in command], cwd=UI_ROOT, check=False
        )
        if completed.returncode != 0:
            raise ReactAdminArtifactError("react admin frontend build failed")


def _node_executable() -> Path:
    executable = shutil.which("node.exe" if os.name == "nt" else "node")
    if executable is not None:
        return Path(executable).resolve(strict=True)
    specification = importlib.util.find_spec("playwright")
    if specification is not None and specification.submodule_search_locations:
        package_root = Path(next(iter(specification.submodule_search_locations)))
        bundled = package_root / "driver" / ("node.exe" if os.name == "nt" else "node")
        if bundled.is_file():
            return bundled.resolve(strict=True)
    raise ReactAdminArtifactError("node executable is unavailable")


def _source_files(source_root: Path) -> tuple[Path, ...]:
    if not source_root.is_dir() or source_root.is_symlink():
        raise ReactAdminArtifactError("react admin build source must be a real directory")
    files: list[Path] = []
    for candidate in source_root.rglob("*"):
        if candidate.is_symlink():
            raise ReactAdminArtifactError("react admin build source cannot contain symlinks")
        if candidate.is_file():
            if candidate.name == MANIFEST_NAME:
                raise ReactAdminArtifactError("react admin build source cannot contain a manifest")
            files.append(candidate)
    if not files:
        raise ReactAdminArtifactError("react admin build source is empty")
    return tuple(sorted(files))


def _inventory(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        rows.append({"path": relative, "size": path.stat().st_size, "sha256": _digest_file(path)})
    return rows


def _build_tool_versions() -> dict[str, str]:
    package = json.loads((UI_ROOT / "package.json").read_text(encoding="utf-8"))
    return {
        "builder": "scripts.build_react_admin_artifact/v1",
        "node": os.getenv("NODE_VERSION", "managed-runtime"),
        "vite": str(package.get("devDependencies", {}).get("vite", "unknown")),
    }


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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--source", type=Path, default=DEFAULT_DIST)
    parser.add_argument("--source-ref")
    parser.add_argument("--api-compatibility-revision")
    parser.add_argument("--skip-frontend-build", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.build:
            if arguments.output is None or arguments.artifact is not None:
                raise ReactAdminArtifactError("--build requires only --output")
            result = build_artifact(
                arguments.output,
                source=arguments.source,
                source_ref=arguments.source_ref,
                api_compatibility_revision=arguments.api_compatibility_revision,
                run_frontend_build=not arguments.skip_frontend_build,
                production=True,
            )
        else:
            if arguments.artifact is None or arguments.output is not None:
                raise ReactAdminArtifactError("--check requires only --artifact")
            result = validate_react_admin_artifact(
                arguments.artifact, workspace_root=PROJECT_ROOT
            ).health_attestation("current")
    except (OSError, ReactAdminArtifactError, ValueError) as error:
        print(f"REACT_ADMIN_ARTIFACT_INVALID: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
