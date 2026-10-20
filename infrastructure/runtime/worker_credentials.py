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
SERVICES = (*WORKER_SERVICES, LINE_MEDIA_SERVICE)
FORMAT = "nas-worker-credentials/v1"


def read_verifiers(path: str | Path) -> dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("invalid worker credential format")
    values = data.get("services")
    if not isinstance(values, dict) or not values or set(values) - set(SERVICES):
        raise ValueError("invalid worker service registry")
    if any(not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value)
           for value in values.values()) or len(set(values.values())) != len(values):
        raise ValueError("invalid worker verifier")
    return values


def prepare_credentials(root: Path, *, services: tuple[str, ...] = SERVICES) -> None:
    """Create once; never overwrite or print existing machine credentials."""
    if not services or len(set(services)) != len(services) or set(services) - set(SERVICES):
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
