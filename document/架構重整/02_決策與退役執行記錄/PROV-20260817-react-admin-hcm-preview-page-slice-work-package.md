---
doc_type: work-package
declared_status: superseded
identity: PROV-20260817-react-admin-hcm-preview-page-slice
date: 2026-08-17
owner: Case Import / React Page-Slice Integration Owner
domain: Case Import
subsystem: HCM Current Workbook Preview / React Presentation
initiative: react-admin-migration
authority: PROV-20260817-react-admin-page-slice-migration-execution-decision
predecessor: PROV-20260816-react-admin-phase4a-hcm-current-preview
approval_required: 核准此 exact React HCM Preview Page-Slice Work Package
ui_execution_mode: real-browser-required
completion_ceiling: query-real-data-validated-preview-only
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-hcm-preview-page-slice/
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: shared-working-tree; integration-owner-must-fresh-read-before-execution
base_drift_rule: page, client, adapter, route, schema, auth or transport drift requires re-freeze; no silent reuse of old receipts
db_change: false
successor: PROV-20260817-react-admin-hcm-import-result-review-page-slice-work-package
---

# React HCM Current Preview 逐頁精簡遷移工作包

> 2026-08-17人工裁決：不要求合成／真xlsx browser Preview。DataImport頁改為顯示本次新增訂單與問題清單，
> 供人員檢查；本包標`superseded`，既有Preview code/tests可保留但不再作遷移／cutover gate。

> Activation：使用者已明確回覆「核准此 exact React HCM Preview Page-Slice Work Package」。本包等待
> 已取得互斥執行槽，現進入`in-progress`。

## 0. Exact purpose and delivery ceiling

本包依已採用的「逐頁精簡遷移模式」建立，只有一個使用者可見目標：在既有 React
`DataImportPage` 的第一張「HCM 案件匯入」卡中，完成真檔選擇 → immutable bytes snapshot →
零寫入 Preview → typed aggregate DOM 顯示，並以真實 FastAPI + Vite + TOTP 瀏覽器證據閉合本頁
query slice。

本包不重新設計 UI，不把 HCM Import 當成整個 domain 完成，也不把既有 Phase 4A-P 技術實作證據
重算成新的 production 變更。前一包已留下 client/schema/adapter/page/test 的實作基線；本包的
首要工作是對目前 dirty working tree 重新讀取，確認該基線仍符合本包，然後只補 page-level
Network↔DOM/browser evidence。若 fresh audit 發現確實 drift，必須先回報 `SOURCE_DRIFT`，不得
直接擴張 write set；只有下列明確的既有 page/client/adapter/test 路徑可作最小修補，並需在 receipt
逐檔說明。

最高完成狀態固定為：

```text
query-real-data-validated-preview-only
```

這不代表 HCM workbook 已匯入、案件已建立、warning 已處置、receipt 已保存、Apply 已安全、entry
已 cutover 或 Streamlit 已退役。

## 1. 人工批准與執行前 fresh-read

### 1.1 Required approval

執行本包前必須取得下列精確文字批准：

```text
核准此 exact React HCM Preview Page-Slice Work Package
```

未取得 exact approval 前，本文件只能是 `proposed`；任何 browser 啟動、API 呼叫、production
修改或 status 升級均不授權。

### 1.2 Fresh-read sources

Integration Owner 開工時必須重新讀取下列來源；舊 receipt 只作定位，不作現況證據：

- `document/架構重整/00_開發者與Agent導覽.md`
- `document/架構重整/01_規格基線/00_Global_共同契約.md`
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-page-slice-migration-execution-decision.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase4a-hcm-current-preview-specification.md`
- `ui_react/src/pages/DataImportPage.tsx` 與 `DataImportPage.css`
- `ui_react/src/api/case_import/hcm_workbook_schemas.ts`
- `ui_react/src/api/case_import/hcm_workbook_client.ts`
- `ui_react/src/api/case_import/hcm_workbook_errors.ts`
- `ui_react/src/adapters/case_import/hcm_workbook_adapter.ts`
- 對應 React focused tests／fixtures
- `api/routes/hcm_import.py`、`api/schemas/hcm_import.py`、
  `subsystems/case_import/hcm_workbook_import.py` 與 HCM router/service tests

Fresh-read 必須記錄實際 HEAD、dirty paths、source line／symbol、route response model、request
budget、stable IDs 與本包 matrix 的 digest 或生成時間。若現況與本包不一致，以 live-drift
記錄，不把舊完成報告當成修正授權。

## 2. Business scenario and allowed contract

操作者已完成帳密 Challenge → 六位 TOTP 驗證，React 使用既有 memory-only bearer session。操作者
在 `#data-import` 開啟 HCM Current Preview，選擇一份 `.xlsx`，按下明確的 Preview 按鈕；瀏覽器送出
唯一 allowlisted multipart request，後端只解析並回傳 aggregate preview，React 將 server-owned
digest、fingerprint 與 counts 顯示在原有 Drawer。

