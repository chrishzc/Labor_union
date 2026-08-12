---
doc_type: decision-package
status: superseded-by-work-package-51
superseded_by: ../work_packages/51_Preserve_Data_and_Historical_Reprocess_Closure_Work_Package.md
superseded_date: 2026-08-09
---

# Preserve-data Runner Completion Decision Package

> 歷史決策基線：本文件記錄 2026-08-09 實作前的缺口。公開 runner 的本機收斂已由
> `../work_packages/51_Preserve_Data_and_Historical_Reprocess_Closure_Work_Package.md` 授權並完成；專用
> source→backup→candidate→migration→switch→restart/read-smoke 演練仍為未執行的 external gate。

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

The public CLI now establishes the project import path before runner imports,
and validates a missing environment file before argument completeness. It
requires separate source-read/candidate-write descriptors, rejects operational
database names, verifies source read-only principal evidence and a
source-fingerprint-bound maintenance token, and writes append-only operation
receipts/journal entries. It also exposes `--complete-restart` and
`--recover-interrupted-switch`; absent target-host restart/read-smoke adapters
fail closed rather than claiming completion. Parser, preflight, journal,
recovery and metadata tests cover this public path.

The remaining gap is the deliberately unexecuted disposable MySQL rehearsal,
not the runner contract. Its integration test requires `MYSQL_TEST_CONTAINER`
and remains a visible external acceptance gate.

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

Work package 51 authorized the local runner implementation. This document and
work package 51 still do not authorize a connection, backup, schema migration,
environment-file switch, restart or database mutation against an operational
environment. A separate operator-approved package remains required for the
disposable-source rehearsal.
