# Superseded broader candidate v7 rehearsal observation

Date: 2026-08-09

An isolated MySQL 8.4 container bound only to `127.0.0.1:33327` completed
bootstrap, source-safety dry-run, source backup, and candidate restore for
`labor-union-2026-08-09-v7`.  No existing `mysql_db` or deployment environment
was accessed.

The schema apply stopped fail-closed in `106_order_lifecycle_control_facts.sql`.
The source principal is correctly restricted to `SELECT`, `SHOW VIEW`, and
`USAGE`; it cannot obtain `TRIGGER`.  Therefore `mysqldump --triggers` omits
trigger definitions, while the later trigger-drift guard requires them.  Giving
that principal `TRIGGER` would violate the source read-only contract.

This observation came from a broader source-preserving rehearsal.  It is not a
blocker for this retirement acceptance: the 2026-08-09 manual decision narrowed
the local dry-run objective to proving that no schema part or migration can
recreate a retired structure.  It explicitly does not authorize a new
schema-dump principal or trigger-reading mechanism.

The retirement check is therefore the static schema-and-migration scan for the
retired table and its triggers, backed by the release manifest/schema gates and
the relevant pytest suite.  This receipt remains as historical evidence of the
abandoned broader rehearsal; it does not claim that its switch, restart, or
read-smoke steps ran.
