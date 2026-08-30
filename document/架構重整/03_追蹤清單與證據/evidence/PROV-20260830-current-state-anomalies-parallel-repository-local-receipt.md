# Current-state Anomalies parallel repository-local receipt

date: 2026-08-30
owner: Anomalies Agent
execution_ssot: `PROV-20260830-current-state-anomaly-parallel-execution-refresh.md`
base_head: `6302647afb6cb168bacd4fc2660ea0f0df5670d9`
branch: `anomalies/current-state-slimming-parallel`
implementation_head_before_receipt: `eeb9663`
conclusion: `ANOMALIES_REPOSITORY_LOCAL_PARTIAL`

## Scope and effects

- Task 97 prerequisite was reused and not rerun as implementation work.
- No LINE source, shared hot spot, schema, migration, release assembly, production, `union_db`, provider,
  deployment, entry switch, destructive cleanup or published migration was modified.
- `GET /api/v1/anomalies` remains a current-row-only signed-cursor query. The canonical detail route is now
  `GET /api/v1/anomalies/{issue_key}`; the old 64-hex fingerprint remains a typed 410.
- The React `#anomalies` runtime renders only current rows and current typed detail. It does not render
  occurrence, import-warning tracking, claim, resolve or timeline UI, and it does not remove an issue before
  a fresh backend recheck makes the row absent.
- `CurrentIssueCandidate` no longer accepts a missing subject identity or a generic `subject_id` fallback.
- Zero-caller `FINANCE_OCCURRENCE` registry support and its two unregistered finance occurrence definition
  helpers were removed.

## 15-code contract matrix

All 15 codes have a closed subject schema and remain the only codes returned by
`default_anomaly_registry()`. The current producer/action source map is not terminal-ready, so repository-local
cutover cannot be declared complete.

| Code | Closed subject | Current owner detector/snapshot/lock/recheck | Manual owner action | Result |
|---|---|---|---|---|
| `SCHEDULE-006` | PASS | legacy producer; no current snapshot/lock/intent wiring | Preview only; no Apply/readback contract | `SPEC_GAP` |
| `PAYOUT-002` | PASS | legacy producer; no current snapshot/lock/intent wiring | Query-only | `SPEC_GAP` |
| `GOVSUB-001` | PASS | legacy producer; no current snapshot/lock/intent wiring | Preview only; no Apply | `SPEC_GAP` |
| `GOVSUB-002` | PASS | legacy producer; no current snapshot/lock/intent wiring | Preview only; no Apply | `SPEC_GAP` |
| `GOVSUB-003` | PASS | projects legacy revisions; no current bounded absence scan | Query-only | `SPEC_GAP` |
| `GOVSUB-004` | PASS | projects legacy coordinates; no current bounded absence scan | Preview only; no Apply | `SPEC_GAP` |
| `GOVSUB-005` | PASS | legacy producer; no current snapshot/lock/intent wiring | Query-only | `SPEC_GAP` |
| `GOVSUB-007` | PASS | positive-only legacy producer; no authoritative absence scan | no action | `SPEC_GAP` |
| `IMPORT-003` | PASS | legacy producer; no current snapshot/lock/intent wiring | Query-only | `SPEC_GAP` |
| `IMPORT-006` | PASS | legacy producer; no current snapshot/lock/intent wiring | no action | `SPEC_GAP` |
| `BECLASS-001` | PASS | legacy producer; no current snapshot/lock/intent wiring | no action | `SPEC_GAP` |
| `SCHEDULE-002` | PASS | legacy producer currently emits unconditional active state | no action | `SPEC_GAP` |
| `SCHEDULE-003` | PASS | closed identity enforces canonical pair ordering; producer remains legacy | no action | `SPEC_GAP` |
| `LINE-004` | PASS | typed LINE conflict owner query is absent | no action | `WAIT_PEER_LINE_CONTRACT` |
| `LINE-006` | PASS | typed LINE timeline repository port/result is absent | Query-only timeline | `WAIT_PEER_LINE_CONTRACT` |

