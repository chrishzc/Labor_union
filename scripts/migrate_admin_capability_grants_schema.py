"""Fail-closed marker for a retired standalone Access schema migration.

The cumulative schema is assembled from immutable release artifacts. No
current canonical runner imports this module, so it must not expose a second
DDL or transaction path while operator and release-window evidence is absent.
"""

from __future__ import annotations

import sys


MIGRATION_BLOCKED_REASON = (
    "standalone Access schema migration has no current canonical caller; "
    "use the governed preserve-data release chain after its gates pass"
)


def main() -> int:
    print(f"migration blocked: {MIGRATION_BLOCKED_REASON}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
