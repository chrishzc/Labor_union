"""Allow persisted Holiday Query-only leave/substitution batches."""

import sys

MIGRATION_BLOCKED_REASON = (
    "no current canonical runner caller for release artifact "
    "180_leave_substitution_holiday_only_batch_contract.sql"
)


def main() -> int:
    print(f"migration blocked: {MIGRATION_BLOCKED_REASON}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
