---
status: in-progress
priority: P0
owner: global-admin-web-presentation
domain: Global
subsystem: admin-web-presentation-adapter
initiative: react-admin-migration
updated: 2026-08-20
approval_required: 每一 production mutation／entry switch／retirement wave仍需exact Work Package核准
approval_evidence: user-delegated-phase3-through-phase6-execution-2026-08-20
prerequisites: Part_00_全域測試資料治理與Scenario契約.md; UI真實業務流程測試資料與驗收主計畫.md
---

# React 管理端遷移與 UI 真實業務流程驗收計畫

## 0. 人工確認與授權狀態

- 2026-08-15 使用者提出：讀取
  `C:\Users\chris\Desktop\project\Labor_union` 的 React 模板，將 Streamlit 轉移為 React，並與
  `UI真實業務流程測試資料與驗收主計畫.md` 合併執行。
- 2026-08-16 使用者進一步確認：Desktop React 模板目前的頁面、抽屜、資訊架構與互動大致就是
  目標 UI；遷移主線是保留既有畫面，把 `mockData`、頁面內嵌資料與假 handler 換成 real data／
  real API，而不是先重新設計每一個狀態或要求逐 action 完成產品裁決。
- 本文件已由2026-08-20 Phase3–6正式交接與持續目標確認為in-progress架構；production施工仍只依各自
  已核准exact Work Package，不因整體目標自動授權schema、既有DB mutation、provider、entry switch或退役。
- 每一波仍須依第10節建立／執行exact-scope Work Package；不得把整體確認解讀成一次移除全部
  Streamlit的授權。

### 0.1 2026-08-22營運作業前端優先序

最新人工裁決先完成訂單管理→排班日曆→月嫂名冊→資料匯入。每頁依序通過fixture／focused UI tests、
allowlisted development `lu_test_*`真MySQL／API／browser、以及另行明確授權後的工會主機真實業務資料驗收。
`lu_test_*`不是工會真實資料；本機gate失敗不得把候選交給工會主機試錯。此順序調整不授權production host、
entry switch、schema／migration、provider side effect或未完成安全門的Apply。

## 1. Business scenario

已登入且 enabled 的工會人員，需要在目前已接受的 Desktop React UI 中操作真實資料。React 的
頁面、抽屜、tab、欄位分組與主要互動先視為 presentation baseline；工程工作的預設處置是為現有
component 建立 typed API adapter，將 mock view model 換成 server view model，而不是重新設計 UI。

只有接線時命中下列任一條件，才建立 bounded exception 並請人工裁決：

1. 現有後端沒有對應 endpoint／application capability。
2. 現有 API 回傳不足以填入既有 UI，或只有 raw／不穩定 contract。
3. 現有 UI action 與已確認業務規則、資安或資料 owner 明確衝突。
4. 現有後端能力已不符合實際業務，可能需要替換或退役；不得因為已實作就預設保留。

未命中例外的頁面與 action 不等待額外微觀產品討論，直接進入 Mock → API mapping、接線與驗收。

```text
管理人員登入
→ React shell 取得 server-verified session／principal
→ 現有 React component 透過 bounded page adapter 呼叫 FastAPI
→ runtime validation 成功後形成 typed view／typed client error
→ React 只顯示 loading、stale、blocker、receipt 與 repair navigation
→ 同一 UI scenario 與 Streamlit／API／DB oracle 對照
→ 頁面 real-data／action 驗收通過後切換 navigation
→ 發現問題時只把該 entry 路由切回已驗證 Streamlit，不回滾 Domain data
```

## 2. Authority 與相鄰計畫

- Global 共同契約：`document/架構重整/01_規格基線/00_Global_共同契約.md`
- 正式架構與 Domain 索引：`15_正式規格索引與裁決總表.md`
- Deployment／管理端安全邊界：`18_Global_Deployment與治理正式規格.md`
- Entry point governance：`19_Global_Entry_Point_Governance.md`
- Access／session：`17_External_Integration_LINE_Access正式規格.md`
- 各業務頁 owner：`16`～`24` 及其引用的 Domain 規格。
- 真實流程驗收治理：`document/功能開發計畫/UI真實業務流程測試資料與驗收主計畫.md` 與
  `Part_00_全域測試資料治理與Scenario契約.md`。
- Desktop React 完整 UI surface inventory：
  `document/架構重整/03_追蹤清單與證據/evidence/2026-08-16_react_admin_ui_surface_inventory.md`。
- 逐頁精簡遷移執行裁決：
  `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-page-slice-migration-execution-decision.md`。
- `document/管理端UI/可替換前端與Streamlit薄顯示層重整計畫.md` 只作歷史來源；其中
  ADAD、Checkpoint、Source Lock、system map 與已被 current SSOT 取代的業務規則不具現行 authority。

本計畫只擁有 presentation migration、frontend runtime contract、entry replacement 與 UI acceptance
編排，不擁有 Domain root facts、金額、日期、資格、狀態機或 transaction formula。

## 3. React 模板 inventory 與採用裁決

### 3.1 兩個模板現況

| 來源 | 可採用內容 | 不足／限制 |
|---|---|---|
| `C:\Users\chris\Desktop\project\Labor_union\ui_react` | 11 個頁面的資訊架構、共用 layout、drawer、視覺 token 與互動 mock | 沒有真實 API、runtime schema validation、server session、router、測試；大量 mock state |
| `D:\project\Labor_union\ui_react` | React 19／TypeScript 6／Vite 8、oxlint、工作區 assets、初版 API client | 只掛資料匯入頁；client 使用不存在的 generic import routes，缺 authentication 與正式 command envelope |

排除 `node_modules`、`dist`、cache 後，兩側共有 10 個同名檔且內容全部不同；桌面側另有 27 個
UI mock 檔，工作區另有 13 個工具鏈／client／asset 檔。兩側不是可直接覆蓋的版本關係，必須逐檔
語意合併。

### 3.2 允許採用

- Desktop React 的 11 個頁面、Login、Shell、所有 Drawer／Modal／Tab、資訊分組、視覺層級、
  conditional rendering 與主要互動，作為本次遷移的 UI baseline；除 bounded exception 外不重畫。
- `MasterLayout`、`Drawer` 的 visual structure 與 responsive layout。
- Orders、Scheduling、Staff、Import、LINE、Finance、Anomalies、Reports、System／Data Browser、
  Access 等頁面的既有 component tree；資料來源與 mutation handler 必須替換。
- 不含業務語意的 design tokens、spacing、色彩、icon slot 與 empty/loading/error layout。

### 3.3 禁止採用

- `node_modules`、stale `dist`、桌面 `package-lock.json` 及未使用的 `lucide-react` dependency。
- `mockData.ts` 作為 production runtime、canonical fixture 或業務 SSOT。
- 任意帳密即可進入的 local login、只檢查六碼長度的假 TOTP、role-based menu、預填密碼。
- 硬編碼的「系統在線」、通知數、管理員身分、成功、餘額、狀態或 receipt。
- generic cross-domain `/api/v1/imports/{category}/preview|apply`、raw JSON type assertion、以中文
  `detail`／message 推導 retry 或 action。

### 3.4 已人工確認的訂單 SOP 業務裁決（2026-08-16）

下列裁決來自使用者對 Desktop `OrderTracker` 11 步 SOP 抽屜的直接確認。它們是後續
Orders presentation、API disposition 與 scenario acceptance 的業務輸入；不授權 production
code、API、schema、測試資料或 entry cutover mutation。

| SOP 議題 | 人工裁決 | Presentation／backend disposition |
|---|---|---|
| 客戶收到的正式月嫂推薦 | 一般情況只正式推薦一位；只有單一月嫂無法覆蓋全部正式服務日期時，才允許 2–4 位月嫂的分段方案作為一個整體正式推薦 | Candidate Contact Pool 可以保留多位候選與意願紀錄，但 Desktop 多選後一次傳送多位競爭履歷的 mock 不能採用。multi-caregiver 必須由 server 以 confirmed service dates、fresh availability 與完整 coverage evidence 證明單一月嫂無法覆蓋，並以一個含 2–4 個連續、不重疊 segments 的正式方案呈現；客戶不是在多位競爭候選中自行拼選。 |
| 完工後的狀態 | 拆成三個獨立 owner projections | `服務完成` 由 Orders 官方服務日／completion instant 投影；`客戶款項結清` 由 Client Finance obligation／canonical bank fact 投影；`月嫂薪資核銷` 由 Staff Payables／canonical bank fact 投影。三者不是新增三個可由 UI 寫入的 DB status，也不得由同一 stage、alert 或 endpoint 互相推導。 |
| 緊急聯絡電話缺漏 | 顯示警告但允許繼續媒合 | warning 必須由 server typed view 的 stable code 提供，UI 不得由空字串自行推導；它不能阻擋已確認允許的 Candidate Contact Pool、履歷或 matching actions。欄位 owner、masking、repair entry 與其他受影響 action 仍需契約裁決。此決策不放寬 Terms、服務時段、資格、availability、契約、訂金與確認日期等既有正式 blocker。 |

