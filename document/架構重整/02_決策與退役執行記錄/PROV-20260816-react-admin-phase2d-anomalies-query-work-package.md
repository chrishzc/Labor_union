---
doc_type: work-package
declared_status: superseded
identity: PROV-20260816-react-admin-phase2d-anomalies-query
date: 2026-08-16
owner: Integration Owner
domain: Anomalies
subsystem: Alert Query / Import Warning Tracking / React Presentation
specification: PROV-20260816-react-admin-phase2d-anomalies-query-specification
approval_required: human-must-reply-核准此-exact-Phase2D-Work-Package
approval_evidence: human-approved-exact-package
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
successors: PROV-20260816-react-admin-phase2d-backend-public-contract-hardening; PROV-20260817-react-admin-phase2d-h-closure-gate-amendment
---

# React 管理端 Phase 2D：Anomalies／Import Warning Query Real-data 工作包（防偷懶版）

## Supersession record（2026-08-17）

本包的候選實作已由Phase 2D-H補齊severity/public enum contract，並由Closure Amendment以真Chrome
帳密→TOTP Session完成兩個核准GET→DOM及0 non-GET驗收。原本失效的freeze receipt與舊full-suite數字
不重寫為PASS；本包改標`superseded`，由兩個successor及其current evidence承接。disposable MySQL仍為
人工豁免`NOT_RUN`，不構成Anomalies mutation授權。

## 0. Activation gate

本文件已獲人工核准。只有使用者明確回覆：

> 核准此 exact Phase 2D Work Package

才授權下列 exact production/test write set。只回覆「繼續」「下一個 phase」授權建立本 proposed
工作包，不自動授權 production mutation。

Integration Owner 收到核准後必須先：

1. 將本文件 `declared_status` 更新為 `approved`／`in-progress` 並記錄 approval evidence；
2. 記錄 current branch、HEAD、`git status --short`；
3. 對全部 exact write-set path 保存存在性、size、mtime、SHA256 的 collision inventory；
4. 特別標記目前 `AnomaliesPage.tsx/.css` 為 untracked user baseline，不得以歷史 Desktop 副本覆蓋；
5. 宣告 `CONTRACT_MATRIX_FROZEN` 前，所有 production Writer 固定等待。

禁止 checkout、reset、clean、stash、切分支、建立 worktree、stage、commit、push。

## 1. Goal

把現有 `AnomaliesPage` 六筆內嵌假資料替換成：

- canonical anomaly summaries；
- import warning current tasks；
- strict typed query errors；
- loading／empty／partial failure／retry／pagination；
- server-neutral recovery navigation；
- raw detail 缺口的原位 unavailable。

保持 KPI、filters、cards、Drawer 與 CSS hierarchy，不啟用任何 mutation。

最高合法完成狀態：`completed-local-validated`。本波不是 entry cutover 或 Streamlit retirement。

### 1.1 2026-08-16 fresh audit 結果

本工作包目前狀態為 `blocked`，阻擋碼為 `BLOCKED_BACKEND_PUBLIC_CONTRACT_GAP`：真實 Chrome
登入後，Import Warning tasks 可正常載入；Anomalies summaries 的 live payload 則回傳空字串
`severity`。這與候選端嚴格 decoder 及原凍結矩陣宣稱的 `warning | blocking` 不一致。live Pydantic
欄位本身僅宣告 `str`，因此 G1 契約矩陣失效，G7 Network→DOM 不通過。禁止把 decoder 放寬為任意
字串或在前端猜 severity。後端 production 不在本包 write set，需另案核准 public-contract hardening。

同次 fresh audit 另確認：Phase 2D focused frontend 為 4 files／59 tests PASS、focused backend 為
22 tests PASS；但全前端 suite 為 420 PASS／12 FAIL，lint exit 0 但有 2 warnings。因此 G6 亦未通過，
不得沿用先前 368 tests／0 warnings 的完成宣告。

## 2. Exact HTTP allowlist

Frontend production code只可呼叫：

1. `GET /api/v1/anomalies`
2. `GET /api/v1/import-warning-tracking/tasks`

所有其他 `/api/v1/anomal*`、`/api/v1/import-warning*` endpoint固定禁止。測試必須以 fetch/transport spy
斷言 method/path allowlist；unexpected request立即 fail。