The public current detail projection is closed and fails on unknown evidence fields, but a per-code closed
`details_version=1` source map is not present. This remains part of each non-terminal row above.

## Legacy semantics disposition

- Removed: `AnomalyProjectionKind.FINANCE_OCCURRENCE`, `_finance_manual_review_definition`, and
  `_client_refund_return_definition`; exact current inbound caller count was zero and the 15-code registry
  plus owner pages are the current replacement.
- Rewritten: canonical current detail API, current list/detail React client, current page adapter and runtime
  page entry. The old anomaly-recovery detail URL is hidden from OpenAPI and retained only as a bounded
  internal compatibility route.
- Kept because current inbound callers remain: `AlertWorkflowStatus`, `CurrentAlertProjection`,
  `AnomalyApplication.project`, `claim_alert`, `resolve_alert_workflow`, workflow timeline persistence,
  and the legacy React component characterization tests. Deletion would currently violate the zero-caller
  gate; producers, MySQL adapters and Streamlit anomaly callers still depend on them.
- Kept separately: finance-import occurrence terminology that owns import membership/integrity facts; it is
  not anomaly occurrence history.

## Verification

| Gate | Result |
|---|---|
| Focused current API/domain | PASS: 47 tests |
| Anomalies canonical root plus current Task 97/API bootstrap | PASS: 173 tests |
| Cross-domain workflow boundary set | PASS: 18 tests |
| 12-owner collect-only | PASS: 1,799 collected |
| 12-owner canonical execution | PASS: 1,797 passed, 2 skipped |
| Full non-engine Python | PARTIAL: 4,763 passed, 141 skipped, 3 xfailed, 7 failed; one basetemp-policy case passed on isolated replay, remaining six are shared Task 97 entry/commit artifact drift |
| React affected current tests | PASS: 21 tests |
| React full suite | PASS: 185 files, 1,222 tests |
| React production build | PASS; existing chunk-size warning retained |
| Agent governance | PASS |
| Verification baseline validator | PASS schema; baseline itself remains intentionally incomplete |
| Python fatal Flake8 | `NOT_RUN_TOOL_UNAVAILABLE` |
| Changed-Python compile | PASS |
| `git diff --check` | PASS |

One initial parallel 12-owner run produced 59 setup errors because concurrent pytest processes removed a
shared `.pytest_tmp` parent. The isolated absolute-basetemp replay above is the current result and had no
failures.

## Blockers and follow-up

- `WAIT_PEER_LINE_CONTRACT`: LINE-004 needs a typed LINE identity-conflict query/result; LINE-006 needs a
  typed notification-timeline query/result and repository port. No LINE source was modified.
- The other 13 codes remain `SPEC_GAP`: current owner predicates, authoritative subject universes,
  owner snapshot/version, canonical owner-lock mappings, terminal Query/Preview/Apply descriptors,
  owner readback and same-transaction durable recheck intent wiring are absent. The formal specification
  does not supply exact owner operation/input contracts, so this lane did not invent them.
- `INTEGRATION_WRITER_FOLLOWUP`: refresh the shared `.arch-map` Anomalies leaves/tests after final merge;
  update shared formal index/current execution status and Task 97 governance artifacts only from a fresh
  integration head; reconcile the shared API entry inventory for `GET /api/v1/anomalies/{issue_key}` and
  regenerate the source-revision-bound commit disposition artifact. These forbidden shared writes account
  for the six remaining full-suite failures after the isolated basetemp-policy replay passed.
- `DEFERRED_DB_ACCEPTANCE`: DB 1016 engine verification has no authorized `lu_test_*` target in this run.
  The three known allowlisted-engine modules were excluded from the full non-engine gate.
- Production, provider, deployment, entry switch, destructive legacy table cleanup and published migration
  rewrite were not run and are not claimed complete.
