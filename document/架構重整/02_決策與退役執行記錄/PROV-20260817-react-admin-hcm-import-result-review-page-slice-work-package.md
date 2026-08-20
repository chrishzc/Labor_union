---
doc_type: work-package
declared_status: blocked
identity: PROV-20260817-react-admin-hcm-import-result-review-page-slice
date: 2026-08-17
owner: Case Import / React Integration Owner
domain: Case Import / Anomalies
subsystem: hcm-import-result-review
initiative: react-admin-migration
authority: user-business-decision-2026-08-17-result-review-instead-of-preview-browser
supersedes: PROV-20260817-react-admin-hcm-preview-page-slice-work-package
approval_required: 核准此 exact React HCM Import Result Review Page-Slice Work Package
ui_execution_mode: browser-query-only-no-file-upload
completion_ceiling: import-result-query-validated
db_change: none
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-hcm-import-result-review-page-slice/
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
updated: 2026-08-17
blocker: BLOCKED_REAL_BROWSER_EVIDENCE
---

# React HCM Import Result Review Page-Slice 工作包

> Activation：使用者已明確回覆「核准此 exact React HCM Import Result Review Page-Slice Work Package」。

## 0. 最新人工裁決與取代關係

使用者最新裁決：Data Import 不需要合成或真 `.xlsx` 的 Preview browser驗收；頁面真正需要回答：

1. 本次 HCM 匯入新增了哪些訂單。
2. 哪些訂單／來源列／欄位有問題，讓人員檢查並導向既有 Import Warning 流程。

因此本包完整取代 `PROV-20260817-react-admin-hcm-preview-page-slice-work-package`。舊包已標
`superseded`；它的 file-select、immutable bytes、Preview button與真檔browser gate不再是DataImport頁
完成條件。舊證據保留歷史用途，不得解讀為目前產品目標。

本包不啟用 HCM Apply、不執行上傳、不變更 DB，也不把 Apply mutation驗收吸收到 query page。Apply
仍由自己的 transaction／archive／receipt／warning工作包管理；本包只強化其 canonical terminal
receipt shape，並讓DataImport頁查詢／顯示已完成的結果。

## 1. Fresh audit conclusion

### 1.1 EXISTING_GET

| Endpoint | 可直接提供 | 不能證明 |
|---|---|---|
| `GET /api/v1/import-warning-tracking/tasks` | masked subject、logical code、field path、issue codes、tracking status/version、顯示文案與navigation action | 沒有HCM batch／source digest filter；不能可靠判定屬於哪一次匯入 |
| `GET /api/v1/import-warning-tracking/tasks/{occurrence_identity}/referral` | 單一HCM問題的owner referral與目標command | 必須先知道occurrence identity；不是批次結果清單 |
| `GET /api/v1/orders/summaries` | 現行訂單摘要 | 沒有HCM source digest／batch membership；不能用建立時間或status猜「本次新增」 |

HCM route目前只有Preview／Apply／ingest／resubmission POST；沒有receipt／recent batch GET。

### 1.2 Existing durable facts

- `admin_command_receipts` 已保存 `command_family=hcm_workbook_ingest`、source digest、actor、terminal
  `result_snapshot`、`created_at`，可供新增query讀取，不需要新table。
- `case_import_events`／`case_import_receipts` 保存單一case import結果，但沒有HCM workbook digest或batch id，
  無法安全回推某次workbook所新增的case集合。
- `case_import_hcm_review_rows` 保存source digest、row number、masked case identity、issue codes與review identity。
- `import_warning_occurrences/current_tasks` 保存可導向的欄位級問題；現有public GET已typed且去敏。

### 1.3 Missing authority

目前 `HcmWorkbookReceiptView` 與 `admin_command_receipts.result_snapshot` 只有counts：

```text
source_row_count
inserted_count
inserted_with_warning_count
exact_replay_count
review_required_count
failed_count
replayed_workbook
```

它沒有 `case_no`、source row outcome、problem/review identity或warning occurrence identity。因此現況無法
準確回答「本次新增哪些訂單」。禁止以receipt時間窗、actor、order status、case import event順序或
Orders summary差集推導。

## 2. MINIMAL_SAME_PAGE_HARDENING

不新增DB object。最小方案是把future canonical HCM Apply terminal receipt／既有JSON result snapshot擴充為
row-level typed outcomes，再新增唯讀 recent-results GET。DataImport直接顯示該receipt；Warning tasks只負責
問題導向，不再要求瀏覽器上傳檔案。