Request budget：

| User action | Allowed calls | Maximum |
|---|---|---|
| page mount | anomaly summaries offset 0 + warning tasks offset 0 | 各 1 |
| retry one failed family | 該 family offset 0 | 1 |
| load more anomalies | anomalies next offset | 1 |
| load more warnings | warnings next offset | 1 |
| category/status local presentation filter | none | 0 |
| open/close Drawer | none | 0 |
| disabled claim/resolve | none | 0 |
| navigation anchor | hash-only | 0 mutation |

不得以 N+1 detail calls、raw recovery calls或 background polling補欄位。

## 3. Contract-first artifact

Integration Owner 建立：

`document/架構重整/03_追蹤清單與證據/evidence/PROV-20260816-react-admin-phase2d-anomalies-query/contract-field-matrix.md`

每列必須有：

`surface_field_id | endpoint | method | query | JSON path | Pydantic file:line | required | nullable | enum/range | privacy | disposition | UI slot`

Disposition 限：

- `READY_TYPED_DISPLAY`
- `READY_TYPED_INTERNAL_ONLY`
- `PRESENTATION_CONSTANT`
- `BACKEND_GAP`
- `OUT_OF_SCOPE`

Contract Scout 必須逐欄證明：

- anomaly `display_snapshot` 固定為 `BACKEND_GAP`，client request 固定 `include_snapshot=false`；
- anomaly timeline/recovery snapshots/action source bindings不得穿透；
- source_identity/internal fingerprint 不 render；
- import-warning task fields與 navigation enum exact；
- generic anomaly workflow與warning tracking statuses 分開；
- endpoint×allowed status/error matrix；
- current route/schema/test 的 base-drift/collision。

Matrix freeze receipt可保存內容 SHA256作 artifact integrity；hash不是任務 identity或 ownership lock。

## 4. Exact write set 與 lane ownership

### Integration Owner（唯一 shared writer）

- 本 specification／Work Package status與必要勘誤
- `document/架構重整/02_決策與退役執行記錄/README.md`
- `document/功能開發計畫/React管理端遷移與UI真實業務流程驗收計畫.md` 的 Phase 狀態列
- Phase 2D evidence directory／receipts

Integration Owner 不在 Writer 運行中修改 production hot paths。

### Lane A — Contract Scout（strict read-only）

Write set：無。

交付 chat handoff：逐欄 matrix、endpoint/status matrix、current collision inventory、缺口與 exact test來源。
不得寫 contract artifact；Integration Owner fresh-read 後唯一落盤與 freeze。

### Lane B — Backend Contract Test Writer

Exact write set：

- `tests/test_anomaly_registry_router.py`（新增）
- `tests/test_import_warning_tracking_api.py`（只補 query contract tests）

禁止修改 `api/`、`domains/`、`subsystems/`、repository、DB。若 live route無法通過已核准 safe contract，
回報 `BACKEND_PUBLIC_CONTRACT_GAP`，不得自行 harden backend。

### Lane C — Frontend Client Writer

Exact write set：

- `ui_react/src/api/anomalies/anomaly_query_schemas.ts`
- `ui_react/src/api/anomalies/anomaly_query_errors.ts`
- `ui_react/src/api/anomalies/anomaly_query_client.ts`
- `ui_react/src/tests/fixtures/anomalies/anomaly_query_contract_fixtures.ts`
- `ui_react/src/tests/anomaly_query_client.test.ts`

不得修改 shared transport/runtime decoder/Auth/session/package/lockfile。

### Lane D — Adapter Writer

Exact write set：

- `ui_react/src/adapters/anomalies/anomaly_query_adapter.ts`
- `ui_react/src/tests/anomaly_query_adapter.test.ts`

不得修改 page/client/schema。只接受 Lane C exported types。

### Lane E — Presentation Writer

只有 Lane B/C/D freeze 後可開始。

Exact write set：

- `ui_react/src/pages/AnomaliesPage.tsx`
- `ui_react/src/pages/AnomaliesPage.css`
- `ui_react/src/tests/anomalies_page_real_data.test.tsx`
- `ui_react/src/tests/anomalies_no_fake_mutation.test.tsx`

