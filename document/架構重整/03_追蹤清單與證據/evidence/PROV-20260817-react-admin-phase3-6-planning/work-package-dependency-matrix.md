# React 管理端 Phase 3～6 Work Package dependency matrix

> Planning evidence only。所有列仍受各自`declared_status`與exact approval約束；本表不是施工授權。

## 0. Page-slice routing override（2026-08-17）

本表引用的 canonical routing decision 為
`document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-page-slice-migration-execution-decision.md`。
本節優先解釋本 matrix 的依賴範圍：

- **Query-only lane**：既有 typed GET 或該頁最小 typed view 可按 page-specific Work Package 直接接線；只需該頁的 auth、schema、adapter、success／empty／typed error／timeout／abort／PII 與 UI evidence。它不等待無關的 Scenario／DB engine、mutation、provider 或其他 page predecessor。
- **Mutation／controlled-data lane**：Preview／Apply／receipt、transaction／worker、external provider、controlled data 與跨站 invariant 才進入下列 central DAG，並依各自 exact Work Package 的 Scenario／DB／browser gate 執行。
- **混合頁面**：query slot 與 mutation slot 分開判定；一個 disabled 或未閉合的 action 不得阻塞同頁已通過的 GET。缺少次要欄位維持原 slot `unavailable`。
- **既有 DB**：只允許 GET UI 觀察；不得用 `union_db` 或任何既有業務 DB 執行 mutation、seed、migration、repair 或建立 controlled data。

因此，下方 central predecessor waves、shared-hotspot 與 Phase 3～6 gates 保留作 mutation／controlled-data／cross-cutting public contract routing，不再是所有 React query page 的中央施工前置。此 routing 變更不刪除、不重算任何歷史 Work Package 或 receipt。

## 1. 人工決策節點

| Decision | Recommended／choices | 只阻擋 |
|---|---|---|
| Anomaly Claim/Resolve policy | A short-transaction exception；或B Preview→Apply | Claim/Resolve mutation，不阻擋typed detail query |
| HCM source archive | Option A required archive before DB write（recommended）；或B正式改spec | 4A-H Apply，不阻擋HCM Preview |
| Data Browser source correction | A retire generic routes（recommended）；或B owning-domain commands | correction mutation，不阻擋masked query |
| Form Management owner/identity | 五塊分owner＋dedicated/one-to-many React identity | Form production successor/retirement；不阻擋Orders typed context |
| Case workbooks atomicity | 每family whole-workbook或explicit row-atomic partial | CW-H Apply contract，不阻擋410 HCM Historical |
| Finance/Reports subsidy owner | Reports presentation vs Finance workspace | Phase5 Finance full replacement；不阻擋各自bounded queries |
| New Order entry semantics | 一般人工建單或只允許source intake/bootstrap recovery | `orders.create`；不阻擋既有Orders Query |
| Matching formal recommendation | 單人優先；server證明無法覆蓋時2–4段為一個package | Matching mutation；不阻擋Scheduling Query |
| Orders operational timeline | 7-stage／11-step／case delivery每slot owner與lineage | Tracker read model；缺少者保持unavailable |
| Three settlement projections | 三owner projections，禁止aggregate completed | Orders settlement presentation only |
| Staff master owner | profile／PII／certificate／bank分離owner | Staff create/edit；不阻擋summary/preferences |
| Staff remaining controls | `end_pause` effective semantics與preference definition administration owner | 對應兩個React/Admin mutations；不阻擋3B1已凍結三flow |
| Leave request date/case coverage | request interval是否約束outcome日期、是否可跨case | 額外date/coverage rejection；不阻擋3B2既有state/version/staff/unique-link原子修復 |
| Weekly workbook authority | 三sheet欄位、公式、期間、artifact owner | Generic export；不阻擋named AP/subsidy reports |
| LINE order-group provider capability | 自動create是否真被provider支持；或人工evidence流程 | Order-group mutation；不阻擋typed query |
| LINE/Knowledge authorization normalization | enabled users同業務權限；root只多Account Center | 所有新LINE/Knowledge mutation的production auth完成宣稱 |
| Notification manual replay | source-event lineage與新delivery intent/replay receipt | manual replay；不阻擋rule Save/Delete |
| Knowledge index runtime | immutable artifact、atomic switch、rollback、provider target | reindex/retry；不阻擋item lifecycle |
| Contract Signing public Query | signing/delivery/document metadata、download auth/redaction | Contract Drawer real-data；Phase2A先顯示unavailable |

