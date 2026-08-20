---
doc_type: work-package
declared_status: blocked
identity: PROV-20260817-react-admin-reports-query-page-slice
date: 2026-08-17
owner: Reports React Page Integration Owner
domain: Government Subsidy / Reporting
subsystem: reports-query-page-slice
authority: PROV-20260817-react-admin-page-slice-migration-execution-decision
activation_blocker: none for exact-approved quarterly/annual bounded query; weekly fields remain unavailable
approval_required: 核准此 exact React Reports Query Page-Slice Work Package
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-reports-query-page-slice/
completion_ceiling: query-real-data-validated
ui_execution_mode: browser-required
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: ReportsPage、finance_reports route/schema或report authority drift時必須重新凍結
blocker: BLOCKED_REAL_BROWSER_EVIDENCE
bounded_authority: exact Reports approval authorizes implemented quarterly/annual redacted query only
---

# React Reports：逐頁精簡 query page-slice 工作包

> Activation：使用者已明確回覆「核准此 exact React Reports Query Page-Slice Work Package」。季度／年度
> bounded redacted query已完成local/integration驗證；weekly仍unavailable，目前只等待真Chrome GET evidence。

## 1. Scope 與 activation

本包只把 `ReportsPage` 的 Government Subsidy 季度／年度核銷報表改為真實唯讀 query；不建立 generic
weekly report、XLSX export、DB、mutation、entry cutover 或 Streamlit retirement。

舊 `PROV-20260817-government-subsidy-reporting-authority-decision-work-package.md` 仍保留較廣的reporting
治理問題；本次exact Reports approval只收斂已實作的季度／年度redacted query。Weekly與export欄位仍未授權，
維持unavailable；舊文件不再阻擋本bounded page-slice。

- 本 page package 可以核准並完成 client/page骨架、unavailable states與focused contract準備。
- `api/routes/finance_reports.py`、strict public view與 subsidy DOM接線只有在 reporting authority decision完成後才可啟動。
- authority仍有 `DECISION_REQUIRED` 時，季度／年度slot保持 `blocked-public-contract`／unavailable；不另建新gap，也不以live SQL、
  現有ReportsPage、fixture或HTTP 200補權威。

`api/routes/finance_reports.py` 同時是 Accounts Payable query page-slice hot spot。writer順序固定：Finance AP route candidate
freeze → Integration Owner fresh-read collision inventory → Reports Subsidy唯一route writer。兩包不得平行修改該檔。

## 2. Page surface

保留既有 Reports 三 sheet 視覺階層：

1. `reports.tab.weekly-summary`：週報案件受理總表，後端typed authority未提供，原位 unavailable。
2. `reports.tab.subsidy`：唯一query-enabled sheet；內含 `quarterly`／`annual` view switch。
3. `reports.tab.weekly-active`：每週服務中／工時說明，後端typed authority未提供，原位 unavailable。

KPI cards只有在季度／年度 strict view明確提供對應aggregate時才顯示；不得沿用101案、68案、NT$1,010,800、328小時等
local literals或自行加總。

所有 export controls 原生 disabled：

- `reports.export.full-workbook`
- `reports.export.quarterly-xlsx`
- `reports.export.annual-xlsx`
- `reports.export.weekly-summary`
- `reports.export.weekly-active`

disabled controls不得有 `alert/confirm/prompt`、download URL、blob、non-GET或假成功。

## 3. Backend public query contract（authority完成後才施工）

### 3.1 Routes

- `GET /api/v1/finance-reports/subsidy-reconciliation/quarterly?application_year=<year>&quarter=<1..4>`
- `GET /api/v1/finance-reports/subsidy-reconciliation/annual?application_year=<year>`

兩條route必須：

- 使用 enabled-principal `require_admin`。
- 改為 `BaseResponse[GovernmentSubsidyReportPreviewView]` 或季度／年度各自的strict Pydantic view；禁止
  `BaseResponse[dict[str, Any]]`。
- 明確回傳period、generated_at、source/version lineage、general/subsidized aggregates與已核准DISPLAY rows。
- full identity card、address、bank／document secrets與EXPORT_ONLY欄位不得進JSON、log、error或receipt。
- masked employer／staff欄位必須由server產生；React不得遮罩完整PII後再顯示。
- Query 0 commit／0 outbox／0 job／0 workbook generation／0 provider；error使用Global typed envelope與correlation。

`/quarterly/export`、`/annual/export` 不屬本包，React不得呼叫。`xlsx_bytes`永遠不進success JSON。

### 3.2 Exact backend write set