必須語意 merge目前 untracked UI baseline；禁止從 Desktop重新 copy整檔。

### Lane F — Fresh Verification Auditor（strict read-only）

Write set：無。只回傳 exact commands、exit codes、raw counts、warnings、write-set drift與 findings。
不得建立/修改 receipt；Integration Owner在最新 candidate親自重跑關鍵 gates後唯一寫 evidence。

## 5. Dependency schedule（最多四 slots）

```text
Round 0: Integration snapshot + Lane A Contract Scout
Gate: CONTRACT_MATRIX_FROZEN

Round 1 parallel:
  Lane B Backend contract tests
  Lane C Frontend client
Gate: BACKEND_QUERY_CONTRACT_VERIFIED + CLIENT_FROZEN

Round 2:
  Lane D Adapter
Gate: ADAPTER_FROZEN

Round 3:
  Lane E Presentation
Gate: CANDIDATE_FROZEN

Round 4:
  Lane F Fresh Auditor
  Integration final read/diff/evidence
```

任何 lane 不得再 spawn writer處理同一檔案。若 base drift，停止受影響 lane，重新盤點，不沿用舊 matrix。

## 6. Backend contract tests（G2）

`tests/test_anomaly_registry_router.py` 至少驗：

1. authenticated GET summaries 200；
2. `include_snapshot=false` 時每筆 `display_snapshot` 為 null，且 safe scalar fields exact；
3. severity只允許 warning/blocking；workflow status只允許 open/claimed/resolved；
4. staff calendar navigation nullable或 exact `{staff_id>0,target_date}`；
5. Query不呼叫 claim/resolve/save/commit；
6. invalid limit/offset 422；
7. unauthenticated 401；
8. repository unavailable仍保持現有 typed error，不在本波改 route。

`tests/test_import_warning_tracking_api.py` 至少補：

1. tasks query完整輸出 all required fields；
2. tracking status六值中的兩個 sentinel；
3. navigation action合法 enum／null；
4. query零 application mutation；
5. invalid limit/offset 422；
6. no corrected_fields/raw source payload。

測試不得只 assert 200；至少逐欄比對兩組不同 sentinel，避免 route回固定資料仍全綠。

## 7. Frontend client contract（G3）

### Required methods

```ts
getAnomalySummaries(params, options): Promise<AnomalySummary[]>
getImportWarningTasks(params, options): Promise<ImportWarningTask[]>
```

不得多出第三個 production method。

### Request rules

- per-request `sessionClient.getToken()`；token missing fail-before-fetch；
- strip caller Authorization；
- GET only；
- anomaly request永遠 `include_snapshot=false`；
- AbortSignal、timeout、baseUrl只依既有 transport options；
- query key/range在client驗證，不依FastAPI 422作前端基本驗證。

### Decoder rules

new schemas與tests掃描禁止：

```text
z.any
z.unknown
z.record
.passthrough(
.catch(
.default(
.coerce
.preprocess
.transform
as any
unknown as
```

每個 DTO negative tests至少：

- missing required key；
- extra envelope key；
- extra nested key；
- wrong primitive；
- nullable violation；
- invalid severity/status/navigation enum；
- bad fingerprint；
- negative version；
- non-null display_snapshot；
- malformed staff-calendar date；
- success envelope data null。

writer fixture不是唯一 provenance；至少一組 fixture直接對應 backend TestClient response JSON。

## 8. Adapter contract（G4a）

Adapter只做 presentation mapping：

- severity `blocking → CRITICAL`、`warning → WARNING`；
- generic workflow badge一對一；
- warning tracking badge一對一，不能映射成 generic claimed/resolved；
- source domain allowlist map，unknown→其他；
- KPI標示 loaded-scope；
- import warning保持 occurrence-level identity；
- safe navigation enum→固定 hash；
- source_identity/fingerprint只作 internal key，不進 visible view model；
- 缺 typed title/description/evidence/action輸出固定 `unavailable` discriminant，不生成中文故事。

禁止 adapter：

- 依 definition code推測title、severity、修復路徑或blocker；
- 解析 issue code/message產生 action；
- 合併多欄 warning 為單一可放行案件；
- 計算全庫total；
- 使用 current time、random、mockData、固定 ANM ids。

兩組變動 sentinel必須證明輸入改變後 DOM/view model同步改變。

