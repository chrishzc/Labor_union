"""NAS machine credentials: per-service tokens and API-only SHA-256 verifiers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import secrets


WORKER_SERVICES = (
    "durable-job-worker", "knowledge-retrieval-worker", "line-worker",
    "incident-worker", "runtime-monitor",
)
LINE_MEDIA_SERVICE = "line-media-proxy"
LINE_OPERATIONS_SERVICE = "line-operations-proxy"
SERVICES = (*WORKER_SERVICES, LINE_MEDIA_SERVICE)
FORMAT = "nas-worker-credentials/v1"


def read_verifiers(path: str | Path, *, allowed_services: tuple[str, ...] = SERVICES) -> dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("invalid worker credential format")
    values = data.get("services")
    if not isinstance(values, dict) or not values or set(values) - set(allowed_services):
        raise ValueError("invalid worker service registry")
    if any(not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value)
           for value in values.values()) or len(set(values.values())) != len(values):
        raise ValueError("invalid worker verifier")
    return values


def prepare_credentials(root: Path, *, services: tuple[str, ...] = SERVICES) -> None:
    """Create once; never overwrite or print existing machine credentials."""
    if not services or len(set(services)) != len(services) or set(services) - {*SERVICES, LINE_OPERATIONS_SERVICE}:
        raise ValueError("invalid service selection")
    targets = [root / service / "token" for service in services]
    registry = root / "api" / "verifiers.json"
    if registry.exists() or any(path.exists() for path in targets):
        raise ValueError("existing worker credentials; refusing to overwrite")
    values = {}
    for service, target in zip(services, targets):
        token = secrets.token_urlsafe(32)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as stream:
            stream.write(token + "\n")
        target.chmod(0o400)
        values[service] = hashlib.sha256(token.encode("ascii")).hexdigest()
    registry.parent.mkdir(parents=True, exist_ok=True)
    with registry.open("x", encoding="utf-8") as stream:
        json.dump({"format": FORMAT, "services": values}, stream, sort_keys=True)
        stream.write("\n")
    registry.chmod(0o400)


def ensure_line_operations_credentials(root: Path) -> None:
    """Add the NAS LINE bridge without altering the existing Worker registry."""
    token_file = root / LINE_OPERATIONS_SERVICE / "token"
    registry = root / "api" / "verifiers.json"
    if not token_file.exists() and not registry.exists():
        prepare_credentials(root, services=(LINE_OPERATIONS_SERVICE,))
        return
    if not token_file.is_file():
        raise ValueError("partial LINE operations credentials; existing files preserved")
    token = token_file.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token):
        raise ValueError("invalid LINE operations credential; existing files preserved")
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    expected = {LINE_OPERATIONS_SERVICE: digest}
    if registry.exists():
        if read_verifiers(registry, allowed_services=(LINE_OPERATIONS_SERVICE,)) != expected:
            raise ValueError("LINE operations verifier mismatch; existing files preserved")
        return
    # Resume a first-time interruption after token creation, keeping that token.
    registry.parent.mkdir(parents=True, exist_ok=True)
    with registry.open("x", encoding="utf-8") as stream:
        json.dump({"format": FORMAT, "services": expected}, stream, sort_keys=True)
        stream.write("\n")
    registry.chmod(0o400)