- `api/routes/finance_reports.py`：只改季度／年度 preview GET auth、typed materialization與error boundary。
- `api/schemas/government_subsidy_report.py`（new）：authority凍結後的strict redacted view。
- `tests/test_government_subsidy_report_query_contract.py`（new）。
- `tests/test_subsidy_reconciliation_register.py`：只加query read-only／aggregate conservation regression，若authority要求。

`subsystems/government_subsidy/reconciliation_register_query.py`、repository、Domain與XLSX builder是read-only evidence；若必須修改其
公式/root facts才能完成，固定 `SCOPE_EXPANSION_REQUIRED` 並維持activation blocked，不得藏進page package。

## 4. React exact write set

- `ui_react/src/api/reports/subsidy_report_query_schemas.ts`
- `ui_react/src/api/reports/subsidy_report_query_errors.ts`
- `ui_react/src/api/reports/subsidy_report_query_client.ts`
- `ui_react/src/adapters/reports/subsidy_report_query_adapter.ts`
- `ui_react/src/pages/ReportsPage.tsx`
- `ui_react/src/pages/ReportsPage.css`
- `ui_react/src/tests/fixtures/reports/subsidy_report_query_contract_fixtures.ts`
- client／adapter／page／request-budget／no-fake focused tests。
- 本包 evidence directory。

不得修改 FinancePage、shared transport/Auth、package/lockfile、其他pages、README、main plan、shared matrix或既有receipt。
`ReportsPage.tsx/.css`在本包執行期間只有一位writer。

## 5. Query behavior／request budget

| Action | Budget | Rule |
|---|---:|---|
| open subsidy tab | 1 active quarterly或annual GET | 不預抓另一view |
| year／quarter change | 1 GET | abort舊request並丟棄stale response |
| quarterly↔annual switch | 1 GET | 只載入active view |
| retry | 每次人工點擊1 GET | 0 polling、0 auto retry |
| weekly tabs | 0 GET | explicit unavailable |
| export buttons | 0 GET | native disabled |

無memory token零fetch；success/nested DTO strict decode，missing/wrong/null/extra/duplicate identity/aggregate mismatch fail closed。
loading、empty、401/403、422、503、timeout/network、abort/stale與reload均有獨立DOM狀態。empty不得用mock資料填補。

## 6. Adapter／presentation invariants

- period、eligibility、hours、days、unit price、amount與aggregate只顯示server權威值。
- 不把中華民國年、本地日期、rate或hours公式轉成新的業務值；只允許已核准的display formatting。
- general/subsidized totals需與server aggregate守恆；React不重新計算並覆蓋server數字。
- PII必須已server masked；client接到疑似完整identity card/address欄位時strict decoder fail closed。
- weekly summary與weekly active兩個slot只顯示「後端尚未提供typed authority」，不render原本local arrays。

## 7. Gates

1. G0：exact Reports approval、季度／年度bounded authority與AP route writer已freeze且collision inventory完成。
2. G1：authority matrix無未決欄位；final Pydantic/Zod/redaction/aggregate/error matrix凍結。
3. G2：quarterly/annual require_admin、strict view、Global error、0 raw dict／PII／xlsx bytes route tests。
4. G3：client strict negative、fresh token、abort/stale、request budget tests。
5. G4：adapter零公式／金額／狀態推導；weekly slots unavailable；export native disabled。
6. G5：0 mock/local business arrays/alert/confirm/prompt/non-GET；build/lint/full focused React。
7. G6：UTF-8/header/diff/secret/PII/write-set audit。
8. G7：真FastAPI + Vite + TOTP browser，使用既有DB只做季度／年度GET Network→DOM；不得建立或修改DB。

完成上限為 `query-real-data-validated`。不得宣稱weekly report、XLSX、Finance entry cutover或Streamlit retirement完成。

## 8. Evidence

執行時產出final contract matrix、freeze receipt、candidate inventory、verification receipt、browser receipt與open findings。
本次只建立獨立matrix draft，不是implementation evidence。

## 9. DB gate

| Gate | Status | Reason |
|---|---|---|
| Scope gate | PASS | exact Reports核准已取得；限定既有公式的strict redacted query、0 DB |
| Change inventory | PASS | 0 schema/seed/backfill/destructive；query-only |
| Static release gate | NOT_RUN | 無schema release |
| Descriptor gate | NOT_RUN | 無owned-object變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不建立DB；existing DB只GET browser |
| Developer acceptance gate | NOT_RUN | 不操作既有DB |

結論：`DB_CHANGE_NOT_READY`。