## 9. Page preservation 與 stable surfaces（G4b）

至少保留／建立：

| Stable ID | Requirement |
|---|---|
| `anomalies.page` | page root可見 |
| `anomalies.kpis` | 四張 KPI cards可見 |
| `anomalies.category-filters` | category bar可見 |
| `anomalies.status-filters` | status pills可見 |
| `anomalies.list` | anomaly cards／empty/error state |
| `anomalies.import-warnings` | independent warning tasks section |
| `anomalies.drawer` | selected summary Drawer可開關 |
| `anomalies.drawer.root-evidence` | typed gap原位 unavailable |
| `anomalies.drawer.recovery` | typed gap或server navigation |

DOM存在不代表保留；tests必須斷言不是 `display:none`、`hidden`、`aria-hidden=true`、opacity 0 或零尺寸
的作弊節點。component test無 layout時至少檢查visible/accessible；browser gate再檢查bounding rectangle。

### Locked controls

Integration freeze前從 current UI產生 exact mutation-control inventory。至少：

- `anomalies.card.claim`
- `anomalies.drawer.resolve-reason`
- `anomalies.drawer.resolve`

每一個都必須 native disabled、無 fake handler。不要用固定總數替代 stable-ID inventory。

### Allowed controls

- local category/status filter；
- retry anomalies／retry warning family；
- load more；
- open/close Drawer；
- hash navigation anchor。

## 10. Mock laundering 防護

Production dependency closure由 `AnomaliesPage` 遞迴imports到client/adapter，不得觸及：

- `api/mockData.ts`
- `MOCK_*`
- 現有六筆 `ANM-001..ANM-006`
- 固定 `ORD-2026-0801` 等樣本
- `setAnomalies` local business state
- `alert()`／`confirm()`／`prompt()`
- `new Date()`生成claimed time

將現有六筆 mock 的 IDs、姓名、固定描述、固定 evidence 字串建立 literal corpus scan；production 0 hits。
Presentation constant只允許 category labels、status labels與unavailable文案。

## 11. Required tests

Backend：

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/test_anomaly_registry_router.py `
  tests/test_import_warning_tracking_api.py `
  --basetemp .pytest_tmp/react-phase2d-anomalies-contract -q
```

Frontend focused：

```powershell
cd ui_react
npx vitest run `
  src/tests/anomaly_query_client.test.ts `
  src/tests/anomaly_query_adapter.test.ts `
  src/tests/anomalies_page_real_data.test.tsx `
  src/tests/anomalies_no_fake_mutation.test.tsx
```

Frontend full/static：

```powershell
npm test -- --reporter=dot
npm run lint
npm run build
```

Static scans：

```powershell
rg -n "mockData|MOCK_|ANM-00[1-6]|alert\(|confirm\(|prompt\(|new Date\(" `
  ui_react/src/pages/AnomaliesPage.tsx `
  ui_react/src/api/anomalies `
  ui_react/src/adapters/anomalies

rg -n "z\.any|z\.unknown|z\.record|\.passthrough\(|\.catch\(|\.default\(|\.coerce|\.preprocess|\.transform|as any|unknown as" `
  ui_react/src/api/anomalies `
  ui_react/src/adapters/anomalies `
  ui_react/src/tests/anomaly_query_client.test.ts `
  ui_react/src/tests/anomaly_query_adapter.test.ts
```

任一 forbidden scan有 hit固定 FAIL；不得以 comment或dead code allowlist掩蓋。

## 12. Browser runtime gate（G6）

使用真 FastAPI 8000、Vite 5173與已完成 Phase 2C 的人工 TOTP Session。禁止 dev token／fixture bearer。

Auditor只讀記錄：

1. Login後 Shell可見；
2. Network中兩個 allowlisted GET帶 Session並回200；
3. Anomalies DOM顯示live cards或合法empty；
4. Import warnings DOM顯示live tasks或合法empty；
5. 點卡片開Drawer，raw slots顯示unavailable而非JSON；
6. filter不發request；
7. locked controls disabled且0 POST；
8. no token/fingerprint/source identity/raw PII出現在DOM／console；
9. backend停用或401時只影響對應query family且fail closed；
10. viewport內主要surface有非零bounding rect。