## 2. Mutation／controlled-data backend predecessor waves（central DAG）

Phase3任一 mutation／controlled-data writer 前先要求`PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS`，
並由`phase3-scenario-lineage-matrix.md`驗證對應successor scenario/fixture/expected/checklist存在。
這是該 mutation slice 的 metadata/test-data gate，不是 query-only page 的全域施工前置，也不是 production 或 DB 授權。

| Wave | Work Packages | Parallel rule | Default owner |
|---|---|---|---|
| B0 Validation + Global API boundary | Phase3 Scenario Lineage Governance → Global FastAPI Typed Error Boundary | 必須先串行完成；Global包唯一修改`api/main.py`、shared transport與password challenge input schema，期間不得與Auth或Phase5/6 shared writer平行；其他route不得各自發明401/403/422 envelope | Luna metadata/tests → Primary contract/integration |
| B1 Scheduling | 3B1 Staff amendment；3B-Q-H Current Query hardening；3B2 Leave UoW；3B-H Holiday | 3B1／3B2／3B-H mutation lanes依B0與各自前置串行；3B-Q-H若是query-only可依自身typed contract獨立執行，只有修改shared error boundary時才回到B0；transaction hotspots不得平行競寫 | Terra bounded tests＋Primary contract/UoW |
| B2 Anomalies/Data Browser | Phase2D-H Closure Gate Amendment → 3D-H detail→3D-R；3D-W-H warning receipt→3D-W-R；3D-DB-H→3D-DB-R | 3D-W-H／Claim／Resolve等mutation依Closure、Scenario與Global Error gate；3D-H／3D-DB-H query-only可依自身redacted typed view獨立執行；backend paths不重疊可平行，`AnomaliesPage`固定3D-R→3D-W-R串行 | Luna verification＋Terra＋Primary |
| B3 Imports | Phase4 Scenario Lineage → 4A-H HCM；4A-CW-H three families；Durable Core＋Bridge → 4A-FI-H（同包完成Finance三command caller adoption） | 所有包先過Global Error Boundary；HCM/CW archive policy未決不得施工；FI-H不得與另立caller writer競寫route；Public Outcome在六caller後 | Terra＋Primary |
| B4 Finance | 4B-AP-H；4B-S-H；4B-CF-H；Durable Core＋Bridge → 4B-SP-H（同包完成Staff Payout caller adoption） | CF-H／SP-H可與AP-H並行；AP-H與S-H共同修改`api/routes/finance_reports.py`，必須串行；`15`/`16`正式規格Primary | Terra＋Primary |
| B5 LINE/Access | Authorization Normalization → 4C-D-H／4C-K-H／Access Account Center | normalization先閉合四live roles、unknown/local-bypass與admin/public route matrix；Knowledge只凍結current guarded caller allowlist；其後paths不重疊可平行，provider永不在測試中真發送 | Primary contract → Terra＋Primary |
| B6 Remaining visible controls | RM-H；NR-H；KL-H backend-first | backend paths不重疊可平行；真provider rollout不在本wave | Terra writers＋Primary contract |
| B7 Orders remediation | Phase2A Query Boundary Remediation；Contract Signing保持gap | React-only回歸修復先完成；不改Phase2B mutation/backend | Primary integration |
| B8 Access observability | Account Center → Audit-H/R → Durable Job Global/R | backend contracts可先平行盤點；`AccountManagementPage.tsx`只可依固定次序串行 | Primary contract＋Terra clients |
| B9 Durable Jobs | Option A docs decision → Core Persistence/Worker → Caller Integration Bridge → six adoption owners（Assignment；FI-H；Subsidy；Payroll；SP-H；Orders Auto）→ masked Public Outcome → React client | Option A先裁決case-insensitive MySQL key、lowercase contract、JSON number/actor equality；Core只擁有queue lifecycle UoW，不宣稱Domain handler原子；其後Core/Bridge串行，四個獨立caller可依write set平行，FI-H/SP-H由各bounded包唯一擁有，Public Outcome不得先於六者 | Primary contract/UoW → Terra bounded callers |
| R6 LINE mutations | RM-R；NR-R；KL-R React successors | clients可平行；`LineManagementPage.tsx`三包必須串行 | Terra clients＋Primary page integration |