上述三項只列為已知接線例外，不是開始 React 遷移前必須繼續展開的逐欄位討論。其餘 UI 先依
既有畫面接 real data；若 adapter 無法忠實填入既有 view model，再回到 bounded exception 處理。

## 4. 待人工確認之目標架構：Global → Domain → Subsystem → Module

```text
Approved Admin Edge
  → React Admin Web Presentation Adapter
    → AccessSessionClient + bounded domain API clients
      → confirmed FastAPI typed routes or separately approved replacements
        → existing Application Workflow Coordinators
          → unchanged owning Domains / typed ports / outer Unit of Work
```

### 4.1 Global

- 將正式 presentation 名稱收斂為 technology-neutral `Admin Web Presentation Adapter`；React 是
  current target，Streamlit 是遷移期 compatibility adapter。
- FastAPI 維持唯一 business HTTP boundary；React 不直接存取 MySQL、Service、Repository、正式檔案
  或 external provider。
- production 優先 same-origin 提供 SPA 與 `/api`；local Vite 使用明確 proxy。若需要 cross-origin，
  origin、methods、headers 與 credentials 必須 exact allowlist，禁止 `*` 或動態 reflection。
- frontend artifact 必須有 build version、digest、FastAPI compatibility、health、CSP 與 rollback identity。
- `VITE_*` 只能放非敏感 runtime config；internal key、DB credential、LINE secret、raw session token
  不得被打包、記錄或顯示。

### 4.2 Domain

- Domain owner、SSOT、root facts、state machine、金額／日期／資格公式及 transaction boundary 全部不變。
- React 不建立 Domain reducer，不解析中文狀態或 error message 決定 action，不把 mock state 升格為事實。
- Query 唯讀、Preview 零寫入、Apply fresh-read；只有 server receipt 能顯示正式成功。

### 4.3 Subsystem

1. `AccessSessionClient`
   - 只映射既有 login、current-session、renew／sliding expiry、logout／revoke typed routes。
   - access token 不得進 URL、localStorage、sessionStorage、log 或 fixture；只把 token 放在 JavaScript
     memory 並不能滿足 F5／new-tab 的日常營運需求。
   - 現有 `/refresh` 仍要求原 bearer token，且只延長同一 server-side session 的到期時間；它不是
     reload 後的 credential recovery mechanism。因此 Phase 1 開工前必須人工裁決下列其一：
     1. `recommended`：React 使用 `HttpOnly + Secure + SameSite` 的 server session／refresh cookie，
        `/me` 可在 reload／new-tab 後恢復 principal；mutation 同步具備 Origin／CSRF 防護，logout
        撤銷 server session 並清除 cookie。既有 bearer route 可在相容期保留給 Streamlit。
     2. 明確接受 reload／new-tab 必須重新登入；UI 不得把 `/refresh` 宣稱為 session restore。
   - cookie／BFF、CSRF、credentialed CORS 與 auth response shape 都是 public contract 變更，必須先有
     獨立核准的 Access Work Package；未裁決前 Phase 1 auth implementation 為
     `BLOCKED_AUTH_RESTORE_DECISION`。
   - invalid、expired、revoked、disabled 一律 fail closed。
2. `AdminWebTransport`
   - 統一 base URL、Authorization、correlation、timeout、abort／supersession 與 envelope parsing。
   - transport／schema／typed backend failure 轉成 typed client error；unknown schema fail closed。
3. Bounded domain clients
   - 每個 client 只對應單一 bounded domain 或已核准跨 Domain coordinator endpoint。
   - success payload 必須 runtime validate；raw `unknown`／`dict` 不得穿透 page renderer。
4. UI operation state
   - shell 只保存 navigation、draft、selection、single-flight、loading、stale、error、receipt presentation。
   - timeout 結果未知時查 receipt／job；不得換 idempotency key 盲目重送。

### 4.4 Module

- React routes、pages、components、view formatter、accessibility、design tokens 與 browser test adapters。
- 純顯示 formatter 可以處理日期／千分位／遮罩後 view，但不能推導正式日期、金額、資格、狀態或 blocker。
- 每個 mutation page 必須把 intent、expected version、Preview fingerprint、stable idempotency key 與
  server receipt 的 lineage 清楚呈現。

## 5. Public compatibility 與 entry point 治理

現有 `ui/app.py` 動態註冊 10 個 Streamlit 頁面。每一個 React route 都是新 external entry，必須逐項：

1. 記錄 source Streamlit entry、React replacement route、operator、business scenario 與 canonical owner。
2. 保持既有 FastAPI contract；若需要新增／修改 route、envelope、auth transport 或 CORS，先回到人工確認。
3. React 驗收通過前，Streamlit entry 維持 active；不得因沒有 static caller 直接刪除。
4. 切換 navigation 後保留可操作 rollback URL；觀測期完成才裁決 replacement／retirement。
5. 每個 mutation slice 必須證明 React forward-written data、receipt、job 與 anomaly 仍可由 rollback
   Streamlit entry query、repair 或 replay；只保留舊 URL 不等於 operational rollback。
6. 執行 focused regression 與 entry queue validator，再處理下一個 entry。

目前 entry queue 漏掉 `ui/pages/09_data_import.py`，因 generator 只辨識常數 `title`，而該頁直接呼叫
`st.title(...)`。這是 Phase 0 inventory gap；修正 generator／queue 屬 production governance mutation，
必須列入獲核准的 exact write set，不能在本 proposed 文件中順便修改。

## 6. 與 UI 真實業務流程主計畫的整合方式

- React 不建立第二套 scenario catalog。Part 0～16 仍依原 dependency graph、root facts、fixed clock、
  fixture、expected、DB/API/UI oracle 與 receipt identity 執行。
- 每個 Part 增加 presentation applicability：`streamlit-required`、`react-required`、`dual-run-required`、
  `not-applicable` 或 `blocked`；不能把 React build pass 當成 Domain acceptance。
- Browser receipt 只證明 UI 可見互動；transaction、replay、rollback、worker／outbox 與 DB invariant
  仍由 pytest／專用 verifier 證明。
- 測試只連名稱與環境雙 allowlist 的 development／validation DB；依2026-08-21人工裁決，可直接使用既有
  `lu_test_*` DB與目前設定的credential（包括root），disposable DB為選配。LINE、銀行、付款、補助及外部傳送
  全部使用受控 adapter。
- Part 00 仍為 `blocked-for-implementation`；本計畫不授權修復 33 案、`115000051` drift、schema manifest、
  seed chain 或 validation DB。

### 6.1 逐頁精簡遷移模式（2026-08-17）

依已核准的逐頁精簡遷移裁決，本計畫的執行單位改為「一頁一個最小 Work Package」，而不是把所有頁面綁在單一中央前置 DAG：

1. 已有穩定 typed GET 的頁面，直接建立 bounded client／page adapter，保留既有 React component、Drawer、Tab 與 CSS，並做 page-level query 驗收。
2. raw 但穩定的 GET 只補該頁所需的最小 typed view／redaction contract；不把 raw dict 傳進 renderer，也不順便重構無關 Domain。
3. 缺少次要欄位、detail、timeline、recovery 或未核准 projection 的 slot，原位顯示 `unavailable`；同頁其他已接線區塊仍可完成驗收。
4. Preview／Apply／receipt、action handler、外部 provider、owner／transaction、schema／seed／migration 與 controlled-data Scenario 另立 bounded successor；query 接線不自動解鎖 mutation。
5. Part 00 的 Scenario／DB receipt 只在該 page slice 宣稱 mutation、controlled data、transaction、worker、external side effect 或跨站 Domain invariant 時成為必要 gate。既有 typed GET 的 real-data UI 接線仍需 success／empty／typed error／auth／timeout／abort／PII evidence，但不因無關 mutation 或 disposable DB engine 而阻塞。
6. Existing Global error、correlation 與 Scenario verifier 工作包照原範圍收尾；只有該頁實際依賴其 public contract 時才列為前置。舊 central DAG 與 B0～B9 只作 mutation／controlled-data／cross-cutting contract lane routing，不再是所有 query page 的總前置。
7. 2026-08-21人工已撤銷「既有DB只能GET」blanket restriction。已核准page slice可在allowlist `lu_test_*`
   development／validation DB執行受控mutation與建立／修復本次owned測試資料，並須保存唯一scenario identity、
   before/after readback、receipt及scoped cleanup／保留策略。這不授權schema／migration、全庫seed、reset、
   replacement、`--switch`、`union_db`或production target。

本節不改變各 Domain 的 SSOT、正式業務規則、既有 Work Package 的狀態或 exact approval；它只改變 page slice 的排程與 gate routing。

## 7. 分階段遷移與建議順序

### Phase 0：UI baseline 與 Mock → API mapping