### 2.1 Canonical row outcome

每一來源列固定一個terminal outcome：

```text
source_row: positive integer
case_no: string | null
outcome: inserted | inserted_with_warning | exact_replay | review_required | failed
problem_identity: string | null
problem_fields: string[]
issue_codes: string[]
referral_occurrence_identities: string[]
```

規則：

- `inserted`代表本次建立新的正式訂單；UI「本次新增」只列此outcome。
- `inserted_with_warning`代表訂單已建立但有問題；同時出現在新增訂單與問題清單。
- `exact_replay`不得列為本次新增，另以replay標示。
- `review_required`／`failed`不得列為新增；case number可能為null。
- problem fields與issue codes只含欄位名稱／stable code，不含原始值、姓名、電話、地址或完整來源列。
- referral identities由canonical HCM review root／warning occurrence builder產生；若outbox尚未投影，UI顯示
  「問題已保存，導向建立中」，不得假裝task不存在。
- row outcome總數必須等於`source_row_count`，各counts必須與outcome分類守恆。

### 2.2 Apply contract boundary

本包只擴充Apply成功receipt與持久化snapshot，不改Apply按鈕、outer UoW、archive、idempotency、transaction
或warning outbox語意。Apply是否可執行仍由其獨立工作包決定；本包測試可使用service fixture，不操作
`union_db`。

舊receipt沒有row outcomes時，recent-results GET必須回：

```text
row_outcomes_available: false
row_outcomes: []
legacy_summary_only: true
```

不得重算／backfill舊批次，也不得用空list冒充「本次沒有新增訂單」。

### 2.3 Conditional recent-results GET

利用現有`admin_command_receipts`新增：

```text
GET /api/v1/case-import/hcm/workbooks/results?limit=1..50&before_receipt_id=<optional>
```

Response為strict `BaseResponse[HcmWorkbookResultPageView]`，依receipt id倒序，僅讀
`command_family=hcm_workbook_ingest`。每一項包含：receipt id、source digest、completed at、aggregate counts、
row-outcomes availability與typed row outcomes。不得回idempotency key、raw result snapshot、來源檔名、token、
原始列或PII。

若fresh implementation發現existing receipt table在支援版本缺必要`created_at/id/result_snapshot`，停止並回報
`SCOPE_EXPANSION_REQUIRED`；不得新增table。現行schema audit顯示這些欄位已存在，因此預期0 DB change。

## 3. DataImport page behavior

HCM卡改為「最近匯入結果與問題檢查」，不顯示file input、Preview或Apply control。本包頁面啟動只做一個
recent-results GET；每次明確刷新最多一個GET。

每個receipt顯示：

- 完成時間、去敏source digest短碼、aggregate counts與legacy availability。
- 「本次新增訂單」：只列`inserted`與`inserted_with_warning`的case number與outcome。
- 「需要檢查」：列source row、masked／nullable case identity、problem fields、issue codes、problem identity。
- referral occurrence可在既有Import Warning task查詢結果中找到時，顯示安全navigation；找不到時顯示
  projection pending，不做mutation。
- exact replay獨立列示，不算新增。
- legacy summary-only明確顯示「舊receipt未保存逐列membership」，不可顯示空成功。

其他五張Import卡維持各自現況，本包不解鎖、不重構、不共用HCM result client。

## 4. Request budget and stable IDs

| Operation | Budget |
|---|---:|
| Initial DataImport result load | 1 HCM recent-results GET |
| Explicit refresh | 1 GET per click |
| Expand receipt／switch result tabs | 0 request |
| Load matching warning tasks | at most 1 existing warning-tasks GET per explicit receipt expansion; no polling |
| Navigate referral | local hash/navigation only; 0 mutation |
| Upload／Preview／Apply | 0 request; controls absent fromthis page-slice |

Stable identities：

- `imports.hcm-results.open`
- `imports.hcm-results.refresh`
- `imports.hcm-results.receipt.<id>`
- `imports.hcm-results.new-orders`
- `imports.hcm-results.new-order.<encoded-case-no>`
- `imports.hcm-results.problems`
- `imports.hcm-results.problem.<problem-identity>`
- `imports.hcm-results.problem.referral.<occurrence-identity>`
- `imports.hcm-results.replays`
- `imports.hcm-results.legacy-unavailable`
- `imports.hcm-results.empty`
- `imports.hcm-results.error`