### 2.1 唯一 allowlisted HTTP action

```text
POST /api/v1/case-import/hcm/workbooks/preview
```

Request contract：

- body 是 `multipart/form-data`，唯一檔案欄位為 `workbook`；不得手動設定 boundary。
- 只有使用者明確按下 `imports.hcm-current.preview` 才能送出；開 Drawer、選檔、render、tab
  或 reload 不得自動 POST。
- `.xlsx`、非空、最多 `20 * 1024 * 1024` bytes；client 先驗證並保存 immutable bytes snapshot。
- 每次送出即時讀取 memory bearer；不得 localStorage、sessionStorage、cookie、URL、fixture 或 log
  保存 token。
- timeout 30 秒；支援 `AbortSignal`。關閉 Drawer、選擇新檔或 generation 變更時取消／丟棄舊請求。
- 本包最多一個明確 Preview POST；不得自動 retry、poll、prefetch、StrictMode duplicate request 或
  同一按鈕多次 parallel request。

Success `BaseResponse[HcmWorkbookPreviewView]` 僅允許下列 typed fields：

| Field | Server authority／constraint | UI disposition |
|---|---|---|
| `source_content_digest` | `api.schemas.hcm_import.HcmWorkbookPreviewView`; lowercase 64-hex | 顯示 server digest；必須等於同一 snapshot SHA-256 |
| `source_row_count` | strict integer `>= 0` | 顯示 aggregate 總列數 |
| `ready_count` | strict integer `>= 0` | 顯示 server aggregate |
| `ready_with_warning_count` | strict integer `>= 0` | 顯示 server aggregate |
| `review_required_count` | strict integer `>= 0` | 顯示 server aggregate |
| `preview_fingerprint` | lowercase 64-hex | 顯示 lineage fingerprint；不得用於解鎖 Apply |

Envelope 的 `success`、`message`、`data`、`error` 必須遵守目前 response model 與前端 strict
decoder；unknown field、missing required、wrong primitive、null violation、invalid hex、negative
或 fractional count 一律 fail closed。UI 不渲染 raw payload、traceback、完整檔案 bytes、完整本機
路徑或客戶個資。

### 2.2 Preview is not a domain mutation

雖然 HTTP method 是 POST，這只是 multipart preview command 的 transport 形狀；本包驗收必須證明：

- 不建立案件 root、warning task、receipt、claim、idempotency record 或任何正式 business row。
- 不執行 Apply、ingest、historical overwrite、resubmission、row correction、warning disposition、
  owner repair 或外部 provider side effect。
- 不以 `HTTP 200`、aggregate counts、舊 Streamlit screenshot 或 UI 顯示成功宣稱 domain mutation PASS。
- 任何需要 transaction／outer UoW／archive／receipt／Apply 的工作都留在既有 Phase 4A-H／warning
  successor；本包不建立新的 Domain gap，亦不修改既有 gap 文件。

## 3. UI scope and stable identities

### 3.1 Wired HCM Current slots

| Stable identity | Expected behavior |
|---|---|
| `imports.page` | 保留資料匯入頁 shell 與六張卡 |
| `imports.hcm-current.open-preview` | 開啟 HCM Preview Drawer；不發 API |
| `imports.hcm-current.drawer` | 保留既有 Drawer；close／換檔可取消 pending preview |
| `imports.hcm-current.file` | 接受 `.xlsx`，建立 immutable snapshot；選檔本身不 POST |
| `imports.hcm-current.preview` | 明確觸發唯一 allowlisted Preview POST |
| `imports.hcm-current.preview-summary` | 僅顯示 server aggregate 與 lineage digest/fingerprint |
| `imports.hcm-current.row-detail-unavailable` | 原位顯示「後端未開放逐列 typed Preview」；不生成 row story |
| `imports.hcm-current.close` | 關閉 Drawer、abort pending request；零 mutation |
| `imports.hcm-current.open-apply` | 保留原位置，native disabled |
| `imports.hcm-current.apply` | Drawer footer 保留原位置，native disabled |

### 3.2 Other five cards