若本機資料沒有active anomaly/warning，browser empty state仍可PASS；populated mapping由provenance component
sentinel證明。不得為了畫面有資料而寫DB、seed或改fixture。

## 13. Evidence receipts（G7）

Integration Owner唯一建立：

1. `contract-field-matrix.md`
2. `contract-matrix-freeze-receipt.md`
3. `candidate-change-inventory.md`
4. `verification-receipt.md`
5. `browser-smoke-receipt.md`
6. `open-findings.md`
7. `evidence-summary.md`

每份必須記錄current branch/HEAD、commands、exit codes、真實test counts、warnings、not-run與blockers。
不得引用其他代理「已通過」文字或歷史 counts作fresh evidence。

## 14. Completion gate

| Gate | PASS condition |
|---|---|
| G0 Scope/write set | 所有非baseline bytes只在exact paths；0 DB/backend production/shared hotspot |
| G1 Contract freeze | matrix逐欄完成；raw fields與display/internal privacy明確 |
| G2 Backend evidence |兩route query contract tests通過且證明零寫入 |
| G3 Client | strict decoders、auth/abort/pagination/negative tests通過 |
| G4 Adapter/Page | visual hierarchy保留；real DTO；raw slots unavailable；partial failure隔離 |
| G5 Zero fake mutation | exact locked inventory native-disabled；0 non-GET／fake success |
| G6 Static/full suite | focused/full tests、lint、build、UTF-8、diff/write-set scan通過 |
| G7 Browser/evidence | 真Session Network→DOM與7份fresh receipts完整 |

任何 gate `BLOCKED`／`NOT_RUN` 時不得標 completed。Auth/browser若暫時不可用，只能阻擋G7；G1–G6
仍必須完成，不得以browser blocker作為什麼都不做的藉口。

## 15. 明確不可接受的虛假完成

- 只移除 `MOCK_` 名稱，但把六筆literal搬到adapter/test helper。
- Anomalies與Warnings全部顯示unavailable，仍宣稱real-data完成。
- 只驗200或只驗envelope，nested data不strict decode。
- 使用 raw detail/recovery JSON填現有title/evidence/action。
- 由source_domain/definition code/message猜業務title、blocking或repair route。
- 把import warning映射成generic resolved／claimed。
- 刪除／隱藏Drawer、filters、cards或mutation controls迴避驗收。
- disabled樣式但仍有handler／POST。
- component test漏mock request而實際打localhost。
- writer自行修改shared decoder、backend schema或Auth讓測試變綠。
- 以snapshot-only、`expect(true)`、`.skip/.todo/.only`或writer fixture自證完成。
- 使用歷史test counts、另一工作區、另一HEAD或舊browser screenshot。

## 16. 多代理執行協議與啟動 Prompts（核准後使用）

本節不是摘要 Prompt，而是不可跳關的協作協議。任何代理回報的 `PASS`、測試數字、截圖或
`victory` 都只是待驗證輸入；只有 Integration Owner 能在最新共享工作樹 fresh-read、重跑及逐 gate
裁決後更新正式狀態。

### 16.1 Integration Owner 主 Prompt