`LineManagementPage.tsx`的canonical presentation merge順序固定為：既有Phase4C-Q → D-R Delivery secondary
view → K-R masked FAQ catalog → RM-R Rich Menu publication → NR-R Notification Rules mutation → KL-R Knowledge
lifecycle。每一步開始前fresh-read前一步diff／tests；後一步不得平行修改page/CSS/no-fake test。Knowledge
KL-H必須在K-H query hardening完成且base freeze後才可施工，兩者共享backend paths亦不得平行。

Orders bootstrap/matching/timeline/settlement/emergency、Staff master、weekly workbook及LINE order-group目前仍為gap，
未取得owner/public-contract裁決前不得加入production wave。

Durable Core另唯一擁有`api/dependencies/private_operations.py`中的durable worker composition小節，用來證明
transaction／heartbeat／connection ownership；不得與Phase6 runtime writer平行。Knowledge／LINE／monitor composition
在該包保持不變，Phase6開始前必須fresh-read Core receipt與diff。

## 3. React successor waves

| Shared hot spot | Bounded clients/adapters | Integration rule |
|---|---|---|
| `SchedulingPage.tsx` | 3B1 Staff/Availability/Lifecycle、3B-Q-H→3B-Q-R Current Query、3B2-R Leave、3B-H-R Holiday | bounded clients/tests可平行；presentation固定依3B-Q-R → 3B2-R → 3B-H-R串行，page只有一位Primary/指定Presentation Writer；3B1 staff directory不得重做 |
| `AnomaliesPage.tsx` | detail/recovery、warning transition、未來Claim/Resolve | query與warning clients可平行；page串行 |
| `DataBrowserPage.tsx` | masked query only | source correction仍disabled |
| `DataImportPage.tsx` | HCM、BeClass、Staff Historical、Historical Orders、Finance Import | 每family client可平行；page唯一writer固定串行HCM-R → CW-R → FI-R，逐包交接fresh base receipt；HCM Historical維持410 |
| `FinancePage.tsx` | AP、Client Finance、Staff Payout、Finance Import facts | bounded clients可平行；presentation固定AP-R→CF-R→SP-R→FI-R串行；JobAccepted不等於terminal success |
| `ReportsPage.tsx` | Subsidy named reports；generic weekly仍gap | AP留在FinancePage；Subsidy authority由Primary裁決 |
| `LineManagementPage.tsx` | Customer Service、Identity、Rules/Menu、Delivery、Knowledge | clients可平行；六-tab page單一writer；所有provider mutation需獨立gate |
| `AccountManagementPage.tsx` | Account Center、Audit、Jobs、MFA self-service | presentation固定Account Center→Audit React→Jobs React串行；MFA self-service另案；secret/root policy由Primary驗收 |

## 4. Entry/runtime/release strict order

