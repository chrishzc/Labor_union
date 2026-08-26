---
doc_type: work-package
declared_status: approved
date: 2026-08-26
owner: Scheduling
current_task: CUR-LINE-BABYLOG-MEDIA-01
authority: 96 current register and 20 §5.4 current execution authorization
---

# CUR-LINE-BABYLOG-MEDIA-01 服務日日誌受控媒體工作包

## 1. Current specification and convergence

Canonical owners are `00_Global_共同契約.md` §2.2, `20_LINE客服與月嫂自助服務正式規格.md` §5.4,
`96_Current_剩餘代辦任務總表.md`, and the NAS and LINE Rich Menu feature plans. Current Authority approves
verified LIFF staging, digest/version, Preview/Apply, cleanup/reconciliation, authenticated download, and required
`lu_test_*` schema gates. No provider or production effect is included.

```yaml
specification_status: SPEC_READY
convergence:
  status: READY
  blockers: []
research:
  route: R0
  disposition: NO_RESEARCH
```

## 2. Requirements and acceptance

- `BM-REQ-01`: only a server-verified current staff binding with a visible assignment/service day may stage JPG/PNG.
- `BM-REQ-02`: Scheduling owns `baby_log_photo` and `meal_photo`; LINE only transports bytes and identity evidence.
- `BM-REQ-03`: log Preview is zero-write and binds assignment, service day, text, cooking fact, staging digest/version and kind.
- `BM-REQ-04`: Apply fresh-locks the same facts and commits controlled-file registration, attachment links, log, event,
  receipt and outbox in one outer MySQL transaction; same-key replay returns the original result.
- `BM-REQ-05`: `requires_cooking=true` needs at least one meal photo; unresolved cooking, stale staging, digest drift,
  subject mismatch, duplicate reference, unauthorized access or transaction failure fails closed.
- `BM-REQ-06`: LIFF/readback exposes only typed file metadata and authenticated staff-scoped download, never a NAS locator.
- `BM-ACC-01`: verified LIFF stage → Preview → confirm → Apply → DB/readback succeeds for a cooking service day.
- `BM-ACC-02`: non-cooking text-only compatibility remains; legacy media rows remain readable and are not backfilled.
- `BM-ACC-03`: cleanup/reconciliation continue to own abandoned staging and storage/metadata drift.

## 3. Scope, write set and effect ceiling

In scope: service-day media schemas/routes/workflow/repository, `staff_schedule.html`, additive schema/release metadata,
focused tests, current specification/status and final evidence. The sole tracked-file writer is the parent agent.

Excluded: `union_db`, production mount/provider, deployment, public URLs, watcher-owned completion, direct LINE media
storage, destructive cleanup, legacy row backfill and unrelated UI redesign.

Safe stop conditions: owner/public-contract drift, non-additive migration, existing owned-object `partial|drift`, unknown
DB target, or any native patch exceeding 30 seconds.

## 4. Independent entry gates

### Necessity

| Step | Requirement or failure path | Decision |
|---|---|---|
| Replace direct LINE media store with O1 staging | `BM-REQ-01/02/03`; current route bypasses O1 | `required_now` |
| Compose controlled registration and Scheduling Apply | `BM-REQ-04/05`; partial commit is forbidden | `required_now` |
| Add controlled attachment relation while retaining legacy column | `BM-REQ-04`, `BM-ACC-02` | `required_now` |
| Add staff-scoped typed readback/download | `BM-REQ-06` | `required_now` |
| Provider delivery or production mount | outside current effect ceiling | `required_later` |

### Source basis and reuse

| Source | Exact basis | Decision |
|---|---|---|
| Authority/specification | 2026-08-26 amendments in `20` §5.4 and `96` | `reuse` |
| Controlled files | current `subsystems/controlled_files/` and schema 1004 | `reuse` |
| Scheduling text log | current Domain/workflow/repository/routes and schema 204 | `copy-adapt` |
| Legacy LIFF media route | direct `FileSystemLineMediaObjectStore` path | `reject` as new caller path |
| External dependency/code | none required | `reject` |

Entry status: `PASS`. Package status: `PACKAGE_READY`.

## 5. DB change inventory and gates

| Class | Candidate effect | Replay/rollback |
|---|---|---|
| `schema-only` | additive controlled-file FK/index and attachment-kind expansion; legacy provider reference becomes nullable | release/descriptor; discard candidate before switch |
| `system-seed` | none | not applicable |
| `business-row-backfill` | none; legacy media remains legacy | not applicable |
| `destructive` | none | forbidden |

Required order: scope → inventory → static release → descriptor → read-only plan → disposable fresh → preserve-data
candidate → developer acceptance. Any `BLOCKED` or `NOT_RUN` gate keeps the summary `DB_CHANGE_NOT_READY`.

## 6. Coverage and verification

| Requirement / acceptance | Package step | Direct oracle |
|---|---|---|
| `BM-REQ-01/02` | verified staging adapter | route deny-path and content-sniff tests |
| `BM-REQ-03/05` | media-aware Preview | zero-write, cooking, stale/digest/owner tests |
| `BM-REQ-04` | borrowed controlled-file workflow in outer UoW | rollback/replay repository and disposable MySQL tests |
| `BM-REQ-06` | readback/download projection | another-staff denial and no-locator response tests |
| `BM-ACC-01/02` | LIFF caller and compatibility | static LIFF contract, API integration and text-only regressions |
| `BM-ACC-03` | reuse O1 cleanup/reconciliation | existing focused suites plus attachment orphan observation |

Retry ceiling is one only for a newly evidenced transient failure. Unknown Apply outcome permits readback/reconcile only.
Retain final redacted receipts and release evidence; remove task-local intermediate plans/logs after closure.
