---
doc_type: work-package
declared_status: approved
identity: PROV-20260817-react-admin-phase5-entry-navigation-switch-decision
date: 2026-08-17
owner: Global Entry Point Governance / Integration Owner
authority: awaiting-exact-human-approval
approval_required: 核准此 exact Phase 5 Entry Navigation Switch Decision Work Package，並採用 Option A
approval_evidence: user-replied-核准此-exact-Phase-5-Entry-Navigation-Switch-Decision-Work-Package-Option-A
source_gap: PROV-20260817-react-admin-phase5-entry-navigation-switch-policy-gap
prerequisites: none for this control-plane decision; applying a specific switch later requires only that entry's readiness plus relevant Phase5A/5B runtime evidence
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: control-plane contract or Phase5A mapping drift requires fresh read and re-freeze
db_change: none
---

# Phase 5：Entry navigation switch Option A control-plane 決策工作包

## 0. Exact decision and current-turn boundary

Recommended **Option A** is frozen as an application-owned, versioned, file-backed entry target map. It provides
single-entry CAS, audit receipt, React/Streamlit target resolution and rollback without adding a DB table or schema.

The existing exact approval phrase is retained:

> 核准此 exact Phase 5 Entry Navigation Switch Decision Work Package，並採用 Option A

This decision can be approved independently of all bounded pages, Global runtime, Scenario and DB gates. It does not
switch an entry. A later production implementation package builds the control plane, and each later per-entry command
still requires that entry's own readiness/observation authority.

This docs-refinement turn modifies only this existing Work Package. It does not modify the source gap, production,
tests, queue, pages, launchers, README/main plan, navigation target or entry status.

## 1. Canonical owner and non-goals

Owner: `Global Entry Point Governance / Admin Presentation Routing`.

The owner controls only which presentation target opens for one known administrative entry. It does not own:

- Domain/API data, mutation, authorization or business status;
- React/Streamlit page implementation or health internals;
- deployment artifact production, reverse proxy, launcher or worker;
- entry discovery/rollback mapping (Phase 5A remains source authority);
- three-service local runtime (Phase 5B remains runtime foundation);
- retirement/deletion (Phase 6 remains owner).

Queue disposition and page readiness are inputs, never the runtime target store. Hash fragments are client navigation
inside a selected React shell and are not server routing keys.

## 2. File-backed state contract (no DB schema)

### 2.1 Checked-in contract and initial state

The production successor will own:

- `config/admin_entry_targets.schema.json`: strict schema/version contract;
- `config/admin_entry_targets.initial.json`: immutable boot/default state with every known entry targeting Streamlit;
- a deployment-configured writable `ADMIN_ENTRY_TARGET_STATE_PATH` for runtime state.

Production must explicitly configure the runtime path on durable local storage. It must not write into Git files,
source tree, `/tmp`, current working directory, browser storage or DB. Missing/unreadable/unwritable path fails closed.

### 2.2 Single atomic state file

One strict JSON state owns both target map and receipt chain so map/receipt cannot commit separately:

```text
schema_version: 1
revision: integer >= 1
entries: exact known entry records
receipts: append-only logical receipt array
state_digest: sha256 of canonical state excluding state_digest
```

Each entry record contains:

```text
entry_id
replacement_group
current_target: streamlit | react
streamlit_target: exact Phase5A rollback path/query
react_target: profile-neutral relative path `/admin/#<canonical-hash>`
required_react_artifact: version + digest or null while unavailable
entry_revision: integer >= 1
```

The store takes an OS-level exclusive lock, strict-decodes the whole state, verifies digest and receipt chain, writes a
same-directory temporary file, flushes, then atomic-replaces the state. Unsupported filesystems or lost locks fail
closed. Startup never silently recreates a corrupt/missing production state from defaults.

There are only 11 React candidates over 10 Streamlit rollback identities. The Phase5A `staff-scheduling` group remains
one-to-many: `#staff` and `#scheduling` have independent entry records/revisions and share only the Streamlit module.

## 3. One-entry CAS command

The control plane accepts exactly one entry per command:

```text
entry_id
expected_state_revision
expected_entry_revision
expected_current_target
desired_target: streamlit | react
required_artifact_version/digest (required when desired_target=react)
reason_code
idempotency_key
actor
correlation_id
```

Apply algorithm:

1. lock and strict-read latest state;
2. verify known entry, whole-state digest/receipt chain, state/entry revisions and expected current target;
3. reject arrays, wildcards, groups and any command that implies more than one entry;
4. for React, verify the exact released artifact binding and the entry-specific health/readiness predicate;
5. change one entry only, increment global and that entry's revision by one, append one receipt, atomically replace;
6. read back and return the stored receipt.

Same idempotency key + same canonical command returns the identical stored receipt with `replayed=true`; same key with
different command is typed 409. Stale revision/target/artifact is typed 409. Lock/storage/artifact unavailability is
typed 503 and performs zero state change.

Bulk switch, implicit group switch, `all`, unknown entry, unknown target, prototype name and manifest-only identity all
fail before write.