```text
你是 D:\project\Labor_union 的 Phase 2D Integration Owner。你不是轉述員；你是唯一整合、文件與
完成狀態裁決者。其他代理只能交付 candidate，禁止接受任何代理的 COMPLETED／VICTORY_CONFIRMED。

Business outcome：保留既有 AnomaliesPage UI 的資訊架構，把 production 中內嵌的六筆假異常替換為
canonical Anomalies summaries 與 Import Warning tasks 的真實唯讀資料。不得重新設計畫面；不得啟用
claim／resolve／warning transition／repair mutation；不得把 raw dict 顯示或轉譯成業務事實。

權威讀取順序：
1. strict UTF-8 完整讀取 AGENTS.md；若存在再讀 .agents/AGENTS.md。
2. 記錄 branch、HEAD、git status --short；保留全部 dirty／untracked／ignored user成果。
3. README.md、document/架構重整/00_開發者與Agent導覽.md。
4. 00_Global_共同契約.md、15_正式規格索引與裁決總表.md、06_Anomalies_Domain.md、
   22_銀行流水匯入與帳務異常處理正式規格.md。
5. PROV-20260816-react-admin-phase2d-anomalies-query-specification.md 與本 exact Work Package。
6. 最後才讀 live route/schema/subsystem/page/tests；不可以 live code 改寫人工規格。

全域禁止：
- 不得使用 DDH；不得使用 Stitch 或重做 UI；不得讀寫 C:\Users\chris\Desktop 的模板。
- 不得 checkout/reset/clean/stash、stage/commit/push、建立branch/worktree或操作遠端。
- 不得安裝套件；不得修改 package*.json、shared transport/runtime decoder、Auth、App/Shell、其他頁面。
- 不得修改 DB/schema/migration/seed/backfill；不得退役或修改 Streamlit entrypoint。
- 不得把 secret、token、TOTP、完整個資寫入命令、DOM、log、fixture、screenshot或receipt。
- 所有手動維護的新增／修改 source/test 必須有 coding-rule 的繁體中文結構化檔頭，strict UTF-8無BOM。

唯一核准的 production HTTP operations：
- GET /api/v1/anomalies?include_snapshot=false
- GET /api/v1/import-warning-tracking/tasks
任何其他 Anomalies／Warning endpoint、任何 non-GET，均 OUT_OF_SCOPE。若現有契約不足，保留原UI
slot並顯示「後端尚未提供」，記錄 BACKEND_PUBLIC_CONTRACT_GAP；禁止擴後端、解析 snapshot、
猜 root cause、把 warning 映成 generic claimed/resolved，或用假資料補齊畫面。

先建立 current-working-tree baseline：branch、HEAD、每個 exact write-set path 的 tracked/untracked狀態、
size與SHA256。hash只作本輪byte-level保護，不作任務身分。AnomaliesPage.tsx/.css是user baseline，必須
語意合併，不得從commit或Desktop覆蓋。任何非write-set path在結案時與baseline不同，判定
WRITE_SET_VIOLATION；先停工辨識owner，不可自動復原。

固定狀態機，不得跳步：
SNAPSHOT_SAVED
→ CONTRACT_SCOUT_RETURNED
→ MATRIX_FROZEN_BY_INTEGRATION
→ BACKEND_AND_CLIENT_CANDIDATES_FROZEN
→ ADAPTER_CANDIDATE_FROZEN
→ PRESENTATION_CANDIDATE_FROZEN
→ FRESH_AUDIT_RETURNED
→ INTEGRATION_REVERIFIED
→ completed-local-validated | blocked

規則：
1. Contract Scout完成前，不得派任何Writer。Scout只回傳證據；你必須親讀route/schema並落盤matrix。
2. Matrix freeze後，Backend Test Writer與Frontend Client Writer才可平行；兩者write set不可重疊。
3. Adapter Writer等待client interfaces freeze；Presentation Writer等待client與adapter freeze。
4. 任一handoff前後都重查HEAD、dirty collision及write-set digest。發生base drift時回到受影響freeze點。
5. Auditor唯讀，不得寫receipt。你是唯一receipt／README／Work Package status writer。
6. AUTH／TEST_DATA／BROWSER blocker只可阻擋G7；不得阻擋G1–G6。不得用「無法登入」提前停工。
7. 真瀏覽器登入只由使用者在Chrome輸入帳密與TOTP；代理不得要求、讀取、保存或代輸憑證。
8. 每個pytest使用唯一 --basetemp .pytest_tmp/<phase2d-lane>，不得共用cache或把temp放根目錄。
9. 不接受固定預期test count；receipt記錄當次命令、exit code、真實file/test count、warnings與HEAD。
10. 不接受writer自行定義fixture再用同一fixture自證契約；至少一組contract vector必須直接追溯live
    Pydantic model／route test，且由Integration或Auditor另製adversarial negative vector。

G0–G7逐項裁決。任一必要gate BLOCKED／NOT_RUN時不得稱完成，不得使用VICTORY_CONFIRMED。
允許的最終狀態只有：completed-local-validated、blocked、failed-scope-violation。
```

### 16.2 Lane A — Contract Scout Prompt（唯讀）

