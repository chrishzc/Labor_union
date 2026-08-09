import json
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIRECTORY = (
    REPOSITORY_ROOT
    / "document"
    / "架構重整"
    / "03_追蹤清單與證據"
    / "evidence"
    / "writer_inventory_v3"
)
DISPOSITION_MANIFEST = EVIDENCE_DIRECTORY / "writer_inventory_v3_disposition.manifest.json"


def test_writer_inventory_v3_disposition_validator_accepts_full_coverage():
    candidate_identities = _identities("writer_inventory_v3_candidate.findings.jsonl")
    reviewed_identities = _identities("writer_inventory_v3_disposition.records.jsonl")
    manifest = json.loads(DISPOSITION_MANIFEST.read_text(encoding="utf-8"))
    result = subprocess.run(
        [sys.executable, "scripts/validate_writer_inventory_v3_dispositions.py"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert candidate_identities == reviewed_identities
    assert f"records={manifest['record_count']}" in result.stdout


def test_writer_inventory_v3_candidate_scans_services():
    from scripts.generate_writer_inventory_v3_candidate import ROOTS

    assert "services" in ROOTS


def test_writer_inventory_v3_receipts_close_legacy_scheduling_and_payroll_boundaries():
    records = _records("writer_inventory_v3_disposition.records.jsonl")
    scheduling_legacy = [
        record
        for record in records
        if record["owner"] == "scheduling"
        and "retired legacy matching communication transaction" in record["transaction_boundary"]
    ]
    payroll = [record for record in records if record["owner"] == "payroll"]

    assert not scheduling_legacy
    assert payroll
    assert all(record["final_disposition"] in {"retain_canonical", "retain_restricted"} for record in payroll)
    assert all("typed" in record["runtime_caller"].lower() for record in payroll)


def _identities(filename: str) -> set[str]:
    lines = (EVIDENCE_DIRECTORY / filename).read_text(encoding="utf-8").splitlines()
    return {str(json.loads(line)["identity"]) for line in lines if line}


def _records(filename: str) -> list[dict[str, str]]:
    lines = (EVIDENCE_DIRECTORY / filename).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line]
