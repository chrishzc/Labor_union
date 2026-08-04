"""Validate the checked-in production SQL-writer baseline."""

from __future__ import annotations

from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from shared_kernel.writer_inventory import validate_writer_inventory

BASELINE_PATH = (
    REPOSITORY_ROOT / "config" / "production_writer_inventory.v1.json"
)


def main() -> int:
    findings = validate_writer_inventory(REPOSITORY_ROOT, BASELINE_PATH)
    print(f"production writer inventory verified: {len(findings)} findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
