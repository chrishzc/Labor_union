---
doc_type: work-package
declared_status: blocked
identity: PROV-20260817-react-admin-finance-query-page-slice
date: 2026-08-17
owner: Finance React Page Integration Owner
domain: Client Finance / Staff Payables / Finance Reporting / Finance Import
subsystem: finance-query-page-slice
authority: PROV-20260817-react-admin-page-slice-migration-execution-decision
approval_required: 核准此 exact React Finance Query Page-Slice Work Package
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-finance-query-page-slice/
completion_ceiling: query-real-data-validated
ui_execution_mode: browser-required
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: FinancePage、四組query route/schema/client或shared hot spot drift時必須fresh-read並重新凍結
blocker: BLOCKED_REAL_BROWSER_EVIDENCE
---

# React Finance：逐頁精簡 query page-slice 工作包

> Activation：使用者已明確回覆「核准此 exact React Finance Query Page-Slice Work Package」。

## 1. Scope

本包只把 React `FinancePage` 從本地假資料改為四組真實唯讀 query，依下列順序串行施工；同一時間只能有一位
`FinancePage.tsx/.css` writer：

```text
FQ1 Client Receipt Query
→ FQ2 Staff Payables Query
→ FQ3 Accounts Payable masked Query
→ FQ4 Finance Import Query
```

每個 tab 完成自己的 client／adapter／focused tests 後才修改下一個 tab；不得平行競寫 page、CSS、shared fixture 或
evidence。某個次要欄位缺 contract 時原位顯示 `unavailable`，不另建欄位級 gap，也不阻擋其他 typed GET tab。

本包不是 Finance mutation、XLSX export、DB、entry cutover 或 Streamlit retirement 授權。

## 2. Query routes 與最小 backend hardening

### FQ1 Client Receipt

- `GET /api/v1/orders/{case_no}/client-finance/receipt-reconciliation`
- success：strict `ClientReceiptQueryView`，包含 case/account version、bank facts、obligations。
- 只把該 GET auth 從舊 capability 差異收斂至 enabled-principal `require_admin`；同檔 Preview／Apply 不在本包。
- case selector 重用既有 Orders summary client；不得新增第二個 Orders client。

### FQ2 Staff Payables

- `GET /api/v1/staff-payables/{staff_id}`
- success：strict `StaffPayablesQueryView`，包含 staff/version、obligations、events。
- 只把該 GET auth 收斂至 enabled-principal `require_admin`；payout/difference/return/reversal Preview／Apply 不在本包。
- staff selector 重用已完成的 `staff_directory` client；不得競寫 Staff files。

### FQ3 Accounts Payable

- `GET /api/v1/finance-reports/accounts-payable?target_month=YYYY-MM&view=summary`
- 現況雖為 typed `AccountsPayablePreviewView`，但沒有 admin guard，且公開完整 `bank_account` 與
  `recipient_identity_card`；目前固定 `blocked-public-contract`。
- 本包只做最小 public query hardening：加入 `require_admin`，preview view 改為 server-masked
  `bank_account_masked`、`recipient_identity_card_masked`，保留日期、付款類型、受款人、bank code、amount、
  obligation/case identities。完整值不得進 JSON／log／receipt。
- `/accounts-payable/export`、archive download、legacy `/accounts-payable-summary` 均不接；XLSX 按鈕原生 disabled。
- 若 masked view 不能只在 route/view boundary完成，FQ3 保持 `blocked-public-contract` 並在同頁顯示 unavailable；
  不得擴張至 workflow、DB 或另建欄位 gap。

### FQ4 Finance Import

- `GET /api/v1/finance-import/batches`
- lazy GET：`/batches/{batch_identity}/manifest`、`/review-rows`、`/reprocess-runs`。
- 只把上述 GET auth 收斂至 enabled-principal `require_admin`；workbook ingest、Preview、Apply、correction、reprocess
  mutation全部排除。
- status/classification/disposition/available-actions 若 public schema仍為 generic string，UI只顯示 server raw label，
  不建立本地狀態機或把字串映射成成功／可Apply。

四組 GET 均須使用 Global typed error envelope、fresh memory bearer、X-Correlation-ID、strict success/nested decode，
Query 0 commit／0 outbox／0 job／0 provider。

## 3. Exact write set

### 3.1 Backend（只允許 query boundary）

- `api/routes/client_receipt_reconciliation.py`：只改 GET query auth/correlation。
- `api/routes/staff_payout.py`：只改 `GET /{staff_id}` auth/correlation。
- `api/routes/finance_reports.py`：只改 accounts-payable preview auth、masked materialization與typed error。
- `api/schemas/accounts_payable_export.py`：只建立 masked JSON preview view；不得改 XLSX internal row contract。
- `api/routes/finance_import.py`：只改四個 query GET 的 auth/correlation。
- `api/schemas/client_receipt_reconciliation.py`、`staff_payout.py`、`finance_import.py`：只有 final matrix證明
  required/nullable/extra 漂移時才允許最小 query view修正；不得碰 mutation DTO。
- focused route tests：Client Receipt query、Staff Payables query、AP masked query、Finance Import query。