下列五張卡必須繼續 render 既有視覺位置，但 Preview／Apply 皆 native `disabled`，無 handler、無
fetch、無 alert／confirm／prompt，並在畫面以 `已退役` 或 `本波未開放／後端尚未提供 bounded
contract` 說明：

- `imports.hcm-historical.preview`／`imports.hcm-historical.apply`：HCM historical whole-row
  overwrite retired；不可重新啟用。
- `imports.client-beclass.preview`／`imports.client-beclass.apply`：獨立 bounded contract 未在本包。
- `imports.staff-historical.preview`／`imports.staff-historical.apply`：獨立 historical contract 未在本包。
- `imports.historic-orders.preview`／`imports.historic-orders.apply`：獨立 orders adoption contract 未在本包。
- `imports.bank-statements.preview`／`imports.bank-statements.apply`：Finance Import 專屬 work package 未在本包。

其他卡不因 HCM Preview 成功而解鎖；不共用 HCM client，不用 mock data 填補。

## 4. Current source inventory and conditional write boundary

### 4.1 Fresh source inventory already observed

目前 fresh-read 已觀察到下列實作存在並覆蓋本包主要行為：

- `DataImportPage.tsx` 使用 discriminated `HcmPreviewState`、generation guard、AbortController、HCM
  snapshot、typed adapter 與 five-card disabled controls。
- `hcm_workbook_client.ts` 僅暴露 Preview client，使用 `workbook` multipart、30 秒 timeout、memory
  token、server/local digest 比對；未暴露 Apply／ingest method。
- `hcm_workbook_schemas.ts` 使用 strict envelope/data 與 lowercase 64-hex／non-negative integer constraints。
- `hcm_workbook_adapter.ts` 只映射 aggregate 並檢查 row-outcome conservation；逐列資料明確 unavailable。
- focused tests 已涵蓋 client negative cases、adapter conservation、file→Preview→DOM、same-name
  different-bytes 清除舊 preview、disabled controls 與零 alert／confirm。
- `api/routes/hcm_import.py` 對 Preview 使用 `POST /workbooks/preview`、temporary file cleanup 與
  typed `HcmWorkbookPreviewView` response model；Apply／ingest／historical paths 不是本包 allowlist。

這些是現況觀察，不是本包完成證據；必須由 fresh audit、真瀏覽器 Network↔DOM 與可重現命令重新驗證。

### 4.2 Exact write set

因目前 production page/client/adapter/tests 已存在，預設執行 write set 為 **evidence-only**：

- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-hcm-preview-page-slice/`
  內的 fresh inventory、contract matrix、verification receipt、browser smoke receipt、open findings。

本包預設禁止修改 production 與 tests。若 fresh audit 發現本包直接 scope 內的 source drift，且確實
需要修補，只有下列既有 paths 可在 Integration Owner 明確記錄後修改：

- `ui_react/src/pages/DataImportPage.tsx`
- `ui_react/src/pages/DataImportPage.css`
- `ui_react/src/api/case_import/hcm_workbook_schemas.ts`
- `ui_react/src/api/case_import/hcm_workbook_errors.ts`
- `ui_react/src/api/case_import/hcm_workbook_client.ts`
- `ui_react/src/adapters/case_import/hcm_workbook_adapter.ts`
- `ui_react/src/tests/fixtures/hcm_workbook_contract_fixtures.ts`
- `ui_react/src/tests/hcm_workbook_client.test.ts`
- `ui_react/src/tests/hcm_workbook_adapter.test.ts`
- `ui_react/src/tests/data_import_hcm_preview_flow.test.tsx`
- `ui_react/src/tests/data_import_no_fake_mutation.test.tsx`

上述 conditional paths 不代表已授權修改；若涉及 shared transport、runtime decoder、Auth/session、App、
Drawer、package/lock、backend route/schema、Domain、repository、DB、Streamlit、entry registry 或
其他頁面，固定回報 `SCOPE_EXPANSION_REQUIRED`，停止 source modification，另立 successor／取得人工裁決。

### 4.3 Forbidden writes and operations

- 不修改 `README.md`、main migration plan、page-slice decision、shared dependency matrix、02/README 或
  任何既有 gap／receipt；本包只新增自身文件與 evidence draft，integration owner另行裁決 index。
- 不修改 `api/routes/hcm_import.py` 或 `api/schemas/hcm_import.py`；本包把它們當 read-only contract source。
- 不修改 `api/shared`、`ui_react/src/api/shared/*`、Auth/session、`App.tsx`、`MasterLayout`、`Drawer`、
  `package.json`、`package-lock.json`、Vite config、其他 React page、Streamlit、DB schema、seed、migration、
  fixture、production data 或 external provider。
- 不用 `union_db` 執行 mutation、seed、repair、migration、reset 或建立資料；若使用既有 DB，只能讓真瀏覽器
  發出本包 allowlisted Preview request並觀察結果，不直接查表以偽造 DOM 證據。
- 不建立 `lu_test_*` DB；本包不是 DB engine gate。

## 5. Anti-fake and request-budget gates

### 5.1 Network budget

| 操作 | 上限 | 必須觀察 |
|---|---:|---|
| 開啟 HCM Drawer | 0 request | 只改 local UI state |
| 選擇／重新選擇檔案 | 0 request | snapshot/hash；清除舊 preview |
| 明確 Preview click | 1 POST | 唯一 path、唯一 `workbook` multipart、current memory bearer |
| Preview loading 期間重複 click | 0 additional POST | button disabled；無 parallel duplicate |
| 關閉 Drawer／換檔 | 0 additional request | AbortSignal／generation discard |
| 其他五卡 Preview／Apply | 0 request | native disabled，無 handler |
| Apply footer/button | 0 request | native disabled，無 fake success |

整個 browser case 的非本包 request（例如 login challenge、TOTP verify、health）必須在 evidence 中
分開列出；不得把它們算成 HCM Preview request，也不得把其他頁的 request 歸入本包。

### 5.2 Anti-fake checklist

- 不得 import `mockData`、硬編 counts、案例號、姓名、warning、row outcome、日期或 fingerprint。
- 不得從 aggregate counts 推導逐列結果、案件建立、warning story、eligibility 或 Apply readiness。
- 不得使用 `alert()`、`confirm()`、`prompt()` 或 success toast 冒充 Apply。
- 不得用 Happy DOM／unit fixture 單獨宣稱 browser real-data completion；fixture 只能證明 deterministic
  component behavior。
- 必須以兩份同名、bytes 不同的 `.xlsx` 在 browser／或現有 focused flow 證明 snapshot lineage 變化；
  不得沿用前一個 preview。
- 不得 render token、raw payload、完整 local path、file bytes 或個資；digest/fingerprint 只顯示必要的
  64-hex lineage。
- `source_content_digest` 與 local snapshot SHA-256 不一致時必須 fail closed、清除 preview，不可顯示 stale aggregate。
- 任何 POST 不是 Preview allowlist 時，驗收結論固定 `BLOCKED_SCOPE`。

## 6. Real TOTP browser acceptance

Exact approval 後，Integration Owner 啟動既有 FastAPI + Vite，不建立新 DB；由人工使用真實帳號密碼與
六位 TOTP 登入，不能使用 dev token、mock response 或直接 DB query。驗收步驟：

1. 開啟 `http://127.0.0.1:5173/#data-import`，記錄登入以外的 HCM request 起點。
2. 確認六張卡都在 DOM；只有 `imports.hcm-current.open-preview` 可啟用，其他五卡 Preview／Apply 與
   HCM Apply 均 native disabled。
3. 開啟 HCM Preview Drawer，確認開啟沒有 POST。
4. 選擇第一份去敏 `.xlsx`，確認 file input 只建立 snapshot，沒有 POST；確認 Preview button 可用。
5. 明確點擊 Preview，Network 只能看到一個 `POST /api/v1/case-import/hcm/workbooks/preview`，status、
   multipart key、Authorization 與 response 摘要去敏記錄；不得把 token、raw payload 或個資寫入 receipt。
6. 將 response 的六個 typed fields 與 DOM summary 逐欄比對；確認 row detail slot 顯示 unavailable，
   Apply 仍 disabled。Aggregate 200 不等於建立案件。
7. 關閉 Drawer、重新選擇同名但 bytes 不同的 `.xlsx`，確認舊 summary 消失、舊 request 不會覆蓋新 snapshot；
   若未重新明確點擊 Preview，不得看到新的 aggregate。
8. 點擊所有 disabled Preview／Apply controls，確認沒有非 allowlisted network、alert、confirm、prompt 或
   假成功；Anomalies／Import Warning mutation 不在本包。
9. 重新整理／session 過期時依 Phase 2C memory-only policy 驗證：沒有 token 不發 HCM request，呈現 auth boundary，
   不把 auth failure 當成 empty preview。

Browser evidence 欠缺時，狀態只能是 `blocked`／`BLOCKED_REAL_BROWSER_EVIDENCE`；不能以舊的 Phase 4A-P
receipt、HTTP 200、unit tests 或 Streamlit rendering 替代。

## 7. Verification commands and evidence outputs

本包不要求重新建立 DB。取得 exact approval 後，由 Integration Owner 依現況執行：

```powershell
Set-Location D:\project\Labor_union\ui_react
npm test -- src/tests/hcm_workbook_client.test.ts src/tests/hcm_workbook_adapter.test.ts src/tests/data_import_hcm_preview_flow.test.tsx src/tests/data_import_no_fake_mutation.test.tsx
npm run build
npm run lint
```

```powershell
Set-Location D:\project\Labor_union
.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp/phase4a-hcm-page-slice -q tests/test_hcm_import_router.py tests/test_hcm_workbook_import.py
git diff --check
```

若既有 source/tests 未修改，以上只產生 verification receipt，不產生 code diff；若 command 會接觸正式
資料或改 DB，立即停止並記錄 `UNAUTHORIZED_SIDE_EFFECT`。

Evidence directory 必須只新增下列 page-slice artifacts：

- `hcm-preview-page-slice-evidence-matrix.md`（本包配套 draft，非 freeze receipt）
- `candidate-change-inventory.md`（fresh file inventory／0 production write default）
- `verification-receipt.md`（只記錄實際執行 output，不可複製舊數字）
- `browser-smoke-receipt.md`（Network↔DOM、真 TOTP；缺證據標 blocked）
- `open-findings.md`（source drift、auth/runtime 或未開放 slot；不得把缺口改寫成 PASS）

## 8. Gate table and status rules

| Gate | PASS condition | 未滿足時 |
|---|---|---|
| G0 Scope／fresh baseline | exact approval、fresh read、write set／forbidden paths閉合 | `BLOCKED_SCOPE` |
| G1 Contract | route/schema/client逐欄 matrix、strict envelope、multipart/request budget一致 | `BLOCKED_CONTRACT` |
| G2 Client／adapter | focused strict negative tests、digest lineage、row conservation、abort／timeout | `BLOCKED_CLIENT` |
| G3 Page／UI | six cards保留、HCM slots wired、five cards／Apply native disabled | `BLOCKED_PRESENTATION` |
| G4 Anti-fake／network | allowlisted POST only、0 fake mutation、0 unexpected request | `BLOCKED_SCOPE` |
| G5 Static | build、lint、UTF-8、diff、secret／PII、write-set audit | `NOT_RUN`／`BLOCKED` |
| G6 Real browser | 真 TOTP、existing DB only、Network↔DOM aggregate、reload／new-file evidence | `BLOCKED_REAL_BROWSER_EVIDENCE` |

只有 G0–G6 均有 current evidence 才能標記 `query-real-data-validated-preview-only`。任何 gate 缺證據
都不能標 `completed`，更不能標 mutation-ready、entry-readiness、cutover 或 retired。

## 9. DB gate (zero DB change)

| DB gate | Status | Evidence／reason |
|---|---|---|
| Scope gate | `PASS` after exact approval / otherwise `BLOCKED` | 本包不含 schema、seed、backfill、migration 或 production data |
| Change inventory | `PASS` | default write set 是 evidence-only；conditional source edits限既有 page/client/test paths |
| Static release gate | `NOT_RUN` | 無 schema／release artifact |
| Descriptor gate | `NOT_RUN` | 無 owned-object 變更 |
| Read-only plan gate | `NOT_RUN` | 不建立或 reset DB；既有 DB僅供 browser GET／Preview觀察 |
| Engine verification gate | `NOT_RUN` | 本包不執行 mutation；POST Preview不等於 DB engine evidence |
| Developer acceptance gate | `NOT_RUN` | 不套用 migration、不操作 `union_db` |

依專案規範，必要 DB gate 為 `NOT_RUN` 時總結固定為 `DB_CHANGE_NOT_READY`。這是「本包沒有 DB change」
的治理結果，不是 HCM Preview query page 的額外實作 blocker。

## 10. Successor and rollback routing

- HCM Apply、receipt observation、warning disposition、row correction、archive、outer UoW、ingest、historical
  overwrite、resubmission 與 mutation browser evidence 沿用既有 Phase 4A-H／Phase 3D successor；本包不解鎖。
- 其他五張 Import cards各自等待其 bounded page／mutation package，不因 HCM Preview success 連帶完成。
- Query browser failure 只回到既有 Streamlit Data Import entry 供操作；不回滾任何 DB/domain data，亦不宣稱
  Streamlit 已退役。
- 不新增欄位 gap；若 fresh read 發現新的 owner／transaction／provider／DB／public contract問題，只在
  `open-findings.md` 指向既有 canonical owner或回報需另立 successor，不在本包內複製 gap 文件。