## 4. Audit receipt

Each receipt is non-secret and contains:

```text
receipt_id
idempotency_key
entry_id
before_target / resulting_target
before_state_revision / resulting_state_revision
before_entry_revision / resulting_entry_revision
artifact_version / artifact_digest (nullable for Streamlit)
actor_id
reason_code
correlation_id
occurred_at
previous_receipt_digest
receipt_digest
replayed
```

No token, password, TOTP, PII, arbitrary URL, raw environment, business payload or exception text is allowed. Audit
receipts prove control-plane state only; they never prove the page/business workflow succeeded.

## 5. Target resolution

### Streamlit target

`streamlit_target` is the exact sanitized rollback deep link frozen by Phase5A, including fixed subview where needed.
It is not a user-supplied URL. Staff/Scheduling resolve respectively to the fixed `calendar` and `staff-directory`
subviews of the shared Streamlit calendar module.

### React target

The state stores only same-origin relative `/admin/#<canonical-hash>` plus immutable artifact binding. Local host/port
is supplied by the Phase5B runtime profile; production origin/artifact is supplied by the later hosting release. No
entry or page hard-codes `5173`, host names or proxy topology.

### Fail-closed runtime behaviour

- unknown entry: reject; do not select a default business page;
- corrupt/missing/stale state: route only to a safe authenticated shell/error surface, not React;
- target=`react` but artifact/health unavailable: use the entry's fixed Streamlit rollback target for this request,
  emit a bounded control-plane alert, and require an operator CAS rollback to change stored target;
- target=`streamlit`: always use the Phase5A exact rollback resolver;
- unauthenticated requests preserve only the sanitized entry identity through login; no arbitrary URL/query survives.

Automatic runtime fallback is not a state mutation and cannot generate a successful rollback receipt.

## 6. Rollback semantics

Rollback is the same one-entry CAS command with `desired_target=streamlit`. It requires fresh revisions, expected
current=`react`, reason/idempotency/actor/correlation and returns the same typed receipt shape. It does not rollback
Domain data, DB rows, API commands, audit history or deployment artifacts.

Before switching the next entry, the current entry must have either:

- completed its declared observation window and retained a verified rollback rehearsal; or
- been explicitly CAS-rolled back with a stored receipt.

## 7. Minimal future production successor

After this decision is exactly approved, the production control-plane successor may be bounded to:

- `config/admin_entry_targets.schema.json` (new)
- `config/admin_entry_targets.initial.json` (new)
- `subsystems/access/admin_entry_target_control.py` (new)
- `infrastructure/file/admin_entry_target_store.py` (new)
- `api/schemas/admin_entry_targets.py` (new)
- `api/routes/admin_entry_targets.py` (new)
- focused file-store/CAS/route/integrity tests
- dedicated control-plane evidence

Pages, launchers, DB/schema, queue generator, React/Streamlit navigation and deployment files are not part of that
minimal control-plane successor. Runtime consumers and per-entry switching remain later separately approved packages.

## 8. Preconditions by action (not global DAG)

| Action | Minimum prerequisite |
|---|---|
| approve this decision | none beyond current Phase5A mapping evidence |
| implement file-backed control plane | this decision approved; Phase5A identity/rollback contract frozen |
| exercise control plane locally | Phase5B relevant runtime profile available |
| switch one entry to React | that entry's page/readiness/rollback/artifact/health evidence only |
| switch another entry | prior switched entry observation or rollback receipt complete |
| retire one Streamlit entry | that entry's Phase6 retirement gate only |

No unrelated page, Global Scenario, DB engine or provider gate is required for a different entry's switch.

## 9. Decision acceptance

1. Option A, owner, state path policy and no-DB choice are explicit.
2. Strict schema, digest, lock, atomic replace and corruption handling are defined.
3. One-entry CAS/idempotency/audit receipt and same-key replay are defined.
4. 11 React/10 Streamlit identities and one-to-many Staff/Scheduling semantics are preserved.
5. React and Streamlit targets are profile-neutral, sanitized and unknown-safe.
6. Artifact unavailable, runtime fallback and explicit rollback are distinct.
7. This turn produces no runtime target change, production code, queue/status change or switch receipt.

## 10. Exact docs write set for this refinement

- this existing decision Work Package only.

The source gap and production gap remain historical inputs and are not modified, duplicated or silently closed.
Shared README/main plan synchronization is deferred to Integration handoff.

## 11. DB gate

| Gate | Status | Reason |
|---|---|---|
| Scope | `PASS` | docs-only no-DB control-plane decision |
| Change inventory | `PASS` | schema/seed/backfill/destructive all zero |
| Static release | `NOT_RUN` | no DB release |
| Descriptor | `NOT_RUN` | no DB object |
| Read-only plan | `NOT_RUN` | no migration |
| Engine verification | `NOT_RUN` | no DB task |
| Developer acceptance | `NOT_RUN` | no DB operation |

Conclusion: `DB_CHANGE_NOT_READY`; no DB change is needed for the selected file-backed control plane.