```text
Phase 5A inventory foundation may run after Global + Scenario governance
  → canonical 10 Streamlit + React identities + rollback URLs (no cutover)
  → all required bounded backend + React successors
  → Phase 2A Orders Query boundary remediation PASS
  → Phase 5B controlled 8000/8501/5173 dual-run
  → Phase 5 navigation-switch policy decision
  → separately approved Phase 5 navigation-switch production successor
  → one Phase 5 entry readiness candidate at a time (frozen manifest read-only)
  → Phase 6B-HOST immutable production React artifact/release
  → Phase 6B-RUN launcher/monitor typed artifact-health probes + artifact-selector rehearsal
  → one separately approved production-same-origin per-entry runtime switch successor
  → Phase 6A validator installation may be VALIDATOR_INSTALLED_NOT_READY
  → independent requirements/source-inventory producers validate latest released target
  → Phase 6A PHASE6_READY_FOR_ENTRY_RETIREMENT
  → one Phase 6C legacy entry G7A authority → G7B candidate removal → post-removal regression at a time
  → rollback retention expires
  → Phase 6A PHASE6_READY_FOR_FINAL_DEPENDENCY_CLEANUP
  → final Streamlit dependency cleanup exact WP
```

Phase6A validator可提早建立，installation receipt固定為`VALIDATOR_INSTALLED_NOT_READY`；只有執行release-gate
evaluation時，在上述條件閉合前才固定回`PHASE6_NOT_READY`。兩個狀態不得混用。

Phase5A baseline固定是10個Streamlit runtime identities＋11個React baseline routes；`#staff`只作Scheduling
deep-link，`#system-status`需另經identity amendment後才可能成為第12個React identity，Form Management目前
沒有replacement。這些差異必須由independent manifest表達，不得以數量相等或queue自我生成expected掩蓋。

## 5. Shared files：唯一 Integration Writer

- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- `document/架構重整/01_規格基線/05_Staff_Payables_Export_Domain.md`
- `document/架構重整/01_規格基線/09_Finance_Import_Domain.md`
- `document/架構重整/01_規格基線/14_Government_Subsidy_Domain.md`
- `document/架構重整/01_規格基線/16_Staff_Payables與Client_Refund正式規格.md`
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md`
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md`
- `document/架構重整/01_規格基線/01_Orders_Domain.md`（Assignment、Case Workbook、Orders Auto Completion
  依各包順序串行）
- `document/架構重整/01_規格基線/19_Global_Entry_Point_Governance.md`（Phase5A → navigation switch／
  System Status amendment → Phase6C；Integration Writer only）
- `document/架構重整/02_決策與退役執行記錄/README.md`
- `document/功能開發計畫/React管理端遷移與UI真實業務流程驗收計畫.md`
- `document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl`
- `validation/scenarios/react_admin_entrypoints.json`
- Phase5 readiness matrix、Phase6 source/artifact manifests
- `ui_react/src/App.tsx`、`MasterLayout.tsx`、shared transport/Auth、package/lockfiles（Global Error Boundary先於其餘Auth/Phase5/6 writer串行）
- launcher、monitor、`api/main.py`
- `tests/test_entrypoint_review_queue.py`（Phase5A → System Status amendment → Phase6B-RUN串行）
- `scripts/launcher_preflight.py`、local launchers、monitor與smoke tests（Phase5B → Phase6B-RUN串行）
- `scripts/validate_streamlit_retirement_readiness.py`及retirement tests（Phase6A validator amendment先建立，
  Phase6A release gate只消費／補強；不得平行競寫）
- Phase6A requirements由Contract/Integration Owner freeze，`retirement-source-inventory.json`由不同的
  Independent Inventory Owner產生；兩者共同`registry_revision`但不得同人同次自我驗證。
- `api/dependencies/jobs.py`（Durable Caller Integration Bridge → masked Public Outcome串行）

各bounded lane可平行產出不重疊的內容檔與精確index delta；上述正式規格、README、index、scenario
catalog與evidence summary只由唯一Integration Writer在所有相關lane freeze且fresh-read後一次整合。

