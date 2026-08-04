"""Fail closed when post-legacy writer evidence drifts from live source."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIRECTORY = REPOSITORY_ROOT / "document" / "架構重整" / "evidence" / "writer_inventory_v3"
MANIFEST_PATH = EVIDENCE_DIRECTORY / "writer_inventory_v3_candidate.manifest.json"
FINDINGS_PATH = EVIDENCE_DIRECTORY / "writer_inventory_v3_candidate.findings.jsonl"
GENERATOR_PATH = REPOSITORY_ROOT / "scripts" / "generate_writer_inventory_v3_candidate.py"


def _read_manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _evidence_hash() -> str:
    return sha256(FINDINGS_PATH.read_bytes()).hexdigest()


def _require_blocked_records() -> int:
    records = [json.loads(line) for line in FINDINGS_PATH.read_text(encoding="utf-8").splitlines()]
    if not records:
        raise ValueError("candidate evidence is empty")
    if any(record["effective_disposition"] != "blocked" for record in records):
        raise ValueError("candidate evidence contains an effective disposition")
    if any(record["approved_to_remove"] is not False for record in records):
        raise ValueError("candidate evidence contains removal approval")
    if any(record["requires_strong_model_review"] is not True for record in records):
        raise ValueError("candidate evidence is missing strong-model review gate")
    if any(not isinstance(record["high_risk_tags"], list) for record in records):
        raise ValueError("candidate evidence has an invalid high-risk tag set")
    if any(not record["writer_type_candidate"].endswith("_candidate") for record in records):
        raise ValueError("candidate evidence has an invalid writer type")
    if any(not record["recommendation_candidate"].endswith("_candidate") for record in records):
        raise ValueError("candidate evidence has an invalid recommendation")
    return len(records)


def _require_legacy_subsidy_projection_boundary(manifest: dict[str, object]) -> None:
    boundary = manifest.get("legacy_subsidy_projection_boundary")
    if not isinstance(boundary, dict):
        raise ValueError("legacy subsidy projection boundary is missing")
    if boundary.get("table") != "client_payments":
        raise ValueError("legacy subsidy projection table is invalid")
    if boundary.get("fields") != [
        "subsidy_refund_receivable",
        "subsidy_refund_refunded",
    ]:
        raise ValueError("legacy subsidy projection fields are invalid")
    if boundary.get("semantic_role") != "legacy_projection_only_not_client_finance_ssot":
        raise ValueError("legacy subsidy projection semantic role is invalid")
    if boundary.get("runtime_field_callers") != []:
        raise ValueError("legacy subsidy projection has runtime callers")
    if boundary.get("writer_disposition") != "blocked_no_removal_authorization":
        raise ValueError("legacy subsidy projection disposition is invalid")


def main() -> int:
    subprocess.run([sys.executable, str(GENERATOR_PATH)], cwd=REPOSITORY_ROOT, check=True)
    manifest = _read_manifest()
    count = _require_blocked_records()
    _require_legacy_subsidy_projection_boundary(manifest)
    if manifest["finding_count"] != count:
        raise ValueError("manifest finding count differs from evidence")
    if manifest["evidence_sha256"] != _evidence_hash():
        raise ValueError("manifest evidence hash differs from evidence")
    print(f"writer_inventory_v3_candidate_validated findings={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