- 核准 Desktop React 為 UI baseline，不再把視覺 inventory 當成待逐項重審的產品清單。
- 將 Desktop 11 頁完整 component tree 與工作區 React toolchain 做逐檔語意合併；不複製
  `node_modules`、stale `dist` 或 Desktop lockfile。
- 對每一頁建立精簡 mapping：`component/view field → current mock source → target API/client → adapter → status`。
- 每一頁以一個最小 page-slice Work Package 推進；已接線的 query 不等待其他頁完成，局部缺口只在原位標示 `unavailable` 或另立 bounded successor。
- status 只使用 `READY_TO_WIRE | ADAPTER_NEEDED | BACKEND_GAP | BUSINESS_EXCEPTION`。
- `READY_TO_WIRE` 與 `ADAPTER_NEEDED` 只在已有closed typed server contract時直接排入實作；
  `ADAPTER_NEEDED`僅表示presentation mapping未完成，不得用於raw dict／`Any`／未凍結public fields。
  raw public contract一律標`BACKEND_GAP`並先立backend hardening。
- 只有 `BACKEND_GAP` 與 `BUSINESS_EXCEPTION` 形成例外清單；例外需說明使用者可見影響與最小選項，
  不以架構術語要求使用者先設計畫面。
- 建立第一個 exact Work Package，不修改 production runtime。

### Phase 0 Exit Gate

Phase 0 只產生唯讀 inventory、disposition 與 proposed Work Package。下列必要 gate 全部 `PASS` 後，
才可申請 Phase 1 production code 授權；任一 `BLOCKED` 或 `NOT_RUN` 固定為
`REACT_PHASE_1_NOT_READY`。

| Gate | PASS 條件 |
|---|---|
| UI baseline | Desktop 11 頁、Login／Shell／Drawer／Modal／Tab 已保存，且確認原則為保留 UI、替換資料與 handler |
| Mock mapping | 每頁的集中 mock、內嵌資料與假 handler 已對應到 target client 或明確例外，不要求先裁決所有欄位語意 |
| API foundation | shared auth transport、runtime decoder、typed error、loading／empty／error pattern 有一份共用設計 |
| Exception isolation | `BACKEND_GAP`／`BUSINESS_EXCEPTION` 不阻塞同頁其他 `READY_TO_WIRE` 區塊；不可用假成功填補 |
| Compatibility | React 新入口與 Streamlit rollback 路徑、local proxy／same-origin 原則明確 |
| Work Package readiness | 第一波 exact paths、頁面、target endpoints、測試與 out-of-scope 明確 |

### Phase 1：完整模板合併＋API foundation

- 把 Desktop 的 11 頁、Login、Shell、Drawer 與 CSS 語意合併進工作區 `ui_react`，保持目前 UI。
- 實作 shared auth transport、runtime decoder、typed error、request cancellation 與 route shell。
- 在 Access Work Package 裁決並驗證 reload／new-tab session restore；不得用 localStorage／sessionStorage
  保存 bearer，也不得把現有 bearer-only `/refresh` 當成恢復機制。
- 集中 mock source behind adapters，讓每頁可以逐一由 mock adapter 切換成 real API adapter。
- 不在此階段重新設計業務畫面，也不刪除 Streamlit。

### Phase 2：Query real-data 接線

第一個 bounded slice 是 Phase 2A Orders／OrderTracker。其已於 2026-08-16 取得人工核准的
specification 與 exact Work Package：

- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase2a-orders-query-real-data-specification.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase2a-orders-query-real-data-work-package.md`

Phase 2A 曾完成local candidate，但2026-08-17 fresh audit發現source重新加入raw／未核准Orders routes與
permissive Zod，屬`live-drift`，不能再用舊receipt宣稱完成。新的React-only boundary remediation須先恢復
八個GET allowlist、strict decoder及unavailable slots；Contract Signing raw Query另列public contract gap。
7-stage、11-step動態狀態、order-scoped通知、三個獨立結清狀態、formal recommendation與emergency warning
仍是 contract gaps。Phase 2B兩條安全mutation亦已local驗證，但需要明確安全測試案件才能執行真browser
mutation。Phase 2C帳密challenge→TOTP→memory Session已完成真Chrome驗收。

- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase2a-orders-query-contract-boundary-remediation-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-contract-signing-public-query-redaction-contract-gap.md`

Phase 2D Anomalies／Import Warning Query 已核准並完成候選接線；原工作包的invalid freeze不回填假PASS，
而是於2026-08-17標為`superseded`，由Phase 2D-H contract hardening與Closure Amendment承接：

- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase2d-anomalies-query-specification.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase2d-anomalies-query-work-package.md`

Phase 2D只接canonical summary與field-level warning task兩個GET；raw detail/recovery與claim／resolve／transition
維持原位unavailable。Phase 2D-H候選已把severity改由Domain registry衍生，並將Anomalies／Recovery／
Import Warning public status收斂為封閉enum；前端decoder未放寬。

修復規格與 exact Work Package 已獲人工核准並執行；真Chrome兩個query family已完成Network→DOM。
Phase 2D-H工作包已依2026-08-17最新人工closeout裁決標記`completed`：

- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase2d-backend-public-contract-hardening-specification.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase2d-backend-public-contract-hardening-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase2d-h-closure-gate-amendment-work-package.md`

2026-08-17 closure amendment已取得exact核准並完成安全範圍內執行：`lu_test_*`連線前防呆、34個
focused backend、59個Phase 2D React及510個full React tests均通過；build PASS。使用者在真Chrome完成
帳密→TOTP後，兩個核准GET均200並進入DOM，Claim／Resolve維持disabled。使用者另明確選擇不建立
額外測試DB；因此engine gate記為`NOT_RUN（人工豁免）`而非PASS，且既有`union_db`不得用於mutation
測試。MasterLayout兩個lint warnings仍屬Shell owner debt；本closeout不自動授權Anomalies mutation。

- 優先把 Orders／OrderTracker、Staff、Scheduling、Anomalies、Import Warning、Data Browser、System
  Status、Audit／Jobs 的列表、詳情、drawer 與狀態資料換成 real API。
- LINE 同步完成 query-only surfaces：客服 tickets、identity bindings、delivery tasks、rich-menu／config
  snapshot、notification rules catalog、knowledge／FAQ items 與 order groups。route 回傳 raw contract者
  必須先完成backend public-contract hardening；不得只在bounded client自行猜schema或讓raw `dict`進component。
- Anomalies 除 registry／recovery 外，必須接 `import_warning_tracking.py` 的 task／referral query，讓匯入
  警告可被找到並導向處理；不得只顯示 DataImport Drawer 內的臨時 dirty rows。
- 保持 component props 與畫面結構；差異由 page adapter／view-model mapper 吸收。
- 每接完一頁即驗 loading、empty、error、reload、權限與 deep link，不等待其他頁完成。

### Phase 3：既有 action handler 接線

Phase 3 的 action handler 只處理已具備核准 command／Preview／Apply contract 的 mutation；純 query page slice 可依自身 typed GET 先行，不受本節 mutation predecessor 全域阻擋。

- 將既有 Drawer／Modal／button 的 local mutation、`alert()`、`confirm()` 逐一換成 API handler。
- 後端已有能力者直接接線；需要 request／response shape adapter 者在前端 bounded client 內轉換。
- 沒有 API 或業務明確衝突者只禁用該 action 並進例外清單，不阻塞整頁 real-data 上線。
- 接入 Anomalies claim／resolve／recovery navigation，以及 Import Warning transition Preview／Apply；
  Resolve 只代表人工處置狀態，不得冒充來源資料已修復。
- LINE 先接已有穩定 capability 的客服處理與 identity management；publication、delivery control、
  knowledge lifecycle 與 notification-rule mutation 留在 Phase 4。

Phase 3 已拆成可獨立核准、不可互相推定授權的兩個 proposed Work Package：

- **Phase 3A — LINE 客服結案與身分解除**：接 ticket/binding Query、Customer Service 結案
  Preview／Apply，以及 identity revocation Preview／Apply。Customer Service 現行 Apply 缺獨立 Preview，
  必須先完成 public-contract hardening；Rich Menu、delivery、rules、FAQ／Knowledge、groups、identity
  replacement／retry／manual override 不在本波。
- **Phase 3B — Staff／Scheduling 安全 actions**：接 matching preferences、不可服務期間、Staff
  retirement/reactivation、leave/substitution 四條獨立 Query／Preview／Apply flow。Staff master、holiday、
  custom rest、quick lock、leave intake 與 assignment plan 不在本波。

正式文件：

- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase3a-line-customer-service-identity-specification.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase3a-line-customer-service-identity-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase3b-staff-scheduling-safe-actions-specification.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase3b-staff-scheduling-safe-actions-work-package.md`

兩包已於2026-08-16取得 exact 人工核准。Phase3A已完成核准範圍的focused實作與驗證；2026-08-17 fresh
回歸為前端focused 8 files／53 tests、後端focused 44 tests及全量React 43 files／510 tests通過，build通過，
lint僅保留`MasterLayout.tsx`兩個既有Fast Refresh warnings。真browser仍缺有效volatile Session／controlled data，
因此Phase3A維持`blocked`。Phase3B在G1發現Staff selector、
typed error、occupancy mutex及Leave outer-UoW缺口後標為`blocked`，等待3B1修訂核准。各包先由 Luna 執行 read-only Contract Scout／Fresh Auditor；business
contract與production writer使用高能力模型，且只能在matrix freeze後依互斥write set施工。禁止使用
DDH作為任務、gate或驗收證據。

Phase3B1修訂：

- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3-scenario-lineage-governance-work-package.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase3-scenario-lineage-matrix.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-global-fastapi-typed-error-boundary-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase3b1-staff-contract-hardening-selector-amendment.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3b-q-h-scheduling-current-public-query-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3b2-leave-substitution-contract-outer-uow-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3b-q-r-scheduling-current-query-react-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3b2-r-leave-substitution-react-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3b-h-holiday-public-contract-uow-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3b-h-r-holiday-react-work-package.md`

2026-08-17 Phase 3 Scenario Lineage Governance已取得exact核准並完成metadata gate：8個scenario、
fixture/expected、Part 04／09／14 checklist與validator已落地，Integration Owner fresh重跑15 tests PASS。
Canonical verifier compatibility亦以51 tests完成。其最高輸出仍只為metadata-ready；Global Error Boundary
及Correlation Precedence Amendment已另以backend 72、React focused 69、full React 517 tests完成。3B1／
3B2的DB／browser mutation receipts仍須由各自工作包產生，不回捲阻擋獨立query page slice。

Phase3 production writer開工前，`phase3-scenario-lineage-matrix.md`中該family必須具備successor
scenario、fixture、expected、applicable oracle與fresh receipt路徑；缺任一項固定
`PHASE3_SCENARIO_LINEAGE_NOT_READY`。不得用component fixture、mock、截圖或舊evidence取代controlled
business data。Claim/Resolve與Data Browser source correction仍受人工裁決阻擋。

Global typed error boundary 是3B1、3B-Q-H、3B2與3B-H的hard prerequisite；不得在各route複製不一致的
401/403/422 envelope。3B2只負責Leave/Substitution typed impact與單一outer UoW，不能自行恢復`SchedulingPage`的舊local-state
操作；待backend契約凍結後由3B2-R接線。現行staff current-calendar雖有typed Query，但auth/error
boundary尚有live-drift，必須先完成3B-Q-H，再由3B-Q-R接到
甘特／日曆，不得以`MOCK_STAFF`、`MOCK_ORDERS`或前端buffer公式代替。Holiday固定採3B-H backend-first、
3B-H-R React-second。Phase5 Scheduling entry在3B1、3B2、3B-Q-R、3B2-R、3B-H、3B-H-R全部完成前
只能維持candidate，不得切換。

Phase 3D Anomalies claim／resolve／recovery與Import Warning transition仍受其各自public contract、outer-UoW及
affected-scope regression門禁阻擋；其他owner的full-suite失敗須揭露與交接但不得誘發Anomalies越界修正。
本次唯讀UI證據與人工DB豁免不得替代mutation engine evidence。2026-08-17已補上原先缺失的
Phase3D gap與backend-first exact successor：

- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3d-anomalies-warning-mutation-gap.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3d-anomalies-public-detail-hardening-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3d-r-anomaly-detail-react-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3d-claim-resolve-preview-policy-gap.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3d-warning-transition-receipt-hardening-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3d-w-r-warning-transition-react-work-package.md`

Claim／Resolve目前另有Global Preview契約與Anomalies直接短交易commands的矛盾；人工選Option A或B前，
相關控制維持disabled。Import Warning Apply目前重用Preview view，先由3D-W-H收斂terminal receipt/re-query，
再由已建立的3D-W-R React successor接線；兩包仍各自等待exact核准，存在文件不代表已施工。

### Phase 4：Import／Finance／LINE 等高副作用流程

Phase 4 僅對 upload／Apply／job／download／delivery／provider 等高副作用 slice 套用 Scenario／DB／transaction gate；同頁或同 workspace 的既有唯讀 GET 仍可依 page-slice 模式獨立接線。

- 保留現有 UI workbench，以既有 bounded API 完成 upload、Preview、Apply、job、download 與 delivery 接線。
- 第一個可能產生／阻擋 warning task 的 Import Apply 啟用前，Phase 2 的 Import Warning query 與 Phase 3
  的處置／修復導向必須已可用；否則該 Apply 保持 unavailable，不允許用前端「放行」alert 代替。
- LINE 明確涵蓋 notification rules Query／Preview／Save／Delete、rich-menu preview／publish／retry、
  delivery task control、knowledge／FAQ ingest／review／publish／retire／reindex，以及已存在 contract 的
  order-group action。缺少 create／cancel contract 的 action 只局部 unavailable。
- 只有 backend gap 或已退役行為另開 Work Package；不因既有後端存在而強制 React 保留它。

2026-08-17 fresh current-state matrix：
`document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-fresh-readiness-matrix.md`。
Phase 4 Scenario adoption／supplement／test-data gap由同目錄
`phase4-scenario-lineage-matrix.md`統一記錄；缺fixture、expected或fresh receipt lineage時不得啟動writer。
對應缺口與metadata-only執行包為
`PROV-20260817-react-admin-phase4-scenario-lineage-governance-gap.md`及
`PROV-20260817-react-admin-phase4-scenario-lineage-governance-work-package.md`；此包完成只代表lineage可追溯，
不代表任何Phase 4 production、DB、browser或provider操作獲准。
2026-08-21 prerequisite amendment已exact核准並完成，Phase4 lineage前置已收斂為
`PHASE3_SCENARIO_LINEAGE_METADATA_READY`，Durable Core／FI-H的Phase4前置則固定為
`PHASE4_SCENARIO_LINEAGE_METADATA_READY`。Global Typed Error不阻擋metadata建立，但仍是每個
Phase4 production writer的獨立硬前置；修訂不得被解讀為runtime解鎖。
此evidence確認HCM僅Preview、FinancePage仍mock-unsafe、LINE rules/menu僅query-only。尚未完成的Phase 4
backend／React successors仍為`proposed`，Phase 4B-S-H為`blocked`；HCM Preview與LINE rules／menu
Query雖已有local-validated成果，也不代表Apply／Mutation、真browser或entry cutover已ready。不能以既有route
或full React tests綠燈推定已核准。

2026-08-21 Finance FI-H已取得exact human approval，狀態為`approved / blocked-prerequisites`，並已補齊G0–G7與
Finance XLSX fixture authority。此核准只批准條件式範圍；Phase4尚未輸出
`PHASE4_SCENARIO_LINEAGE_METADATA_READY`，Durable Job Core／Caller Bridge與合法去識別Finance fixture及
合法Finance engine evidence亦未完成，故不得啟動writer；該evidence可依2026-08-21裁決使用既有allowlist
開發測試DB，不再強制non-root disposable DB。HCM不合成／不上傳測試XLSX與Finance fixture authority仍有效。

Phase 4 首波拆成 Phase 4A-P 與 Phase 4A-H。4A-P 已把 HCM current workbook 的真檔 Upload＋Preview
接入 React並完成local validation，Apply及其他import families原位鎖定；4A-H記錄workbook多重commit、Global typed error、
warning disposition與receipt observation缺口。只有4A-H successor與Phase3 warning處置門禁閉合後，
才可解鎖HCM Apply。正式文件：

- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase4a-hcm-current-preview-specification.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase4a-hcm-current-preview-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase4a-hcm-backend-transaction-receipt-gap.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-hcm-workbook-source-archive-decision-gap.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4a-hcm-apply-transaction-public-contract-work-package.md`

Phase4A-H successor採backend-first，推薦whole-workbook outer UoW與Source Archive Option A；這是privacy／
external-storage裁決，必須在exact核准文字中明示，不能由實作者以temp file替代。
後續React Apply另由`PROV-20260817-react-admin-phase4a-r-hcm-apply-react-work-package.md`承接，backend
未閉合前不啟用控制項。

