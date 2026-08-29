"""Migrate bootstrap receipts to preserve adopted Scheduling versions."""

import sys

MIGRATION_BLOCKED_REASON = (
    "no current canonical runner caller for release artifact "
    "187_case_architecture_bootstrap_receipt_version_contract.sql"
)


def main() -> int:
    print(f"migration blocked: {MIGRATION_BLOCKED_REASON}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
