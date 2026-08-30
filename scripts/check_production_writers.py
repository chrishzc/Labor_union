"""Validate the checked-in, reviewed production SQL-writer inventory."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from shared_kernel.writer_inventory import (  # noqa: E402
    scan_production_writers,
    writer_scan_fingerprint,
)
from scripts.validate_writer_inventory_v3_dispositions import (  # noqa: E402
    validate as validate_dispositions,
)
from scripts.validate_writer_inventory_v3_candidate import (  # noqa: E402
    _require_blocked_records,
    _require_legacy_subsidy_projection_boundary,
)

EVIDENCE_DIRECTORY = (
    REPOSITORY_ROOT
    / "document"
    / "架構重整"
    / "03_追蹤清單與證據"
    / "evidence"
    / "writer_inventory_v3"
)
CANDIDATE_MANIFEST_PATH = EVIDENCE_DIRECTORY / "writer_inventory_v3_candidate.manifest.json"
CANDIDATE_FINDINGS_PATH = EVIDENCE_DIRECTORY / "writer_inventory_v3_candidate.findings.jsonl"
DISPOSITION_RECORDS_PATH = EVIDENCE_DIRECTORY / "writer_inventory_v3_disposition.records.jsonl"

# This is the scan boundary owned by the v3 candidate generator. Keeping the
# boundary explicit prevents a manipulated manifest from narrowing the live
# scan and turning an unreviewed writer into an apparent pass.
V3_SCAN_ROOTS = (
    "api",
    "domains",
    "infrastructure",
    "line",
    "scripts",
    "services",
    "subsystems",
)


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain an object")
    return payload


def _load_records(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError(f"{path.name} contains a non-object record")
        records.append(record)
    return records


def _validate_current_candidate() -> int:
    manifest = _load_json(CANDIDATE_MANIFEST_PATH)
    if manifest.get("contract") != "production-writer-inventory/v3-candidate":
        raise ValueError("unsupported writer inventory candidate contract")
    if tuple(manifest.get("roots", ())) != V3_SCAN_ROOTS:
        raise ValueError("writer inventory candidate scan roots are invalid")

    candidate_records = _load_records(CANDIDATE_FINDINGS_PATH)
    if manifest.get("finding_count") != len(candidate_records):
        raise ValueError("candidate manifest finding count differs from evidence")
    candidate_identities = {
        str(record.get("identity")) for record in candidate_records
    }
    if manifest.get("unique_identity_count") != len(candidate_identities):
        raise ValueError("candidate manifest identity count differs from evidence")
    if len(candidate_identities) != len(candidate_records):
        raise ValueError("candidate evidence contains duplicate identities")
    if manifest.get("evidence_sha256") != sha256(
        CANDIDATE_FINDINGS_PATH.read_bytes()
    ).hexdigest():
        raise ValueError("candidate manifest hash differs from evidence")

    current_findings = scan_production_writers(REPOSITORY_ROOT, V3_SCAN_ROOTS)
    current_identities = {finding.identity for finding in current_findings}
    if current_identities != candidate_identities:
        raise ValueError("current production writers differ from v3 candidate")
    if manifest.get("finding_count") != len(current_findings):
        raise ValueError("current production writer count differs from candidate")
    if manifest.get("scan_fingerprint") != writer_scan_fingerprint(current_findings):
        raise ValueError("current production writer fingerprint differs from candidate")

    # Reuse the candidate validator's exact fail-closed record and legacy
    # projection checks without invoking its generator (the gate is read-only).
    _require_blocked_records()
    _require_legacy_subsidy_projection_boundary(manifest)
    return len(candidate_records)


def _validate_current_dispositions() -> tuple[int, int]:
    result = validate_dispositions()
    records = _load_records(DISPOSITION_RECORDS_PATH)
    undecided = [
        str(record.get("identity"))
        for record in records
        if record.get("final_disposition") == "needs_decision"
    ]
    if undecided:
        raise ValueError(
            "writer inventory contains unreviewed identities: "
            f"{len(undecided)}"
        )
    return result["records"], result["approved_to_remove"]


def main() -> int:
    candidate_count = _validate_current_candidate()
    disposition_count, approved_to_remove = _validate_current_dispositions()
    if candidate_count != disposition_count:
        raise ValueError("candidate and disposition counts differ")
    print(
        "production writer inventory v3 verified: "
        f"candidate={candidate_count} dispositions={disposition_count} "
        f"approved_to_remove={approved_to_remove}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