2026-08-17對抗稽核補充：HCM仍有未受Preview保護的legacy`/workbooks/ingest` writer，Preview fingerprint
未涵蓋identity/mapping/root版本，archive也缺crash recovery；三個historical workbook family尚未逐一裁決
whole-workbook或row-atomic resumable；Finance Import的durable outcome保證超出原route/schema write set。
因此新增`PROV-20260817-case-import-workbook-atomicity-archive-policy-gap.md`與
`PROV-20260817-durable-job-public-outcome-contract-gap.md`作為強制前置，未關閉前不得派production writer。
Case Import可先核准docs-only
`PROV-20260817-case-import-workbook-policy-decision-work-package.md`。Durable Job fresh audit另證明現有repository
只依command identity判重且hidden commit；live inventory實為六個enqueue owner檔、八種command type，部分caller
會把duplicate直接當replay，因此新增
`PROV-20260817-durable-job-persistence-caller-adoption-decision-gap.md`；原
`PROV-20260817-durable-job-public-outcome-contract-work-package.md`改為`blocked`，必須先裁決
existing-column canonicalization或additive schema與caller adoption，不能直接核准局部backend施工。
對應docs-only決策包為
`PROV-20260817-durable-job-persistence-caller-adoption-decision-work-package.md`已於2026-08-21 exact核准Option A並完成
docs-only裁決；其`DECISION_COMPLETE_OPTION_A_CONDITIONAL`只代表架構與successor write set凍結，不代表MySQL
engine、Job runtime或任何Finance／Scheduling流程完成。下一個production successor仍須另行exact核准，固定為
`PROV-20260817-durable-job-core-persistence-worker-contract-work-package.md`；它只建立no-hidden-commit core port，
不切換caller。Core後先建立`PROV-20260817-durable-job-caller-integration-bridge-work-package.md`，再逐一完成
六個caller adoption：Assignment Plan、Finance Import三command types、Government Subsidy、Payroll Rebuild、
Staff Payout及Orders Auto Completion。Finance Import adoption併入4A-FI-H、Staff Payout adoption併入4B-SP-H，
避免同route平行競寫；其餘四個各有exact successor。六者全部PASS後才執行masked Public Outcome與React Jobs，
不得用單一Global test或`gap RESOLVED`字樣冒充完成。

Core同時必須把`api/dependencies/private_operations.py::run_durable_job_cycle`納入exact composition write set，
證明worker／runtime heartbeat的begin、commit、rollback與connection close owner；這個shared runtime path不得與
Phase6 launcher／monitor整合平行修改。

Phase 4B 財務稽核發現 Accounts Payable preview／export／archive 缺少 admin auth，preview 並公開完整銀行
帳號與身分證；Subsidy reconciliation 則仍是 raw dict、缺 auth／PII policy，且尚未證明由正式 Government
Subsidy root facts 產生。因此 FinancePage／ReportsPage 不直接接這些 route，先記錄兩個 successor gap：

- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase4b-accounts-payable-public-contract-gap.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260816-react-admin-phase4b-subsidy-reconciliation-public-contract-gap.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4b-ap-public-contract-hardening-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4b-subsidy-report-authority-hardening-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4b-ap-r-react-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4b-s-r-react-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-government-subsidy-reporting-authority-gap.md`

只有 AP auth／masked preview／binary metadata hardening 通過後，才可另立 React AP read/download slice；
補助報表必須先取得 typed authority。所有核銷、出款、退款、代墊 mutation 繼續原生 disabled。
AP採正式`require_admin`同權限政策；JSON只server-mask，完整法定資料只在授權XLSX；GET Export每次產生
安全唯一artifact，不宣稱idempotent。Client Finance mutation reason必須server trim後1–500字。
Staff Payout受Global durable-job typed outcome前置阻擋；Subsidy hardening目前為`blocked`，禁止照搬legacy SQL。
補助權威只由docs-only`PROV-20260817-government-subsidy-reporting-authority-decision-work-package.md`
先凍結，完成後仍須重新exact核准4B-S production包。

Phase 4C 只先開 notification rules catalog、Rich Menu configuration snapshot與publication history的四個
authenticated GET，由React client嚴格封閉raw route；schema drift fail closed，所有修改／發布／provider action
維持鎖定。Delivery tasks因raw payload暴露識別與provider資料、Knowledge FAQ因raw全文且Query會commit，
已分別建立public-query hardening gap，未完成前不得接React。Phase 4C-Q已完成本機query-only驗證：focused
5 files／12 tests與完整React 43 files／507 tests通過；尚未取得真browser controlled-data證據，不能作為
entry cutover完成證明。

2026-08-17已為Delivery與Knowledge建立backend-only exact successors：

- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4c-line-delivery-public-query-hardening-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4c-knowledge-public-query-hardening-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4c-d-r-react-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4c-k-r-react-work-package.md`

兩包只建立server-masked query；delivery controls、FAQ lifecycle與外部provider/index全部另案。
Knowledge catalog hardening不等於所有Knowledge read routes安全；item detail／jobs／indexes／questions的
敏感全文、URI、answer與runtime identity另記於
`PROV-20260817-knowledge-sensitive-detail-public-contract-gap.md`，React catalog禁止呼叫。

Phase 4C mutation successor另加防偷懶門：Rich Menu保存create/upload/link/switch/cleanup逐步ack receipt並驗證
lost-ack/crash/timeout續跑；Notification Rules禁止raw definition/Any穿透且manual replay維持獨立gap；
Knowledge lifecycle必須在query hardening完成後串行施工，source digest僅作server-side fingerprint，
root/audit/receipt/index-stale marker同一outer UoW，Chroma/reindex仍由index runtime policy gap管理。

Notification Rules backend successor已於2026-08-20完成local focused驗證：closed grammar、Preview零寫入、
dedicated Save／Delete、replay-before-stale與removed／disabled intent→delivery task同UoW cancellation為`29 passed`；
這只解除React mutation接線的backend prerequisite，browser/runtime receipt、manual replay、provider與entry cutover仍未完成。

### Phase 3E／4C：剩餘可見控制的契約收斂

2026-08-17 fresh UI-to-contract audit補出11個仍可見但尚未被前述波次完整承接的能力。此處不把
「後端有某個相似route」直接等同於UI READY：只有owner、根事實、public contract、outer UoW與exact write set
都已可證明者才建立Work Package；其餘建立gap並保持控制native disabled。

Orders／Staff／Reports七個gap：

- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3e-order-bootstrap-entry-gap.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3e-order-matching-formal-recommendation-gap.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3e-order-operational-timeline-gap.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3e-order-settlement-projections-gap.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-orders-emergency-contact-warning-contract-gap.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3c-staff-master-owner-gap.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4b-weekly-workbook-authority-gap.md`

其中正式推薦沿用人工裁決：通常只有一位月嫂；只有server證明單人無法覆蓋全部已確認日期時，
2–4位連續且無重疊的segments才可作為一個整體正式推薦。三個結清狀態保持三個owner projections，
不得出現前端合成的「全部完成」。緊急聯絡電話缺漏只顯示warning，不能阻擋媒合。

LINE三個exact mutation successors與一個owner gap：

- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4c-line-richmenu-publication-mutation-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4c-richmenu-mutation-react-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4c-line-notification-rules-mutation-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4c-notification-rules-mutation-react-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4c-knowledge-lifecycle-mutation-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4c-knowledge-lifecycle-react-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4c-line-order-group-mutation-owner-gap.md`

三條mutation均拆成backend-first與React successor。三個React包都會修改共享`LineManagementPage.tsx`，
因此backend/client lanes可在各自contract freeze後平行，但presentation只能由一位Integration Writer依序施工；
不得由三個模型同時修改頁面。Rich Menu backend已收斂為zero-write Preview、typed Apply/API與durable provider
step evidence／cleanup redrive；但DB engine gate仍`BLOCKED`且React successor尚未施工，因此UI控制不得冒充ready。
Rules整份PUT不能繞過Delete kill switch；Knowledge本波只含item lifecycle，不含reindex/provider。

另有三個共同前置gap：

- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-line-access-authorization-normalization-gap.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-line-knowledge-authorization-normalization-work-package.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-line-notification-manual-replay-contract-gap.md`
- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-knowledge-index-runtime-policy-gap.md`

第一項記錄live role/capability與正式「enabled users同業務權限、root只多Account Center」的漂移，第二項是
其exact production successor；該successor完成前，新的LINE／Knowledge mutation不得宣稱production auth契約
閉合。其餘兩項分別保護source-event replay lineage與production index artifact／rollback。缺口未關閉時，
相應React控制維持disabled。

### Phase 3～6 共用 Part 00 Scenario Gate

2026-08-17以後建立的 mutation／controlled-data backend、React與entry successor依其 page-slice mode 引用
`Part_00_全域測試資料治理與Scenario契約.md`，不得用writer自創fixture取代真實業務驗收。Query-only page slice
仍須做 typed query／UI evidence，但不因無關 mutation 的 Scenario／DB receipt 缺失而停止：

1. Mutation／controlled-data 開工前先選`existing scenario adoption`或`rebuild／supplement`，並保存source scenario/receipt→successor
   mapping；不得修改歷史receipt或複製canonical fixture建立競爭SSOT。
2. Mutation／controlled-data fixture必須是最小、版本化、synthetic/deidentified/invalid-by-design root/external input；禁止直接seed
   derived projection、receipt、outbox、alert或terminal狀態。
3. mutation scenario必須有fixed clock、command lineage、accepted/rejected/stale/replay/rollback與零partial-write
   oracle；query scenario至少有success/empty/typed error/auth/timeout/abort與PII oracle。
4. 每個可發布scenario都要連到`validation/scenarios/`、`fixtures/`、`expected/`及`receipts/`的canonical
   identity；auto-increment ID只能作observed identity。