Luna只做inventory、scans、simple disjoint tests/docs consistency；Terra只做已凍結bounded clients/adapters/
non-overlapping tests；Primary處理正式business decision、public contract、state machine、shared files與final gates。

## 6. Universal anti-fake completion gates

- 每個Phase 4 writer啟動前，Integration Writer必須先核對同目錄
  `phase4-scenario-lineage-matrix.md`及machine manifest的15個coverage records；`TEST_DATA_GAP`或缺
  fixture／expected／receipt lineage時不得施工。
- Writer自己的fixture/test不能是唯一contract evidence；必須可追到Pydantic/Domain/Part00 scenario。
- `build/lint/unit/HTTP 200/screenshot/queue status`皆不能單獨證明browser、transaction、forward-data或retirement。
- Unavailable slot不得隱藏、用mock填滿或由前端推導。
- Browser receipt不證明DB/UoW；disposable MySQL receipt不證明真UI。
- shared page／queue／index競寫、base drift、write-set外改動、真provider side effect皆fail closed。
- `LineManagementPage.tsx`三個mutation successor不得同時施工；backend/client freeze後仍由同一Integration Writer依序接頁。
- 正式推薦、SOP、三結清、緊急聯絡warning、weekly report不得由React的日期/金額/狀態公式補洞。

DB Gate：本matrix為文件，Scope PASS、Change inventory PASS（0 DB change），其餘NOT_RUN；
`DB_CHANGE_NOT_READY`。

## 7. Planning-only exact approval queue

下列文字只列出可執行順序，不代表已取得核准；每一包仍須人工逐字核准其exact scope：

Mutation／controlled-data 前置治理必須先串行；query-only page slice 不因下列中央工作未完成而停止：
   - `核准此 exact Phase 2D-H Closure Gate Amendment Work Package`；只補`lu_test_*`安全門與fresh evidence，
     production 0 write，其他owner的full-suite debt不得被刪除。
   - `核准此 exact Phase 3 Scenario Lineage Governance Work Package`（已完成；輸出僅
     `PHASE3_SCENARIO_LINEAGE_METADATA_READY`）
   - Phase3 canonical verifier compatibility已exact核准並完成；51 tests，輸出
     `PHASE3_CANONICAL_VERIFIER_COMPATIBILITY_READY`。
   - Global Error與Correlation Precedence Amendment均已exact核准並完成；backend 72、React focused 69、
     full React 517 tests通過。
   - `核准此 exact Phase 4 Scenario Lineage Governance Work Package`可在其prerequisite amendment通過後執行；
     Global boundary前置已完成。Query-only page slice仍依自身最小contract判定，不等待Phase4 metadata。
   - 上一條的`Phase3 lineage PASS`存在metadata/runtime語意衝突；proposed
     `PROV-20260817-react-admin-phase4-scenario-lineage-governance-prerequisite-amendment`核准前，Phase4 metadata
     writer維持blocked。核准後只以`PHASE3_SCENARIO_LINEAGE_METADATA_READY`解除metadata前置，不解除Global或
     任何bounded runtime gate。
   - Phase2D Query Browser Closure已由Phase2D-H真Chrome evidence承接並標`superseded`；Phase3A mutation
     browser closure仍須另行核准：`核准此 exact Phase 3A Browser Closure Work Package`。

Query-only page slice 的 exact approval 只需列該頁 GET／最小 typed view、adapter、UI evidence 與
unavailable slots；不得把上述 mutation／controlled-data approval queue複製成每頁的無條件前置。若同一頁
同時含 mutation，query與mutation仍分別記錄，不能用query完成替代mutation receipt。

