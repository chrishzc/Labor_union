from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = ("api", "domains", "infrastructure", "line", "scripts", "subsystems", "ui")
LEGACY_FIELDS = ("subsidy_refund_receivable", "subsidy_refund_refunded")
EVIDENCE_ONLY_PATHS = {
    "scripts/generate_formal_architecture_baseline.py",
    "scripts/validate_formal_architecture_baseline.py",
    "scripts/generate_writer_inventory_v3_candidate.py",
    "scripts/validate_writer_inventory_v3_candidate.py",
}


def test_runtime_code_never_uses_legacy_subsidy_refund_projection_fields():
    offenders = []
    for root in RUNTIME_ROOTS:
        for path in (PROJECT_ROOT / root).rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            relative_path = path.relative_to(PROJECT_ROOT).as_posix()
            if relative_path not in EVIDENCE_ONLY_PATHS and any(field in source for field in LEGACY_FIELDS):
                offenders.append(relative_path)

    assert offenders == []
