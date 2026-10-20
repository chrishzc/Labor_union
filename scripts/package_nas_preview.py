"""Prepare a secret-free, isolated NAS preview build context and handoff bundle."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = {"api", "config", "db", "domains", "infrastructure", "line", "scripts",
                 "shared_kernel", "subsystems", "validation", "ui_react"}
METADATA = {"requirements.txt", "pyproject.toml", ".python-version"}
SECRET_SUFFIXES = {".pem", ".key", ".pfx", ".p12", ".sqlite", ".sqlite3", ".db", ".log"}
SYNOLOGY_IMAGE = "chris23144638/cecec:nas-test-20261016"
WEB_SETUP_IMAGE = "chris23144638/cecec:nas-websetup-r2-20261016"


def _git(*args: str, binary: bool = False):
    result = subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True)
    return result.stdout if binary else result.stdout.decode("utf-8").strip()


def include_source(name: str) -> bool:
    path = PurePosixPath(name)
    if name not in METADATA and path.parts[0] not in RUNTIME_ROOTS:
        return name == "document/line/AI客服QA題庫.jsonl"
    if any(part in {"node_modules", "__pycache__", "dist", "scratch"} for part in path.parts):
        return False
    lower = path.name.lower()
    if lower.startswith(".env") or lower.endswith(".env") or lower in {
        "credentials.json", "token.json", "token", "verifiers.json", ".npmrc", ".pypirc", "pip.conf",
    }:
        return False
    if lower.startswith(("service_account", "client_secret")) or path.suffix.lower() in SECRET_SUFFIXES:
        return False
    return True


def _use_patched_previous_ui_toolchain(context: Path) -> None:
    """Patch historical build tools only when every other manifest fact agrees."""
    current = context / "ui_react"
    previous = context / "previous_ui"
    manifests = [json.loads((folder / "package.json").read_text(encoding="utf-8"))
                 for folder in (current, previous)]
    for manifest in manifests:
        for name in ("vitest", "happy-dom"):
            manifest.get("devDependencies", {}).pop(name, None)
    if manifests[0] != manifests[1]:
        raise ValueError("historical frontend dependencies differ; review its toolchain before building")
    runtime_locks = []
    for folder in (current, previous):
        lock = json.loads((folder / "package-lock.json").read_text(encoding="utf-8"))
        runtime_locks.append({name: tuple(package.get(key) for key in ("version", "resolved", "integrity"))
                              for name, package in lock["packages"].items() if name and not package.get("dev")})
    if runtime_locks[0] != runtime_locks[1]:
        raise ValueError("historical frontend runtime lock differs; review before building")
    for name in ("package.json", "package-lock.json"):
        shutil.copyfile(current / name, previous / name)


def prepare(output: Path, *, secure: bool = False) -> dict:
    from scripts.compact_fresh_schema import SQL_PATH, load_compact_plan
    from infrastructure.runtime.react_admin_api_compatibility import load_react_admin_api_compatibility_registry
    output = output.resolve()
    if output.exists():
        raise ValueError("output exists; choose a new directory")
    plan = load_compact_plan()  # Hash-bound canonical fresh DDL; never historical DROP scripts.
    head = _git("rev-parse", "HEAD")
    dirty_ui = bool(_git("status", "--porcelain", "--", "ui_react"))
    if dirty_ui:
        previous_ref = head
    else:
        last_ui_change = _git("log", "-1", "--format=%H", "--", "ui_react")
        previous_ref = _git("rev-parse", f"{last_ui_change}^")
    output.mkdir(parents=True)
    context = output / "build-context"
    context.mkdir()
    names = _git("ls-files", "--cached", "--others", "--exclude-standard", "-z", binary=True)
    for raw in names.split(b"\0"):
        if not raw:
            continue
        name = raw.decode("utf-8")
        source = ROOT / name
        if not include_source(name) or not source.is_file():
            continue
        if source.is_symlink() or not source.resolve().is_relative_to(ROOT):
            raise ValueError("source links are not allowed in the NAS build context")
        destination = context / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    # Test tools are not runtime dependencies and need not enter this image.
    requirements = (context / "requirements.txt").read_text(encoding="utf-8")
    (context / "requirements.txt").write_text("\n".join(
        line for line in requirements.splitlines()
        if not line.startswith(("pytest==", "schemathesis=="))) + "\n", encoding="utf-8")
    archive = _git("archive", previous_ref, "ui_react", binary=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as snapshot:
        for member in snapshot.getmembers():
            path = PurePosixPath(member.name)
            if not member.isfile() or not include_source(member.name) or ".." in path.parts:
                continue
            destination = context / "previous_ui" / Path(*path.parts[1:])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(snapshot.extractfile(member).read())
    source_ref = f"nas-{head[:12]}-working" if _git("status", "--porcelain") else head
    metadata = {"source_ref": source_ref, "previous_source_ref": previous_ref,
                "api_revision": load_react_admin_api_compatibility_registry().active_revision,
                "schema_release": plan["release_id"], "image": "labor-union-nas-test:local",
                "platform": "linux/amd64", "previous_ui_note": "historical source build, not an attested deployed rollback",
                "working_tree_included": True}
    if secure:
        # Preserve historical application sources; share only the audited build
        # manifests after proving unrelated dependencies and scripts agree.
        _use_patched_previous_ui_toolchain(context)
        metadata["previous_ui_dependency_source"] = "current audited frontend manifests; historical application sources preserved"
        # Keep the secret-filtered context and real previous frontend source;
        # never send the repository root or ignored local files to Docker.
        files = ("deployment/nas/Dockerfile", "deployment/nas/20-lock-legacy-app.sql", "deployment/nas/mysql-client.cnf",
                 "deployment/nas-test/99-ready.sh", "deployment/nas-test/web-setup/index.html",
                 "deployment/nas-test/web-setup/setup.js")
        for name in files:
            destination = context / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)
        shutil.copyfile(ROOT / "deployment/nas/Dockerfile", context / "Dockerfile")
        (context / ".dockerignore").write_text(
            "**/.env\n**/.env.*\n**/*.env\n**/credentials.json\n**/token.json\n**/token\n**/verifiers.json\n"
            "**/.npmrc\n**/.pypirc\n**/pip.conf\n**/*.pem\n**/*.key\n**/*.pfx\n**/*.p12\n"
            "**/node_modules\n**/__pycache__\n**/*.py[cod]\n.git\n", encoding="utf-8")
        css = (ROOT / "ui_react/src/pages/LoginPage.css").read_text(encoding="utf-8")
        (context / "nas-setup-style.css").write_text(css + "\n*{box-sizing:border-box}body{margin:0;font-family:system-ui,sans-serif}"
            "[hidden]{display:none!important}\n", encoding="utf-8")
        for filename in ("compose.yaml", ".env.example", "compose.tunnel.yaml", "cloudflared.example.yaml", "README.md"):
            shutil.copyfile(ROOT / "deployment/nas" / filename, output / filename)
        metadata.update(image="chris23144638/cecec:nas-secure-20261019-r2", mode="nas-security/v1",
                        database_engine_qualification="not_run", image_build="not_run", image_published=False)
        (output / "bundle.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return metadata
    for filename in ("compose.yaml", "nas.sh", "README.md", "limits.env.example"):
        shutil.copyfile(ROOT / "deployment/nas-test" / filename, output / filename)
    shutil.copyfile(ROOT / "deployment/nas-test/Dockerfile", context / "Dockerfile")
    (output / "init").mkdir()
    shutil.copyfile(SQL_PATH, output / "init/10-fresh-schema.sql")
    shutil.copyfile(ROOT / "deployment/nas-test/20-restrict-app.sh", output / "init/20-restrict-app.sh")
    (output / "bundle.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata


def prepare_synology(output: Path, source_bundle: Path) -> dict:
    """Adapt an already-built bundle for DSM; never rebuild or publish its image."""
    import yaml

    output = output.resolve()
    source_bundle = source_bundle.resolve()
    if output.exists() or output.with_suffix(".zip").exists():
        raise ValueError("output exists; choose a new directory")
    # Reuse the schema shipped with the existing image, not newer working-tree DDL.
    checksums = dict(line.split("  ", 1)[::-1] for line in
                     (source_bundle / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines())
    copied = ("bundle.json", "verification.json", "init/10-fresh-schema.sql", "init/20-restrict-app.sh")
    for name in copied:
        if hashlib.sha256((source_bundle / name).read_bytes()).hexdigest() != checksums.get(name):
            raise ValueError(f"source bundle checksum mismatch: {name}")
    metadata = json.loads((source_bundle / "bundle.json").read_text(encoding="utf-8"))
    verification = json.loads((source_bundle / "verification.json").read_text(encoding="utf-8"))
    if metadata["image"] != "labor-union-nas-test:local":
        raise ValueError("unsupported source image")

    app = yaml.safe_load((ROOT / "deployment/nas-test/compose.yaml").read_text(encoding="utf-8"))
    line = app["services"].pop("line-check")
    for service in (app["services"]["api"], line):
        service["image"] = SYNOLOGY_IMAGE
        service["pull_policy"] = "never"
    for service in (*app["services"].values(), line):
        if "env_file" in service:
            service["env_file"] = "../" + service["env_file"]
        service["volumes"] = ["../" + item[2:] if item.startswith("./") else item
                              for item in service.get("volumes", [])]
    runtime_mount = "../runtime/nas_test_runtime.py:/app/scripts/nas_test_runtime.py:ro"
    for service in (app["services"]["api"], line):
        service["volumes"].append(runtime_mount)
    app["networks"]["app"]["name"] = "lu-nas-preview-app"
    app["volumes"]["app-data"]["external"] = True
    # DSM can reach the bridge IP directly. Publish no host port, including
    # localhost: older NAS Docker engines have a documented L2 isolation caveat.
    app["services"]["api"].pop("ports")
    app["services"]["db"]["healthcheck"]["test"] = [
        "CMD-SHELL", "test -f /var/lib/mysql/.lu-preview-initialized && "
        "mysqladmin --host=127.0.0.1 ping --silent"]
    line.pop("profiles")
    line.pop("depends_on")
    line["networks"] = ["app"]
    line_project = {"name": "lu-nas-preview-line-check", "services": {"line-check": line},
                    "networks": {"app": {"external": True, "name": "lu-nas-preview-app"}}}
    initialization = {
        "name": "lu-nas-preview-prepare",
        "services": {"prepare": {
            "image": SYNOLOGY_IMAGE, "pull_policy": "never", "user": "0:0", "restart": "no",
            "network_mode": "none", "read_only": True,
            "tmpfs": ["/tmp:rw,noexec,nosuid,size=64m"],
            "security_opt": ["no-new-privileges:true"], "cpus": 0.25, "mem_limit": "384m",
            "command": ["python", "-c", "import os; from pathlib import Path; "
                        "from scripts.nas_test_runtime import prepare; os.umask(0o022); "
                        "Path('/settings').chmod(0o700); prepare()"],
            "volumes": ["../settings:/settings", "app-data:/data", runtime_mount],
            "logging": {"driver": "json-file", "options": {"max-size": "1m", "max-file": "2"}},
        }},
        "volumes": {"app-data": {"name": "lu-nas-preview-app-data"}},
    }
    output.mkdir(parents=True)
    for folder, config in (("01-prepare", initialization), ("02-app", app), ("03-line-check", line_project)):
        target = output / folder / "docker-compose.yml"
        target.parent.mkdir()
        target.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (output / "settings").mkdir()
    (output / "init").mkdir()
    (output / "runtime").mkdir()
    shutil.copyfile(ROOT / "scripts/nas_test_runtime.py", output / "runtime/nas_test_runtime.py")
    # mysql CLI otherwise decodes the unprefixed Chinese system seed as latin1.
    # This is session framing only; preserve every byte of the frozen DDL/seeds.
    (output / "init/10-fresh-schema.sql").write_bytes(
        b"SET NAMES utf8mb4;\n" + (source_bundle / copied[2]).read_bytes())
    # Execute the original grants as SQL, independent of bind-mount executable
    # bits: an executable .sh cannot rely on the entrypoint's shell functions.
    grants = (source_bundle / copied[3]).read_text(encoding="utf-8")
    if "<<'SQL'\n" not in grants or not grants.endswith("\nSQL\n"):
        raise ValueError("unsupported grants script framing")
    (output / "init/20-restrict-app.sql").write_text(
        grants.split("<<'SQL'\n", 1)[1].removesuffix("SQL\n"), encoding="utf-8", newline="\n")
    shutil.copyfile(ROOT / "deployment/nas-test/99-ready.sh", output / "init/99-ready.sh")
    shutil.copyfile(ROOT / "deployment/nas-test/README.synology.md", output / "README.md")
    metadata.update(image=SYNOLOGY_IMAGE, source_image_digest=verification["image_digest"],
                    mode="synology-gui", image_rebuild=False,
                    source_init_sha256={name: checksums[name] for name in copied[2:]},
                    runtime_override_sha256=hashlib.sha256(
                        (output / "runtime/nas_test_runtime.py").read_bytes()).hexdigest(),
                    nas_gui_and_https_verification="not_run")
    (output / "bundle.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files = sorted(path for path in output.rglob("*") if path.is_file())
    (output / "SHA256SUMS.txt").write_text("".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(output).as_posix()}\n"
        for path in files), encoding="utf-8")
    with zipfile.ZipFile(output.with_suffix(".zip"), "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("settings/", "")
        for path in sorted(output.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(output).as_posix())
    return metadata


def prepare_web_setup(output: Path, source_bundle: Path) -> dict:
    """Create a bounded image-layer context and a single-project GUI handoff."""
    output, source_bundle = output.resolve(), source_bundle.resolve()
    if output.exists():
        raise ValueError("output exists; choose a new directory")
    checksums = dict(line.split("  ", 1)[::-1] for line in
                     (source_bundle / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines())
    init_files = ("10-fresh-schema.sql", "20-restrict-app.sql", "99-ready.sh")
    for name in ("bundle.json", *("init/" + item for item in init_files)):
        if hashlib.sha256((source_bundle / name).read_bytes()).hexdigest() != checksums.get(name):
            raise ValueError("source bundle checksum mismatch")
    metadata = json.loads((source_bundle / "bundle.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True)
    context = output / "build-context"
    sources = ("scripts/nas_test_runtime.py", "scripts/nas_appliance.py", "api/routes/nas_setup.py",
               "subsystems/access/authentication_session.py", "deployment/nas-test/web-setup/index.html",
               "deployment/nas-test/web-setup/setup.js")
    for name in sources:
        target = context / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    (context / "nas-init").mkdir()
    for name in init_files:
        shutil.copyfile(source_bundle / "init" / name, context / "nas-init" / name)
    shutil.copyfile(ROOT / "deployment/nas-test/99-ready.sh", context / "nas-init/99-ready.sh")
    shutil.copyfile(ROOT / "deployment/nas-test/Dockerfile.web-setup", context / "Dockerfile")
    css = (ROOT / "ui_react/src/pages/LoginPage.css").read_text(encoding="utf-8")
    (context / "nas-setup-style.css").write_text(css + "\n*{box-sizing:border-box}body{margin:0;font-family:system-ui,sans-serif;color:#1e1b19}"
        "small{line-height:1.5;color:#74593f}#message{line-height:1.5;color:#9b3429}"
        "button:disabled{opacity:.65;cursor:wait}#complete{line-height:1.8}"
        "[hidden]{display:none!important}\n", encoding="utf-8")
    shutil.copyfile(ROOT / "deployment/nas-test/compose.web-setup.yaml", output / "docker-compose.yml")
    shutil.copyfile(ROOT / "deployment/nas-test/line-check.web-setup.yaml", output / "line-check.yml")
    shutil.copyfile(ROOT / "deployment/nas-test/README.web-setup.md", output / "README.md")
    metadata.update(image=WEB_SETUP_IMAGE, base_image="labor-union-nas-test:local",
                    mode="nas-web-setup/v1", image_rebuild=True,
                    base_image_digest=metadata["source_image_digest"],
                    nas_gui_and_https_verification="not_run")
    metadata.pop("runtime_override_sha256", None)
    metadata["layer_sha256"] = {p.relative_to(context).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sorted(context.rglob("*")) if p.is_file()}
    (output / "bundle.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--secure", action="store_true", help="Prepare the separate, full NAS security image context")
    mode.add_argument("--synology-from", type=Path,
                        help="Existing verified bundle whose image is already on Docker Hub")
    mode.add_argument("--web-setup-from", type=Path,
                      help="Verified GUI bundle whose initialization SQL will be baked into the image")
    args = parser.parse_args()
    if args.web_setup_from:
        result = prepare_web_setup(args.output, args.web_setup_from)
    else:
        result = prepare_synology(args.output, args.synology_from) if args.synology_from else prepare(args.output, secure=args.secure)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