5. Browser receipt只證明UI；DB/Domain invariant與transaction必須由pytest／專用verifier另證。UI success只以
   server receipt/re-query成立，不能用toast、HTTP 200或DOM文字替代。
6. UI execution mode只允許`browser-required`、`browser-file-dialog-assisted`、`browser-blocked`或
   `not-applicable`；各Work Package frontmatter已明列，不得由實作者降級。
7. validation database必須通過environment/database allowlist，禁止fallback到production或未識別本機DB；
   secret與完整個資不得進command、fixture、log或receipt。

任一scenario lineage、fixture安全或oracle缺失只能標`test-data-gap`／`blocked`，不能把程式測試全綠升格為
published或entry ready。

Phase 3～6的backend→React→entry→runtime→retirement依賴與shared-hotspot唯一writer規則，集中記錄於
`document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/work-package-dependency-matrix.md`；
該matrix是planning evidence，不取代個別exact approval。

### Phase 5：逐 entry cutover

- 每次只切一個 entry 的 navigation；保留 Streamlit rollback。
- 通過觀測、focused regression 與 queue validator 後，才處理下一 entry。
- 2026-08-17 的READY 0／PARTIAL 4／BLOCKED 6與「queue漏Data Import／React entries」是Phase5A前歷史基線，
  已由2026-08-20 Phase5A completion evidence取代，不再作current blocker。各業務entry仍須自己的readiness、
  forward-written-data與observation evidence，不能因inventory完成而視為cutover-ready。
- Phase5A歷史Entry治理／rollback基線已完成：10個Streamlit、14個React identities、11筆fixed rollback mapping；
  `#line-ai-events/#line-liff-studio/#line-security`三筆drift維持`review_required`。Phase5B exact Windows
  smoke run `7f0d10991ed8daf8`已PASS，8000／8501／5173 ready、GET-only與owned cleanup均成立；Unix runtime
  仍`NOT_RUN`，且foundation PASS本身不等於可切任一業務entry。
  Option A entry-target control plane successor先完成11-entry historical baseline；其後System Status exact successor
  已新增dedicated `#system-status`並完成registry v2。Current inventory為10個Streamlit、15個React identities、12筆
  fixed rollback mapping；12-entry initial state仍全為Streamlit且尚未provision，未切任何runtime target。三個LINE drift
  identity維持`review_required`且不納入control plane。
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase5a-entry-governance-rollback-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation-work-package.md`
- Phase5B固定為最小dual-run foundation：API 8000、Streamlit 8501、React 5173、relative `/api`、
  strict ports、owned PID cleanup與GET-only smoke。smoke期間monitor／workers／delivery consumers／providers
  全部關閉，不保存Private Operations observation、不建立LINE alert intent，也不要求或建立test DB；
  existing DB只允許health與已核准GET，不得送出mutation。
- Phase5A/B後第一批entry依序為System Status→Anomalies Query→Orders Query→LINE Query；四個proposed
  per-entry工作包已建立。System Status的dedicated`#system-status`已拆成獨立identity amendment，必須先完成
  source witnesses再執行candidate evidence；Orders明確是一個Streamlit entry對
  `#orders`與`#order-tracker`兩個React identities。所有candidate包把Phase5A及System Status successor manifest視為
  唯讀凍結輸入；
  queue/readiness/evidence只由Integration Owner串行回寫，其他lane不得競寫。

  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase5-system-status-entry-identity-amendment-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase5-entry-cutover-system-status-query-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase5-entry-cutover-anomalies-query-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase5-entry-cutover-orders-query-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase5-entry-cutover-line-query-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase5-entry-cutover-data-browser-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase5-entry-cutover-scheduling-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase5-entry-cutover-finance-workspaces-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase5-entry-cutover-form-management-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase5-entry-cutover-access-management-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase5-entry-cutover-data-import-workspaces-work-package.md`

  所有per-entry包的G0已改為exact prerequisite identities，不再接受`Phase5A/B completed`等模糊文字。
  Orders另須Phase2A boundary remediation PASS；Access須依Account Center→Audit→Durable Job串行閉合；
  所有包另須Global Typed Error Boundary及適用runtime prerequisites fresh PASS；Phase3／Phase4 Scenario Lineage
  只要求對應`PHASE3_SCENARIO_LINEAGE_METADATA_READY`／`PHASE4_SCENARIO_LINEAGE_METADATA_READY`。Metadata-ready
  不解除per-entry runtime、DB、browser或switch gate。Navigation真的切換時，除了Navigation Switch Decision外，還必須另立且核准該entry的exact
  runtime switch successor；candidate包本身永遠沒有切換權。

- Fresh audit發現上述per-entry包只擁有readiness tests／queue／evidence，沒有真正切換單一entry navigation的
  runtime owner；queue status不是router。已建立shared policy gap與docs-only決策包，推薦Option A canonical
  admin entry map。此缺口關閉前，per-entry包最高只能標`candidate`，不能宣稱navigation cutover：
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase5-entry-navigation-switch-policy-gap.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase5-entry-navigation-switch-decision-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase5-entry-navigation-switch-production-gap.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase5-per-entry-switch-template.md`

  已建立的`entry-cutover-*` identities因已有inbound references不改名，但其交付上限已明訂為
  `query-candidate`／`readiness-candidate`；任何宣稱`cutover`、`replacement`或`active`均為驗收失敗。
  Runtime switch另分`local-dual-run`與`production-same-origin`：前者只可在5173做rehearsal；後者必須等
  Phase6B-HOST/RUN與immutable artifact獨立release approval後才可產生production switch receipt。

- 後六個entry全數仍為readiness／partial candidate：Data Browser缺typed query successor；Scheduling須完成
  3B1／3B2／3B-Q-R／3B2-R及Holiday backend／React兩段；Finance/Data Import是一對多workspace；Access缺Account public contract；Form Management
  沒有對等React identity/page。不得因hash route、build或局部query存在而跳過這些門。
- Data Browser與Holiday的backend前置已收斂為proposed exact successors；generic source-correction另列政策缺口，
  在人工裁決前維持disabled：
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3d-db-query-public-contract-hardening-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3d-data-browser-part-identity-gap.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3d-data-browser-part-identity-decision-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3d-db-source-correction-policy-gap.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3b-h-holiday-public-contract-uow-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3d-db-r-react-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3b-h-r-holiday-react-work-package.md`
- Data Import／Finance後續不能用generic client；已按bounded owner建立四個backend successor：
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4a-case-workbooks-public-contract-hardening-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4a-finance-import-public-contract-hardening-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4b-client-finance-public-contract-hardening-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4b-staff-payout-public-contract-hardening-work-package.md`
- 上述backend gates完成後的React successors亦已分開；bounded clients可平行，`DataImportPage.tsx`／
  `FinancePage.tsx`各只能有一位Integration Writer：
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4a-cw-r-case-workbooks-react-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4a-fi-r-finance-import-react-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4b-cf-r-client-finance-react-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase4b-sp-r-staff-payout-react-work-package.md`
- Access已有正式sole-root owner；Account Management仍需依序完成Account Center、masked Audit與Durable Job
  observability，MFA self-service另案，不能用登入完成冒充整頁完成。Form Management仍須先裁決五個bounded
  owners與dedicated identity，不能直接施工：
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-access-account-center-public-contract-hardening-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-access-audit-public-query-hardening-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3c-access-audit-react-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-durable-job-public-outcome-contract-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase3c-durable-job-observability-react-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-form-template-catalog-owner-public-contract-gap.md`

### Phase 6：Streamlit 最終退役

- 最後一個 entry 的退役、launcher 移除、default route、monitor、deployment artifact 與 rollback
  需要獨立人工 cutover／release 核准。
- UI-only rollback 只切回已驗證 Streamlit artifact，不回滾 API、schema 或 Domain data。
- 2026-08-17 impact audit確認Streamlit仍由runtime registry、launcher/monitor、既有migration rehearsal、
  Python dependencies、current docs與tests共同持有；搜尋得到211個候選引用，但歷史evidence不是刪除目標。
- Phase6拆成：6A fail-closed release gate、6B-HOST production artifact/hosting、6B-RUN runtime callers接管、
  6C逐entry source retirement。
  production hosting缺口已由核准的6B-HOST successor取代；source retirement缺口仍保留。未滿足Phase5及
  各自release前置不得施工。