不得修改 Domain、Subsystem、repository SQL、DB、shared error/Auth、XLSX workflow、durable job或 mutation tests。

### 3.2 React

- `ui_react/src/api/client_finance/client_receipt_query_{schemas,errors,client}.ts`
- `ui_react/src/api/staff_payables/staff_payables_query_{schemas,errors,client}.ts`
- `ui_react/src/api/accounts_payable/accounts_payable_query_{schemas,errors,client}.ts`
- `ui_react/src/api/finance_import/finance_import_query_{schemas,errors,client}.ts`
- `ui_react/src/adapters/finance/client_receipt_query_adapter.ts`
- `ui_react/src/adapters/finance/staff_payables_query_adapter.ts`
- `ui_react/src/adapters/finance/accounts_payable_query_adapter.ts`
- `ui_react/src/adapters/finance/finance_import_query_adapter.ts`
- `ui_react/src/pages/FinancePage.tsx`
- `ui_react/src/pages/FinancePage.css`
- 四組去敏 contract fixtures、client/adapter/page focused tests、request-budget與no-fake tests。
- 本包 evidence directory。

不得修改 Orders／Staff clients、shared transport/Auth、package/lockfile、其他 pages、README、main plan或shared matrix。

## 4. UI slots 與 stable IDs

四個 tab 固定為：

- `finance.tab.client-receipts`
- `finance.tab.staff-payables`
- `finance.tab.accounts-payable`
- `finance.tab.finance-import`

Query-enabled controls：case selector、staff selector、target month、batch cursor、lazy batch detail、retry。每個 tab 必須有
loading／empty／typed error／abort／stale／reload 與 loaded-scope 說明。

以下控制項保留原位置但必須 native disabled，且 0 handler／0 fake success：

- `finance.client-receipt.settle`
- `finance.staff-payable.mark-paid`
- `finance.refund.approve`
- `finance.subsidy.advance`
- `finance.accounts-payable.export-xlsx`
- `finance.staff-payable.adjustment`
- `finance.finance-import.upload|preview|apply|reprocess`

`settled`／`paid` 只能顯示 server明確回傳狀態；Client Receipt不得用 bank sum與obligation sum在前端推導結清，
Staff Payables不得用 `balance_ntd == 0` 自行產生 paid Badge。沒有 closed typed status時原狀顯示server string或
`unavailable`。退款／補助 mock tabs不得繼續 render假資料，其查詢資訊只可由AP masked rows呈現。

## 5. Request budget 與 state

| Tab | Initial | Selection／lazy detail | 禁止 |
|---|---:|---:|---|
| Client Receipt | 1 Orders selector GET + 1 selected case GET | case change 1 GET | 全案N+1、settlement POST |
| Staff Payables | 1 Staff selector GET + 1 selected staff GET | staff change 1 GET | 全staff N+1、paid POST |
| Accounts Payable | 1 selected month GET | month change 1 GET | export/archive GET、自動下載 |
| Finance Import | 1 batches GET（limit≤50） | selected batch最多 manifest 1 + review page 1 + reprocess page 1 | polling、upload／Preview／Apply |

Runtime只載入 active tab；不得預抓後續 tabs。selection／month／cursor／batch切換必須 AbortController + generation guard，
丟棄 stale response；無 memory token 零 fetch；timeout/network/503顯示 retryable typed error，不得轉成empty。

## 6. Anti-fake gates

1. G0：exact approval、fresh base/dirty baseline、FinancePage唯一writer與FQ1→FQ4串行順序。
2. G1：四組 GET final field/redaction/error matrix；AP masked view先通過route contract才可接DOM。
3. G2：strict decoder negative cases（missing/wrong/null/extra/enum-or-string drift/duplicate cursor/range mismatch）。
4. G3：adapter零金額、settled、paid、refund、subsidy、export、eligibility推導。
5. G4：query loading/empty/error/abort/stale/retry/deep-link與request budget tests。
6. G5：Finance production 0 mock/local business arrays/alert/confirm/prompt/non-GET；所有 mutation controls native disabled。
7. G6：focused backend/React、full React、build/lint、UTF-8/header/diff/secret/PII/write-set audit。
8. G7：真 FastAPI + Vite + TOTP browser，以既有 DB 只執行 GET Network→DOM；不得建立或修改 DB。

完成上限為 `query-real-data-validated`。不得宣稱settled、paid、XLSX、mutation、entry cutover或Streamlit retirement完成。

## 7. Evidence

執行時在指定目錄產出 final contract matrix、freeze receipt、candidate inventory、verification receipt、browser receipt與
open findings。本次只建立 `page-slice-evidence-matrix-draft.md`，不是 implementation evidence。

## 8. DB gate

| Gate | Status | Reason |
|---|---|---|
| Scope gate | PASS | exact核准已取得；query-only且0 DB變更 |
| Change inventory | PASS | 0 schema/seed/backfill/destructive；query-only |
| Static release gate | NOT_RUN | 無schema release |
| Descriptor gate | NOT_RUN | 無owned-object變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不建立DB；既有DB只GET browser |
| Developer acceptance gate | NOT_RUN | 不操作既有DB |

結論：`DB_CHANGE_NOT_READY`。
