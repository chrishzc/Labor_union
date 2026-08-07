---
doc_type: decision-package
---

# Preserve-data Runner Completion Decision Package

## 1. Fresh live finding

The repository already contains useful lower-level contracts:

- `infrastructure/migration/mysql_safety.py` can inspect and validate a
  read-only source principal.
- `infrastructure/migration/maintenance.py` defines maintenance-window token
  validation.
- `infrastructure/migration/journal.py` and `cutover.py` provide append-only
  DDL/switch journals and crash-state reconciliation.
- `infrastructure/migration/verification.py` provides restart/read-smoke
  orchestration.
- `scripts/migrate_preserved_database_additive_schema.py` implements backup,
  restore, additive apply, verification, switch and rollback-switch.

The direct public CLI entrypoint has been repaired: it now establishes the
project import path before importing runner modules, and it delays release
manifest validation until parsed source/candidate input is valid.  Thus
`--help` and invalid-input rejection do not attempt a database connection;
valid operations still fail closed on a protected-artifact digest mismatch.
The repair is covered by subprocess tests and the migration-focused suite
(`27 passed`).

The public CLI parser exposes `--check`, `--dry-run`, `--backup`, `--restore`,
`--apply`, `--verify`, `--switch`, `--complete-restart`, and
`--rollback-switch`. `--complete-restart` does invoke
`complete_cutover_after_restart` with bounded candidate runtime/read-smoke
ports. The CLI still neither accepts nor invokes source-principal evidence or
a maintenance token, and it does not expose interrupted-switch recovery.
There is also no dedicated preserve-data/cutover test suite found under
`tests/`.

This is a real execution-chain gap, not merely missing documentation.

## 2. Required public workflow

The runner must expose an explicit sequence, with each phase persisting a
strict UTF-8 receipt and a stable fingerprint:

`preflight → backup → restore candidate → additive migration → verification
→ switch → restart/read-smoke completion → recovery or rollback`.

Preflight requires both a source database identity and mechanical evidence that
the source connection principal is SELECT-only.  Plan, backup and switch also
require an unexpired, scoped maintenance/write-freeze token.  Candidate write
credentials are separate from source read credentials.

`recover-interrupted-switch` must resolve only the documented digest states;
an ambiguous state fails closed.  `complete-after-restart` must call the
declared restart targets and read smokes, append a completion receipt, and
refuse to mark a switch complete on any failure.

## 3. Safe implementation sequence

1. Add CLI inputs for separate source/candidate connection descriptors,
   source-principal evidence, maintenance token and receipt locations.  Do not
   source credentials from the ordinary application `.env` implicitly.
2. Wire preflight before every source-reading or switch-capable mode.
3. Add explicit `--recover-interrupted-switch`; retain and test the existing
   `--complete-restart` mode with its pluggable restart/read-smoke adapters.
4. Add module tests for principal privilege rejection, token expiry/scope,
   journal-chain drift, each crash state and UTF-8/digest enforcement.
5. Add a disposable-MySQL rehearsal covering the required full sequence and
   recovery.  It must use neither `union_db` nor an operational database.

## 4. Rollback invariant

Rollback only restores the previous environment database selection through a
new append-only receipt.  It never deletes source/candidate databases, dumps,
journal entries, backup artifacts or migrated facts.  A failed restart/read
smoke leaves the switch incomplete and requires recovery/rollback; it cannot
be reported as a successful cutover.

## 5. Authorization boundary

This decision package performs no connection, backup, schema migration,
environment-file switch, restart or database mutation.  A separate work
package must authorize the runner implementation; a further package must
authorize the disposable-source rehearsal.