2026-08-17 execution note：Phase 2D-H Closure amendment已核准並完成安全防呆、fresh regression與真Chrome G6；
兩個核准GET均200且進入DOM，Claim／Resolve維持disabled。使用者明確選擇不建立額外測試DB，故原包與
amendment依人工closeout標記`completed`；engine gate維持`NOT_RUN`且不是PASS。此結果不提供Phase 3D
mutation的transaction／engine evidence，後續mutation仍受其各自工作包門禁。
Phase 3 Scenario Lineage Governance亦已核准並以15個validator tests完成metadata gate；輸出固定為
`PHASE3_SCENARIO_LINEAGE_METADATA_READY`，不等於任何bounded runtime、DB或browser PASS。
0. 任何Phase5 Orders evidence前先恢復Phase2A boundary：
   - `核准此 exact Phase 2A Orders Query Contract Boundary Remediation Work Package`
   - Contract Signing維持`PROV-20260817-contract-signing-public-query-redaction-contract-gap`，人工裁決前不接raw GET。
   - Data Browser scenario／browser驗收前另先：
     `核准此 exact Data Browser UI Part Identity Decision Work Package，並採用 Option A`；canonical Part編號
     由Integration Owner fresh catalog盤點後late-bind。
1. Scheduling mutation backend可在write set不重疊時平行；Scheduling current query可依page-specific package先行：
   - 逐頁query最短序列：`核准此 exact Phase 3 Staff Query Page-Slice Work Package` →
     `核准此 exact React Scheduling Query Page-Slice Work Package`；前者唯一擁有staff directory client與
     `api/routes/staff.py`，後者只重用，兩者均不解鎖mutation。
   - `核准此 exact Phase 3B1 Amendment`
   - 舊3B-Q-H／3B-Q-R已標`superseded`，不得再核准；其query scope由上列Scheduling Page-Slice承接。
   - 3B1 fresh PASS後可平行：`核准此 exact Phase 3B2 Leave/Substitution public contract and outer-UoW Work Package`
   - `核准此 exact Phase 3B-H Holiday Work Package`
2. 對應backend contract freeze後，Scheduling presentation依序施工：
   - Scheduling query已改由單一Page-Slice處理；本段只保留後續mutation presentation。
   - `核准此 exact Phase 3B2-R Leave/Substitution React Work Package`
   - `核准此 exact Phase 3B-H-R Work Package`
2A. Anomalies／Data Browser的mutation依各自backend-first序列施工；query-only detail／masked view可依自身typed contract先行：
   - query page-slice可直接核准：`核准此 exact React Anomalies Query Page-Slice Work Package`。
   - `核准此 exact Phase 3D-H Work Package` → `核准此 exact Phase 3D-R Work Package`
   - `核准此 exact Phase 3D-W-H Work Package` →
     `核准此 exact Phase 3D-W-R Import Warning Transition React Work Package`
   - `核准此 exact Data Browser UI Part Identity Decision Work Package，並採用 Option A` →
     `核准此 exact Phase 3D-DB-H Work Package` → `核准此 exact Phase 3D-DB-R Work Package`
   - Claim／Resolve與source-correction仍是policy gaps，不得被上述query／Warning packages暗中解鎖。
2B. 其餘逐頁query／preview-only最短包：
   - 舊HCM Preview page-slice已依人工裁決`superseded`；改核准：
     `核准此 exact React HCM Import Result Review Page-Slice Work Package`。
   - `核准此 exact React Orders Query Page-Slice Work Package`（只OrdersPage；OrderTracker另包）。
   - `核准此 exact React Order Tracker Query Page-Slice Work Package`（已核准施工）。
   - `核准此 exact React Data Browser Query Page-Slice Work Package，並採用 Option A`。
   - `核准此 exact React Finance Query Page-Slice Work Package`。
   - `核准此 exact React Reports Query Page-Slice Work Package`。