```text
你是 Phase 2D Contract Scout。全程唯讀，不得建立或修改任何檔案。

逐一核對兩個核准GET的route、response_model、Pydantic model、enum、nullable/required、auth、pagination、
error status與focused tests。對每一個既有AnomaliesPage可見欄位輸出：
surface_field_id | current label | endpoint | exact JSON path | Pydantic path:line | required/nullable |
DISPLAY/INTERNAL_ONLY/SENSITIVE_REDACTED/PRESENTATION_CONSTANT/BACKEND_GAP | evidence。

必須特別證明：include_snapshot=false時display_snapshot為null；generic anomaly與import warning是兩種不同
state machine；raw detail/timeline/recovery不可進client；severity只有live enum允許值。找不到證據就標
BACKEND_GAP，不得推論。

最後只使用mandatory handoff格式回報。LANE_STATUS最多只能candidate_ready_for_integration，不能complete。
```

### 16.3 Lane B — Backend Contract Test Writer Prompt

```text
你是 Phase 2D Backend Contract Test Writer。只有Integration提供MATRIX_FROZEN證據後才可開始。
你的exact write set僅限本Work Package列出的兩個focused route test檔；不得改production route/schema/
subsystem/repository，也不得改共享fixture或conftest。

測試必須使用去敏deterministic資料，證明兩個GET的success/error/auth契約、include_snapshot=false的
null行為、enum/state原樣傳輸，以及query前後repository/outbox/job/business row無寫入。不能只assert 200，
不能用mock把不存在的route行為製造出來，不能改assertion迎合live drift。遇到public contract不足立即
回報BACKEND_PUBLIC_CONTRACT_GAP並停止該項，不可擴scope。

執行focused pytest與strict UTF-8/header檢查；回傳raw command/result，不寫evidence文件。
```

### 16.4 Lane C — Frontend Client Writer Prompt