## 5. Exact write set

### Backend contract／query

- `subsystems/case_import/hcm_workbook_import.py`
- `scripts/imports/import_client_hcm.py`
- `api/schemas/hcm_import.py`
- `api/routes/hcm_import.py`
- `api/dependencies/hcm_import.py`（只在GET query dependency需要時）
- `infrastructure/mysql/hcm_workbook_import_repository.py`（legacy snapshot decode／recent query helper）
- `subsystems/case_import/hcm_import_result_query.py`（new，如需要）
- `infrastructure/mysql/hcm_import_result_query_repository.py`（new，如需要）
- `tests/test_hcm_workbook_import.py`
- `tests/test_hcm_import_router.py`
- `tests/test_hcm_import_result_query.py`（new）

### React

- `ui_react/src/api/case_import/hcm_import_result_schemas.ts`（new）
- `ui_react/src/api/case_import/hcm_import_result_errors.ts`（new）
- `ui_react/src/api/case_import/hcm_import_result_client.ts`（new）
- `ui_react/src/adapters/case_import/hcm_import_result_adapter.ts`（new）
- `ui_react/src/pages/DataImportPage.tsx`
- `ui_react/src/pages/DataImportPage.css`
- `ui_react/src/tests/hcm_import_result_client.test.ts`（new）
- `ui_react/src/tests/hcm_import_result_adapter.test.ts`（new）
- `ui_react/src/tests/data_import_hcm_result_page.test.tsx`（new）
- `ui_react/src/tests/data_import_hcm_result_request_budget.test.tsx`（new）

### Read-only reuse

- `GET /api/v1/import-warning-tracking/tasks`與referral schema／React client。
- Orders summaries只作case navigation target，不作batch membership authority。

### Forbidden

- 不改DB schema／migration／seed／backfill或舊receipts。
- 不啟用Apply、upload、Preview、resubmission、warning transition或repair mutation。
- 不修改shared transport/Auth/App/package/lock、OrdersPage、Finance、LINE或其他Import cards。
- 不用raw dict、time-window、order status或前後summary差集推導batch membership。

## 6. Verification gates

| Gate | PASS condition |
|---|---|
| G0 Scope | exact approval；舊Preview包superseded；0 DB／0 upload／0 Apply UI |
| G1 Authority | everynew-order card追溯到new receipt row outcome；legacy rows顯示unavailable |
| G2 Receipt | row outcomes/counts守恆；PII absent；replay/idempotency相容 |
| G3 GET | strict typed recent page、cursor/limit、auth/error、legacy decode、0 commit |
| G4 UI | new orders／problems／replays分區；warning referral safe；loading/empty/error/stale/abort |
| G5 Request safety | initial/refresh/warning-task budget；0 upload／Preview／Apply／non-GET |
| G6 Static | focused backend/React、full React、build/lint、UTF-8/header/diff/secret/write-set |
| G7 Browser query | 真TOTP後只GET既有receipt；無檔案選擇或upload；Network↔DOM result comparison |

Browser沒有recent receipt時可驗empty state，但不能宣稱row-level result已runtime驗證；component／route fixture仍需
證明兩筆不同receipt不混批。

## 7. Evidence and completion

本包配套matrix：
`document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-hcm-import-result-review-page-slice/hcm-import-result-review-evidence-matrix.md`。

完成上限為`import-result-query-validated`。不代表HCM Apply mutation、warning disposition、entry cutover或
Streamlit retirement完成。

## 8. DB gate

| Gate | Status | Reason |
|---|---|---|
| Scope gate | PASS | exact核准已取得；方案固定重用existing JSON receipt table，0 upload／0 Apply／0 DB變更 |
| Change inventory | PASS | schema-only/system-seed/business-row-backfill/destructive均為0 |
| Static release gate | NOT_RUN | 無schema/release artifact |
| Descriptor gate | NOT_RUN | 無DB object變更 |
| Read-only plan gate | NOT_RUN | 不執行migration plan |
| Engine verification gate | NOT_RUN | query/receipt contract不以現有DB mutation驗收 |
| Developer acceptance gate | NOT_RUN | 不修改`union_db` |

結論：`DB_CHANGE_NOT_READY`；本包預期不需要DB change，也不授權Apply。