- Phase6A唯讀validator已在exact核准後提前安裝，安裝結果為`VALIDATOR_INSTALLED_NOT_READY`且
  current release結果必須輸出`PHASE6_NOT_READY`；它同時驗
  10個legacy identities、Phase5A minimum 11個React baseline及其後所有已核准identity amendments所形成的
  latest exact registry，連同完整API／CLI／UI queue、receipt provenance、React→Streamlit→React雙向
  forward-data、production hosting與source manifest，不能用grep零命中或測試綠冒充退役完成。
  每個legacy entry另須production-same-origin switch receipt與closed observation receipt：signed manifest
  current target為React、previous target為Streamlit、one-entry CAS/audit、switch-back rehearsal皆成立；
  candidate/readiness evidence或docs-only switch decision不能替代。
  requirements與source inventory必須由不同producer產生並共用同一registry revision；同人同次自我驗證
  固定`INDEPENDENT_MANIFEST_MISMATCH`。HOST/RUN另須machine-readable release approval receipts，不能用
  implementation tests或文字PASS替代。
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6-retirement-release-gate-work-package.md`
- Phase6B-HOST exact WP已核准，採FastAPI同源`/admin/`掛載immutable React artifact；hash routes與
  root-relative`/api`保持，並要求manifest/digest、CSP/cache、真TOTP browser及current/previous artifact
  rollback。manifest必須allowlist全部served files；private artifact-health只證明active mounted artifact，
  previous由HOST本機selector驗證。fresh Phase5B Windows prerequisite與HOST G0–G7含真Chrome已PASS；這仍
  不等於部署、traffic switch或entry retirement。
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6b-production-hosting-work-package.md`
- Phase6B-RUN是獨立最小successor，只接管local launcher／preflight／smoke／monitor對HOST frozen typed
  artifact health的兩個獨立read-only probes；不接管ngrok、migration rehearsal、DB observation、alert intent
  或provider。HOST與RUN不得互相冒充驗收。RUN保留Streamlit 8501與entry-specific rollback，rehearsal只切
  current／previous artifact selector，不回滾Domain data、API或DB。
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6b-runtime-integration-work-package.md`
- Phase6C final dependency cleanup不得預先用glob建立刪除包；已建立
  `PROV-20260817-react-admin-phase6c-final-streamlit-dependency-cleanup-gap.md`，只在10個per-entry retirement、
  Phase6A PASS、Phase6B-HOST/RUN release與rollback retention全部閉合後late-bind exact paths。
- 每個legacy source必須依
  `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6c-per-entry-retirement-template.md`
  分別建立一個future exact WP；模板要求dynamic caller、forward-written-data、previous artifact、觀測期、
  restore trigger與test disposition，不允許`ui/**`／`tests/**`glob或以grep零命中直接刪除。Rollback retention
  使用closed states；只有`expired_approved`且`retention_end <= BusinessClock`與release-owner deletion approval
  都成立後，才可進G7A removal authority；G7B必須先在隔離candidate移除exact bytes並跑完整回歸，PASS後
  才可正式移除。候選失敗不得更新queue、retention或正式source。
- Fresh Phase6C inventory結果為`READY 0 / GAP 10`，已集中記錄逐entry blockers與future provisional identity；
  不得把此backlog自動轉成刪除授權：
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6c-per-entry-retirement-readiness-gap.md`
- Fresh retirement audit另發現三個gate amendments與一個sequencing decision：validator installation與release
  readiness必須分開、artifact health歸Private Operations typed owner、6B-RUN必須依賴fresh Phase5B receipt，
  且逐entry退役不得由模型自行挑選或平行：
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6a-validator-installation-gate-amendment-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6b-artifact-health-private-contract-amendment-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6b-run-phase5b-prerequisite-amendment-work-package.md`
  - `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-phase6c-entry-retirement-sequencing-decision-work-package.md`

## 8. Current readiness matrix

| Capability | Status | Current evidence／gap |
|---|---|---|
| Desktop visual shell | `implemented-mixed-baseline` | 11頁、Login、Shell、Drawer已合併；部分頁已真接線、其餘mock/unavailable，須逐entry以current source驗證 |
| Desktop UI surface inventory | `completed-read-only` | 11 頁、Login、Shell、17 Drawers、Modal／Tab／二級操作已保存於 `2026-08-16_react_admin_ui_surface_inventory.md`；不構成產品或實作授權 |
| Mock → API mapping | `partial` | 頁面與後端能力已完成初步對照；下游實作者需按本節 matrix 建立 adapter，不需先重審整個 UI |
| Workspace React toolchain | `implemented-foundation` | React 19／TS6／Vite8／oxlint、Vitest 與 Hash shell 已存在；頁面採 lazy chunks |
| Access/session browser contract | `implemented-local-verified` | 真 Chrome 已完成 password challenge → TOTP → memory Session；reload/new-tab依人工選擇仍需重新登入 |
| Runtime response validation | `implemented-foundation` | shared transport、typed errors 與 Zod decoder 已建立；各 Domain client 仍需逐波新增 schema |
| Bounded API clients | `partial / live-drift` | Auth、Anomalies、HCM Preview、LINE客服／Identity及LINE Rules／Rich Menu Query已建立；Orders Query目前違反八GET allowlist，等待Phase2A remediation |
| System Status read-only slice | `implemented-static-current` | 較早真Chrome證據只涵蓋Shell performance snapshot；新dedicated `#system-status` identity已通過static／component gate，但其browser/API runtime因DB recovery維持NOT_RUN；未代表entry cutover |
| HCM Import結果／問題檢查 | `page-slice-rebaseline` | 人工裁決不以合成／真xlsx Preview作遷移gate；頁面改顯示本次新增訂單與問題／warning tasks，Apply仍另案 |
| Accounts Payable preview／download | `blocked-public-contract` | Phase4B-AP-H backend exact successor已proposed；等待人工核准與auth/masking/binary metadata驗證 |
| Subsidy reconciliation report | `blocked-public-contract` | Phase4B-S authority/backend exact successor已proposed；公式/root-fact不明時必須fail closed |
| LINE Rules／Rich Menu Query | `completed-local-validated-query-only` | 四個authenticated GET已strict decode並接既有六-tab頁；full React 507 tests通過，所有publish/save/retry仍鎖定 |
| LINE Delivery／Knowledge FAQ | `blocked-public-contract` | 兩個backend query-only exact successors已proposed；等待人工核准，mutation仍另案 |
| Entry inventory | `completed-foundation-with-drift` | 10個Streamlit與15個React identities已盤點；12筆具fixed rollback，3筆LINE drift維持review_required |
| Dual-run browser acceptance | `windows-foundation-validated` | exact Windows 8000／8501／5173 GET-only smoke與owned cleanup PASS；Unix runtime NOT_RUN，entry rollback仍逐包驗證 |
| Launcher／monitor／CORS | `phase5b-completed-phase6b-run-in-progress` | dual-run launcher、HOST probes及12-entry provision/zero-write attest tooling已完成；queue structural drift已解除，RUN仍受deployment-owned state未實際provision阻擋 |
| UI scenario catalog integration | `partial` | 本規格先定義 UI 接線驗收；涉及測試資料／DB oracle 的 Part 仍受原主計畫 gate 約束 |
| Streamlit retirement | `blocked` | replacement evidence、逐 entry 裁決、cutover／rollback 均不存在 |
| Phase 5 entry cutover | `foundation-completed / no-entry-switched` | Phase5A與Option A control-plane installed-only完成；Phase5B Windows exact smoke fresh PASS，仍未切任何entry |
| Phase 6 retirement gate | `host-validated / run-static-pass-activation-blocked / not-ready` | HOST G1–G7含真實Chrome及fresh focused 28 PASS；Phase5B fresh Windows smoke已PASS；RUN core/rehearsal與fresh focused 2 PASS，queue 557/557、3 PASS。Option C focused與System Status exact 12-entry control plane均完成；runtime provisioning tooling final 41 PASS，但deployment state仍未建立。validator維持PHASE6_NOT_READY，switch／retirement未完成 |

### 8.1 下游實作者的逐頁接線矩陣

本矩陣是實作 routing table，不是重新設計清單。下游模型預設保留現有 component tree、CSS、Drawer、
Tab 與文案；先在 page adapter 內把 server DTO 轉成現有 view model。只有「局部例外」欄位需要另案，
不得因一個按鈕缺 API 而阻塞整頁真資料。

| React surface | Real-data owner／現有 API 起點 | 預設實作 | 局部例外 |
|---|---|---|---|
| Login／Shell | `admin_auth.py`、`system_status.py`、`runtime_health.py` | 真 login／me／refresh／logout、principal、health、notification count adapter | 假 TOTP、remember、forgot password 不接成真功能；沒有正式 contract 時隱藏或標示 unavailable |
| Orders | 核准的Orders typed GET allowlist | 先以單一Orders query page-slice移除未核准candidate/matching/lifecycle/contract-signing calls與前端日期／結清推導 | Service Dates／Reopen及其他Preview／Apply各自mutation包；不得用mutation receipt證明query完成 |
| OrderTracker | 清理後的Orders query client | Orders完成後再做Tracker page-slice；保留7階段／11步／通知槽位 | 沒有server lineage時一律unavailable；禁止生成SOP完成狀態、固定LINE history或由order_status猜stage |
| Scheduling | `staff/summaries`＋`scheduling_current.py` | Staff Query Page-Slice完成後，Scheduling Query Page-Slice只接directory selector與current-calendar | Leave／Availability／Holiday／Matching全部維持disabled／unavailable，由各自mutation包承接 |
| Staff | `GET /api/v1/staff/summaries` | Staff Query Page-Slice只接id/name/phone與名冊／Drawer摘要 | Staff master、證照、銀行、偏好、Availability、Lifecycle槽位原位unavailable／disabled，不阻塞名冊 |
| DataImport | HCM import batch/result＋Import Warning tasks | 顯示本次新增訂單、失敗／warning rows與檢查導向；既有Preview可保留但不是cutover gate | Apply／Correction／Reprocess仍屬Phase4高副作用包；不得用合成xlsx browser流程冒充業務驗收 |
| Finance | receipt reconciliation、staff payable、AP及named reports的各bounded view | FinancePage依AP→Client Finance→Staff Payables→Finance Import串行整合，同一時間唯一page writer | 全部local settled／paid、XLSX及四個假mutation先移除／disabled；不得一次把五tab冒充完成 |
| Anomalies | anomaly summaries、warning tasks及typed detail/referral GET | list/tasks query已真Chrome驗收；下一個同頁query slice只補detail/referral Drawer | Claim／Resolve／Recovery／Warning transition全部獨立mutation，Resolve不得冒充根因已修復 |
| LINE | customer service、identity management、rich menu、tasks、notification rules、knowledge routes | 六個tab保留；Phase3接客服／identity，Phase4依auth normalization→backend hardening→React successor串行 | raw task/rule/knowledge contract必須先backend hardening，不得只做adapter；order-group create/release仍是policy gap |
| DataBrowser | `GET /api/v1/admin/data-browser/{table}` | 同頁最小hardening先凍結React source id↔backend allowlist、pagination與server-masked typed row，再接tabs/search/Drawer | 現有raw rows、source名稱不一致與clipboard alert不可直接搬；source-correction mutation另案，PATCH 410不恢復 |
| Reports | subsidy quarterly／annual GET | 先補同頁最小auth、typed redacted view再接可證明的報表；weekly兩slot原位unavailable | 現有raw dict／PII與假XLSX下載不可接；沒有單一三-sheet workbook contract，不以mock填滿 |
| Account | Account Center、masked Audit Query、Durable Job public outcome、current session routes | shared page依Account Center→Audit→Jobs串行接線 | MFA enrollment/self-service另案；未有typed contract的控制原位unavailable，禁止明文secret與fake jobs |

### 8.2 Adapter contract

每一頁至少有一個 page-level query adapter；每一個 mutation family 有獨立 bounded client。adapter 必須：

1. 接收 API 的 runtime-validated typed result，不使用 TypeScript assertion 假裝驗證。
2. 將 server view 映射成現有 component props；component 不知道 endpoint、token 或 raw envelope。
3. 統一處理 loading、empty、typed error、abort、stale response 與重新整理。
4. mutation 只以 server result／receipt 更新畫面；不得先改 local business state 再顯示成功。
5. 缺 API 時回傳明確 `unavailable` presentation state，不用 mock fallback 冒充 real data。
6. 同一頁可以同時有已接線與 unavailable 區塊；例外不阻塞其他資料顯示。

## 9. 下游實作 Work Package 的 proposed write set

本文件只提供 handoff 規格，不執行下列變更。下游模型開始實作前，應在最新 base 建立 exact-scope
Work Package，並依頁面波次從此集合選取最小 write set：

### In scope

- `ui_react/package.json`
- `ui_react/package-lock.json`
- `ui_react/vite.config.ts`
- `ui_react/src/App.tsx`
- `ui_react/src/main.tsx`
- `ui_react/src/components/`：整合 Desktop 現有 shell、drawer 與 route guard；不得重新設計已接受 UI。
- `ui_react/src/api/`：shared transport、runtime decoder、access session client 及逐 bounded domain clients。
- `ui_react/src/adapters/`：API DTO → 現有 page／component view model mapping。
- `ui_react/src/pages/LoginPage.*`
- `ui_react/src/pages/`：按單一波次選取頁面，將 mock import／local static data／fake handler 換成 adapter。
- `ui_react/src/styles/` 及必要共用 CSS。
- `ui_react/src/**/*.test.ts(x)`、`ui_react/e2e/` 及前端測試設定。
- 對應正式規格、entry inventory、focused evidence 與 operator documentation。

### Conditional／requires separate confirmation

- `api/main.py` 的 local development origin／same-origin static asset wiring。
- 既有 Access／System Status route 或 schema：只有 current contract 無法承載已核准 browser client 時才提案，
  不在第一包預設修改。
- `scripts/launchers/`、monitor、smoke tests：只新增並行 React dev entry，不移除 Streamlit。
- entry queue generator／queue：只補 Phase 1 React entry 與既有 `09_data_import.py` discovery gap。

### 規格階段 Out of scope

- 本輪所有 production code、tests、launcher、API、schema／migration、seed、DB、部署、cutover、Git
  stage／commit／push。
- 未經 bounded exception 核准，不修改現有 UI layout、interaction hierarchy 或業務文案。

## 10. 下游實作 acceptance 與 failure model

1. 現有 11 頁、Login、Shell、Drawer／Modal／Tab 的視覺與主要 interaction hierarchy 保留；改動 UI
   必須連結 bounded exception，不得以「接 API 比較方便」重畫。
2. React build、typecheck、lint、unit／component tests 通過；每個新增／修改 source 有一份合規檔頭。
3. 每個已遷移頁面的正常畫面不再 import `mockData.ts`、不讀內嵌正式樣本、不以亂數生成 fingerprint，
   且成功訊息可追溯到 server result／receipt。
4. 未登入、invalid、expired、revoked、disabled session 均不能看到 business view。
5. token 不出現在 URL、storage、console、DOM、error、snapshot 或 build artifact；logout 呼叫正式 revoke。
6. schema 不符、未知 error envelope、timeout、abort 與較舊 response 都 fail closed，且不覆蓋新 view。
7. local Vite 只經核准 proxy／origin 呼叫 FastAPI；production 不因開發方便擴張 wildcard CORS。
8. `BACKEND_GAP`／`BUSINESS_EXCEPTION` 只讓對應區塊呈現 unavailable；同頁已可接線區塊仍正常運作。
9. Streamlit 仍可由原 launcher 使用；React failure 可切回 Streamlit，Domain data 不需 rollback。
10. 不使用假 TOTP、硬編碼 health／identity、generic import endpoint 或 local business formula。
11. Browser reload／new tab 必須依核准的 Access 決策驗收：recommended cookie 方案要能恢復 principal、
    維持 absolute expiry、撤銷與 CSRF／Origin 防護；若人工選擇重新登入方案，必須清楚回登入頁，且
    不得以現有 bearer-only `/refresh` 假裝恢復成功。
12. 每波驗收至少包含：真 API 成功、empty、typed failure、401／403、timeout／abort、stale response，
    mutation 另含 double submit／server reject／receipt reload。

## 11. 下游模型 handoff 指令

1. 先讀 Desktop React 與本規格，不重新發明 navigation、頁面或 Drawer。
2. 先建立 page adapter seam，再替換 mock source；避免 component 直接散落 `fetch()`。
3. 每一波最多處理一個頁面族與其共用 client，提供 before／after mock-removal inventory。
4. 後端已有 route 不代表必須保留；若接入後無法符合現有業務，回報 `BUSINESS_EXCEPTION`，不要在
   React 中繞過或硬配。
5. 缺 API 時回報 `BACKEND_GAP`：包含畫面位置、使用者原本可做什麼、缺少的最小 request／result、
   以及暫時隱藏或 disabled 的行為。不要要求使用者先理解 Domain／Badge／projection 術語。
6. 實作成果交回後，人工與本代理一起驗收畫面是否仍符合 Desktop baseline、資料是否真實、操作是否
   只由 server result 宣告成功；規格階段不預先展開所有微觀狀態討論。
7. Streamlit 退役、API public contract 修改、backend replacement、schema、資料 migration、production
   external side effect 與部署仍各自需要獨立核准。

## 12. DB change gate

| Gate | Status | Evidence／reason |
|---|---|---|
| Scope gate | `BLOCKED` | UI 主計畫與 Part 00 明確未授權 schema、seed 或 validation DB mutation |
| Change inventory | `NOT_RUN` | 本提案沒有 DB write set |
| Static release gate | `NOT_RUN` | 未建立 migration release |
| Descriptor gate | `NOT_RUN` | 未變更 schema object |
| Read-only plan gate | `NOT_RUN` | 本提案不執行 DB tooling |
| Engine verification gate | `NOT_RUN` | 不以 React 遷移擴張成 DB 驗證或 mutation |
| Developer acceptance gate | `NOT_RUN` | 未操作任何 developer／validation／production DB |

總結：`DB_CHANGE_NOT_READY`。React 遷移必須維持 UI-only rollback；若後續任一 slice 發現 schema
缺口，另立 schema Work Package 並重新執行全部 DB gate。