```text
你是 Phase 2D Frontend Client Writer。只有MATRIX_FROZEN後才可開始。只修改本Work Package exact
write set 指定的 `src/api/anomalies/**` 及其 exact client tests／contract fixtures。本包兩個唯讀 query
family 依既有 exact write set 由此 Phase 2D client 組合；不得自行建立未授權的
`src/api/import_warnings/**` 目錄。

每次request即時讀current in-memory Session token，不可module-load
快取；caller不得覆蓋Authorization。只允許兩個核准GET，支援AbortSignal與契約允許的pagination。
使用strict Zod：禁止z.any/z.unknown/z.record/.passthrough/.catch/.default/.coerce/.preprocess/.transform、
unknown as與只驗envelope。server required key不得optional；nullable不等於optional；extra nested field需fail。

每個DTO至少測missing required、wrong primitive、extra envelope、extra nested、null violation、invalid enum，
另測401/403及live route實際允許的錯誤矩陣、token切換/登出不沿用舊token、abort與unexpected non-GET=0。
component/unit test不得漏mock而打localhost。只回candidate，不改page、adapter、shared transport或docs。
```

### 16.5 Lane D — Adapter Writer Prompt

```text
你是 Phase 2D Adapter Writer。等待Client interfaces freeze後開始。只修改本Work Package指定的
src/adapters/anomalies/**與exact adapter tests。

Adapter只能做格式化、排序與safe presentation mapping；不得推導root cause、repair route、claimability、
resolved狀態或跨state-machine對應。Presentation constants只能是既有UI label/category順序，不得含case、
phone、date、amount、status等假business facts。BACKEND_GAP必須產生typed unavailable slot，不得回空字串
冒充真資料。使用兩組不同sentinel DTO，證明DOM-facing model會隨server data改變且沒有mock literal滲入。

不得修改page/client/backend/docs。只回candidate與raw focused test結果。
```

### 16.6 Lane E — Presentation Writer Prompt

```text
你是 Phase 2D Presentation Writer。等待Client與Adapter freeze後開始。只修改AnomaliesPage.tsx/.css及
本Work Package列出的page/no-fake-mutation tests。這兩個page檔是untracked user visual baseline，必須逐段
語意合併；禁止整檔覆蓋、簡化、重排資訊架構或移除Drawer/filter/card/action slot。

以兩個真GET接線，保留category/status filters、KPI、cards、Drawer、partial-error/empty/loading/retry狀態。
只有server-backed fields可顯示真值；raw detail/recovery slots顯示明確unavailable。兩來源分別失敗時彼此
隔離，不可整頁歸零。所有claim/resolve/deep-link/transition控制保留原位置、使用exact stable control ID、
native disabled且沒有handler；click測試須斷言fetch/transport總non-GET=0、DOM server facts不變、0 alert/
confirm/prompt/toast假成功。

Production import closure不得碰mockData或其轉存helper。禁止display:none/opacity:0/zero-size/aria-hidden
隱藏驗收surface；測試須逐stable ID確認存在、可開Drawer/切filter，且用兩組sentinel證明資料非硬編碼。
不得修改client/adapter/backend/shared/docs。只回candidate，不宣稱completed。
```

### 16.7 Lane F — Fresh Verification Auditor Prompt（唯讀）

```text
你是 Phase 2D Fresh Verification Auditor。全程唯讀，不得apply_patch、格式化、更新snapshot、寫receipt或
修改任何狀態。不得相信Writer／Coordinator提供的test數字；在目前共享工作樹fresh-read所有candidate
diff、matrix、live schema與tests後親自重跑G0–G7所需命令。

必查：write-set外byte drift、mock dependency closure與prototype literal corpus、只允許兩個GET、non-GET=0、
strict Zod禁用語法、fake success、disabled handler、hidden surfaces、test .skip/.todo/.only、expect(true)、
snapshot-only、未預期localhost request、warnings、UTF-8/header、git diff --check、build/lint/full Vitest與focused
pytest。若真Chrome gate已執行，核對Network method/path/status、已登入Session、兩來源sentinel與DOM；不得把
happy-dom、curl、API 200或舊截圖當G7。

只回raw commands、exit codes、counts、warnings、findings與LANE_STATUS。任何無法驗證項標NOT_RUN或BLOCKED，
不能補寫證據或宣布victory。
```

### 16.8 所有 Lane 強制 Handoff 格式

```text
LANE_STATUS: candidate_ready_for_integration | blocked | failed
BASE_BRANCH_HEAD:
FILES_READ:
FILES_CHANGED:              # 唯讀lane必須為NONE
WRITE_SET_AUDIT:
CONTRACT_OR_SURFACE_IDS:
COMMANDS_RUN:
RAW_RESULTS_WITH_EXIT_CODES:
WARNINGS_AND_TEST_NOISE:
NEGATIVE_TESTS_OR_ADVERSARIAL_CHECKS:
UNVERIFIED_ITEMS:
BLOCKERS_WITH_EVIDENCE:
NEXT_OWNER_ACTION:
```

缺任一欄、只有「all passed」、只有截圖或引用其他代理結論，都視為不完整handoff，退回原Lane補證據。

### 16.9 Integration 最終裁決算法

1. fresh-read所有changed files，不以handoff摘要代替code review。
2. 對照baseline列出write-set內外每一個byte change；越界即停止整合。
3. 逐matrix row檢查client schema、adapter mapping與至少一個DOM assertion；READY欄位不可全部unavailable。
4. 親自重跑focused tests → full frontend suite → lint → build → focused backend tests → UTF-8/header/diff/secret scans。
5. 在使用者已手動完成兩段式登入的Chrome session執行真Network→DOM；不進行任何mutation。
6. 依G0–G7逐項寫PASS/BLOCKED/NOT_RUN及直接證據。不得用總測試綠取代單一gate。
7. 只有G0–G7全PASS，才可寫`completed-local-validated`；G7缺失時固定`blocked-real-browser-evidence`；
   contract不足則`blocked-backend-public-contract-gap`。禁止使用`VICTORY_CONFIRMED`。
8. 最後才由Integration單一writer更新7份receipts、Work Package status、README及主計畫；數字必須來自本次raw output。

## 17. DB gate

| Gate | Status | Evidence/reason |
|---|---|---|
| Scope gate | PASS | exact scope為query-only React與route contract tests |
| Change inventory | NOT_RUN | 無DB write set |
| Static release gate | NOT_RUN | 無migration release |
| Descriptor gate | NOT_RUN | 無schema變更 |
| Read-only plan gate | NOT_RUN | 不執行DB tooling |
| Engine verification gate | NOT_RUN | 無DB mutation |
| Developer acceptance gate | NOT_RUN | 不操作developer DB |

總結：`DB_CHANGE_NOT_READY`。
