"""Fail closed if formal architecture evidence no longer matches live source."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = PROJECT_ROOT / "scripts" / "generate_formal_architecture_baseline.py"
EVIDENCE_PATH = PROJECT_ROOT / "document" / "架構重整" / "evidence" / "formal_baseline_v1.json"


def _payload() -> dict[str, object]:
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def _digest() -> str:
    return sha256(EVIDENCE_PATH.read_bytes()).hexdigest()


def main() -> int:
    subprocess.run([sys.executable, str(GENERATOR)], cwd=PROJECT_ROOT, check=True)
    payload = _payload()
    if payload["legacy_projection_boundary"]["runtime_callers"]:
        raise ValueError("legacy subsidy-refund projection is used by runtime code")
    if payload["legacy_projection_boundary"]["legacy_module_callers"]:
        raise ValueError("legacy subsidy-return reconciliation module has runtime callers")
    if payload["legacy_projection_boundary"]["retired_legacy_module_path_exists"]:
        raise ValueError("retired subsidy-return reconciliation module exists")
    if not all(payload["api_route_wiring"].values()):
        raise ValueError("required finance routes are not mounted")
    if not all(payload["schema_evidence"].values()):
        raise ValueError("required client-finance schema evidence is missing")
    print(f"formal_architecture_baseline_validated sha256={_digest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