3. 新的LINE／Knowledge public contracts或mutation開始前：
   - `核准此 exact LINE / Knowledge Authorization Normalization Work Package`
   - normalization PASS後：`核准此 exact Phase 4C-D Work Package` →
     `核准此 exact Phase 4C-D-R Work Package`
   - normalization PASS後：`核准此 exact Phase 4C-K Work Package` →
     `核准此 exact Phase 4C-K-R Work Package`
   - `核准此 exact Phase 4C-RM-H Work Package` → `核准此 exact Phase 4C-RM-R Work Package`
   - `核准此 exact Phase 4C-NR-H Work Package` → `核准此 exact Phase 4C-NR-R Work Package`
   - `核准此 exact Phase 4C-KL-H Work Package` → `核准此 exact Phase 4C-KL-R Work Package`
   - 所有React successors仍依`LineManagementPage.tsx`唯一writer固定順序串行。
4. Import／Finance backend successors開始前，先裁決共同前置：
   - `核准此 exact Case Import Workbook Policy Decision Work Package，並採用本文推薦值`
   - `核准此 exact Durable Job Persistence / Caller Adoption Decision Work Package，採用 Option A`
   - Durable Option A與Phase4 Scenario Lineage均PASS且未要求DB successor後：
     `核准此 exact Durable Job Core Persistence / Worker Contract Work Package`
   - Core與Global Boundary PASS後：`核准此 exact Durable Job Caller Integration Bridge Work Package`
   - Bridge後依exact write set核准四個獨立caller：
     `核准此 exact Assignment Plan Durable Job Caller Adoption Work Package`、
     `核准此 exact Government Subsidy Durable Job Caller Adoption Work Package`、
     `核准此 exact Payroll Rebuild Durable Job Caller Adoption Work Package`、
     `核准此 exact Orders Auto Completion Durable Job Caller Adoption Work Package`；Finance Import三種command
     與Staff Payout分別由4A-FI-H／4B-SP-H唯一擁有，不另開平行caller writer。
   - 六owner adoption全部fresh PASS後才可：
     `核准此 exact Durable Job Public Outcome Contract Work Package`；目前`blocked`，不得提前核准施工。
   - `核准此 exact Government Subsidy Reporting Authority Decision Work Package`
   - Access shared page另依序核准：`核准此 exact Access Account Center Public Contract Work Package` →
     `核准此 exact Access Audit Public Query Hardening Work Package` →
     `核准此 exact Phase 3C Access Audit React Work Package` → Durable Job決策與successor PASS後
     `核准此 exact Phase 3C Durable Job Observability React Work Package`。
5. Phase5A是inventory／rollback foundation，可在Global＋Scenario治理PASS後先核准；所有bounded replacement
   只在entry candidate／switch前必須成熟。foundation完成仍不等於entry cutover：
   - `核准此 exact Phase 5A Work Package`
   - `核准此 exact Phase 5B Work Package`
   - `核准此 exact Phase 5 Entry Navigation Switch Decision Work Package，並採用 Option A`
6. Phase 6可先核准read-only validator installation，但不得把installation當release ready；原獨立修訂已
   被canonical Phase6A spec／WP吸收並標`superseded`：
   - `核准此 exact Phase 6A Work Package`
7. Phase6B-HOST／RUN開始前依序核准：
   - `核准此 exact Phase 6B Work Package`
   - `核准此 exact Phase 6B-RUN Work Package`
   原Artifact Health與RUN Phase5B prerequisite修訂均已被canonical HOST／RUN吸收並標`superseded`，
   不得再次核准或作為平行owner。
8. 第一個source retirement package提出前：
   - `核准此 exact Phase 6C Entry Retirement Sequencing Decision Work Package，並採用 Option A`

Import／Finance一律backend successor先於React successor；同一共享`DataImportPage.tsx`、`FinancePage.tsx`或
`ReportsPage.tsx`一次只能有一位Presentation Writer。未核准、前置未完成或contract未freeze時，只允許read-only
inventory／tests discovery，不得把`unavailable`、mock fixture或HTTP 200冒充完成。

`DataImportPage.tsx`的presentation整合固定串行為HCM-R → Case Workbook-R → Finance Import-R；不得只寫
「sole writer」而讓三包同時啟動。每一包須以fresh base receipt交給下一包。
