# HCM Import Result Review evidence matrix draft

> Status: `DRAFT_INPUT_ONLY`。本matrix不是approval、production evidence或DB授權。

## 1. Existing capability inventory

| Capability | Current public surface | Disposition |
|---|---|---|
| HCM apply aggregate | `POST /api/v1/case-import/hcm/workbooks/apply` → `HcmWorkbookReceiptView` | counts only；不能列本次case membership |
| Recent HCM receipts | none | `MINIMAL_SAME_PAGE_HARDENING`：typed GET over existing `admin_command_receipts` |
| Problem task list | `GET /api/v1/import-warning-tracking/tasks` | `EXISTING_GET`；去敏field/issues/status/navigation，但無batch filter |
| Problem referral | `GET /api/v1/import-warning-tracking/tasks/{occurrence}/referral` | `EXISTING_GET`；單筆安全owner導向 |
| Order summaries | `GET /api/v1/orders/summaries` | 不可作batch membership authority |

## 2. Missing authority

| Required answer | Current source | Gap |
|---|---|---|
| 本次新增哪些訂單 | HCM terminal receipt counts + per-case import receipts | workbook receipt沒有case_no／row outcomes；per-case receipts沒有workbook digest |
| 哪些列／欄位有問題 | HCM review rows + warning tasks | durable facts存在，但HCM receipt沒有problem/referral identities |
| reload後重看結果 | `admin_command_receipts.result_snapshot` | table可讀，但沒有public GET；old snapshot只有counts |

禁止用receipt時間、actor、case event順序、status或Orders summary差集補洞。

## 3. Proposed receipt row contract

| Field | Contract |
|---|---|
| `source_row` | positive integer |
| `case_no` | canonical case number or null |
| `outcome` | `inserted | inserted_with_warning | exact_replay | review_required | failed` |
| `problem_identity` | HCM review identity or null |
| `problem_fields` | stable field paths only；no source values |
| `issue_codes` | stable codes only |
| `referral_occurrence_identities` | deterministic warning occurrence identities |

Conservation：row count等於source row count；aggregate counts等於row outcome分類。`inserted_with_warning`
同時屬新增清單與問題清單；`exact_replay`不算新增。

## 4. Recent result GET contract

```text
GET /api/v1/case-import/hcm/workbooks/results
  ?limit=1..50
  [&before_receipt_id=<positive integer>]
```

| Response field | Rule |
|---|---|
| `receipt_id` | positive integer cursor identity |
| `source_content_digest` | lowercase SHA-256；UI可短碼顯示 |
| `completed_at` | server timestamp |
| aggregate counts | strict nonnegative integers |
| `row_outcomes_available` | false for legacy count-only snapshot |
| `legacy_summary_only` | true only whenold snapshot cannot prove membership |
| `row_outcomes` | strict row contract；legacy fixed empty + explicit unavailable |
| `next_cursor` | positive receipt id or null |

No idempotency key、raw snapshot、filename、token、source values或PII。

## 5. UI slot matrix

| Stable ID | Source | Expected DOM |
|---|---|---|
| `imports.hcm-results.receipt.<id>` | recent result GET | receipt summary／time／digest/counts |
| `imports.hcm-results.new-orders` | `inserted*` rows | 本次新增case list |
| `imports.hcm-results.new-order.<case>` | one row | case_no + exact outcome |
| `imports.hcm-results.problems` | warning/review rows | source row、field paths、issue codes |
| `imports.hcm-results.problem.<identity>` | problem identity | masked review item |
| `imports.hcm-results.problem.referral.<occurrence>` | existing warning task/referral | safe navigation only |
| `imports.hcm-results.replays` | `exact_replay` rows | independent replay list |
| `imports.hcm-results.legacy-unavailable` | legacy snapshot | membership unavailable；not empty success |
| `imports.hcm-results.empty` | no receipts | honest empty state |
| `imports.hcm-results.error` | typed failure | retryable query error；no stale DOM |

## 6. Request budget

| Operation | Max |
|---|---:|
| Initial results load | 1 recent-results GET |
| Explicit refresh | 1 GET per click |
| Expand/collapse receipt | 0 |
| Warning task enrichment | 1 existing tasks GET per explicit receipt expansion |
| Referral navigation | 0 mutation |
| File selection／upload／Preview／Apply | 0 |

## 7. Gate template

| Gate | Status before approval | Required evidence |
|---|---|---|
| G0 scope/supersession | BLOCKED | exact approval；Preview page WP superseded |
| G1 receipt authority | NOT_RUN | row membership + problem identity + conservation tests |
| G2 recent GET | NOT_RUN | strict route/repository/auth/cursor/legacy/0-commit tests |
| G3 React result view | NOT_RUN | new/problem/replay/legacy/loading/error DOM |
| G4 warning navigation | NOT_RUN | exact occurrence match；pending projection state |
| G5 request/anti-fake | NOT_RUN | budgets；0 upload/Preview/Apply/non-GET |
| G6 browser query | NOT_RUN | real TOTP GET-only Network↔DOM；no file gate |

## 8. DB gate

| Gate | Status | Reason |
|---|---|---|
| Scope | BLOCKED | proposed/awaiting approval |
| Change inventory | PASS | existing JSON receipt storage；0 schema/seed/backfill/destructive |
| Static/Descriptor/Plan/Engine/Developer | NOT_RUN | no DB change authorized |

Conclusion：`DB_CHANGE_NOT_READY`。Apply mutation與歷史receipt backfill均不在本matrix。

