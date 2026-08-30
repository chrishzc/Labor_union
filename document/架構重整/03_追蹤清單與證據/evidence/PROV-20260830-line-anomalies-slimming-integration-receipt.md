# LINE／Current-state Anomalies slimming integration receipt

date: 2026-08-30
owner: Integration Writer
artifact_role: `validation_receipt`
consumer: PR #63 reviewers；PR #63 merge後用來取代PR #61／#62的平行lane狀態
evidence_authority: evidence only；不是新規格、mutation Authority或deployment授權
retention: bounded；PR #63 merge且current規格／程式吸收結論後可依artifact lifecycle退役
close_condition: PR #63 merge，或candidate source identity改變而由successor receipt取代
conclusion: `PARALLEL_SLIMMING_INTEGRATION_COMPLETE`

## Candidate identity and integration order

| Identity | Revision |
|---|---|
| fresh `origin/main` base | `6302647afb6cb168bacd4fc2660ea0f0df5670d9` |
| LINE PR #62 head | `39d9d24cf357546fec919cf346123e7656395812` |
| Anomalies PR #61 head | `1ad1dbb9d7fbbbcf62de28338ccde52db6cd7ba9` |
| validated integration code head | `9bd05fd3e735d1020471c5c7d8498a7447672ef6` |
| integration PR | [#63](https://github.com/chrishzc/Labor_union/pull/63) |

Integration order was fixed as `LINE #62 → Anomalies #61 → LINE-004 typed consumer → shared governance`.
The two source PRs remain open; they are not merged or closed by this integration run.

## Integrated write set

- LINE／Scheduling runtime: `line/`, `subsystems/line/`, LINE provider／MySQL adapters and their focused tests.
- Current-state Anomalies: domain／subsystem／API／React current-only identity, list/detail and typed 410 behavior.
- Cross-task implementation: LINE-004 typed current-fact consumer, MySQL adapter, Anomalies runtime/job composition and focused integration tests.
- Shared Integration Writer ownership: affected `.arch-map` leaves／tests／root／meta, Task 97 entry governance,
  production-script inventory, commit dispositions, writer inventory／dispositions and formal baseline.
- Current status projections: formal index, feature-plan index, evidence index and this receipt.

No schema, migration, release assembly, DB engine, production data, provider execution, deployment, entry switch,
destructive cleanup, secret or external side effect was added or run.

## LINE-004 typed current-fact closure

`LINE-004` now reads LINE identity state only through the typed
`MySqlLineIdentityManagementRepository.current_fact` boundary. Anomalies does not query LINE private tables.
The detector builds a complete deterministic owner snapshot and fingerprint, uses the closed subject
`{subject_type, line_user_id}`, and exposes only redaction-safe reason codes and root-condition state.

The current predicate emits an issue for same-role duplicate bindings or a role-specific root/projection
mismatch. A legal customer+staff dual role and the current single-row root-schema limitation are explicitly
suppressed and are not misclassified as an anomaly. LINE-004 is state-only and therefore has no invented
manual action descriptor. `LINE-006` remains deferred.

## 15-code disposition

| Result | Codes |
|---|---|
| `PASS / typed owner consumer` | `LINE-004` |
| `DEFERRED_OWNER_CONTRACT` | `SCHEDULE-006`, `SCHEDULE-002`, `SCHEDULE-003`, `GOVSUB-001`, `GOVSUB-002`, `GOVSUB-003`, `GOVSUB-004`, `GOVSUB-005`, `GOVSUB-007`, `PAYOUT-002`, `IMPORT-003`, `IMPORT-006`, `BECLASS-001`, `LINE-006` |

Closed identity and current-only projection for all 15 codes do not imply that the remaining 14 owner
predicates, locks, operations or readbacks exist. This receipt does not upgrade those gaps.

## Before／after slimming metrics

| Boundary | Before | After |
|---|---:|---:|
| Orders direct `line_group_id` writer path | 1 | 0 |
| Client identity direct root writer path | 1 | 0; delegated to owner boundary |
| Scheduling legacy `enqueue_line_task` caller | 1 | 0 |
| Normal-runtime `line/worker.py` direct `requests.post/delete` provider calls | 5 | 0; test compatibility hook only |
| `_upsert_legacy_role` call sites | 4 | 0; helper and SQL removed |

## Milestone disposition

| Milestone | Result | Boundary |
|---|---|---|
| M1 identity semantics | `passed / PARTIAL` | Repository-local contract and regressions pass; browser sandbox checks skipped because LINE sandbox config was absent. Dual-role schema redesign remains deferred. |
| M2 deterministic current anomaly | `passed` | LINE-004 is a deterministic typed current-fact detector; no speculative AI classification was added. |
| M3 delivery convergence | `passed / PARTIAL` | Legacy Scheduling caller removed and delivery contract verified; candidate contact-pool contract remains deferred. |
| M4 provider／timeline convergence | `passed / PARTIAL` | Runtime provider bypass removed; disposable-MySQL preserve-data check was skipped because no container was available, and LINE-006 remains deferred. |

## Shared governance reconciliation

- Canonical `GET /api/v1/anomalies/{issue_key}` entry is registered with its typed React caller and tests.
- LINE current-fact HTTP entry is classified `review_required / blocked_external_evidence`; no external caller
  was inferred from absence of static callers.
- Entry queue is regenerated to 684 rows: 489 active, 86 retired 410, 75 operator and 34 review-required.
- Task 97 entry governance, production-script inventory, 301 commit dispositions, 1,299 writer
  inventory／dispositions and 1,299-row formal baseline were regenerated from the integrated source.
- Obsolete direct `_ConnectionUnitOfWork.commit` identities for client binding and user lifecycle were removed,
  the matching communication digest was refreshed, and affected Arch Map projections were reconciled.

## Verification

| Gate | Result |
|---|---|
| Focused LINE current-fact boundary | `passed`: 30 tests |
| Anomalies canonical root | `passed`: 154 tests |
| LINE canonical root | `passed`: 522 tests |
| Orders + Scheduling | `passed`: 571 passed, 1 skipped |
| M1–M4 and cross-task set | `passed`: 184 passed, 4 skipped |
| Explicit conditional checks | `passed / PARTIAL`: 3 passed, 4 environment skips (3 browser sandbox, 1 disposable MySQL) |
| Cross-domain exact boundary files | `passed`: 18 tests |
| 12 owner-domain collection／execution | `passed`: 1,805 collected; 1,803 passed, 2 skipped |
| Full non-engine Python | `passed`: 4,787 passed, 141 skipped, 3 xfailed |
| React affected suite | `passed`: 46 files, 291 tests |
| React full suite | `passed`: 185 files, 1,222 tests |
| React production build | `passed`; existing chunk-size warning unchanged |
| React lint | `passed`; 7 existing warnings |
| Agent governance／compileall／fatal Flake8／`git diff --check` | `passed` |
| GitHub checks on validated code head | `passed`: 14 successful, 0 failed／pending／skipped |

## Deferred boundary and closeout

There are no repository-local integration blockers. M1 schema, M3 candidate delivery, M4 LINE-006, the
other 13 owner contracts, DB engine／preserve-data execution, production, provider, deployment and destructive
cutover remain deferred and unauthorized by this receipt.

The integration result is `PARALLEL_SLIMMING_INTEGRATION_COMPLETE`; the bounded product conclusions remain
`ANOMALIES_REPOSITORY_LOCAL_PARTIAL` and `LINE_BACKEND_SLIMMING_REPOSITORY_LOCAL_PARTIAL`.
