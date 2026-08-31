---
doc_type: gap-register
declared_status: in-progress
date: 2026-08-31
owner: architecture-governance / product-and-domain-owners
priority_authority_date: 2026-08-31
---

# Current 剩餘代辦任務總表

> 本表是 Task 96 未完成業務工作的唯一 current register。2026-08-31 最新人工裁決已把 Anomalies 產品原則收斂為：只保留實際可發生且發生後需要人處理的業務異常；純系統公式、deterministic projection／aggregate、transaction invariant、migration integrity、正常來源先後、automatic retry／replay或temporary readback failure不建立 runtime recovery product。
>
> 本次文件修正不自動授權 production／`union_db`、provider、deployment、entry switch、configured DB Apply或destructive cleanup。既有完成 evidence、舊 Work Package與歷史 addenda只作證據，不再複製到current register。

## 1. Current Authority／scope

Task 96維持 active。正式業務語意由`01_規格基線`擁有；本表只路由未完成工作。

狀態只使用`proposed | approved | in-progress | blocked | completed | superseded`。局部 source／test PASS不得冒充runtime、DB、Browser或external acceptance。

2026-08-31 anomaly reachability裁決 supersede較早「15 current issues／13 owner prerequisite contracts」要求：

- runtime Anomalies exact target只剩`GOVSUB-007`、`LINE-006`；
- `BECLASS-001`改為Case Import／Client owner follow-up，不進`#anomalies`；
- `PAYOUT-002`、`GOVSUB-001`～`GOVSUB-005`、`IMPORT-003`、`IMPORT-006`、`SCHEDULE-002`、`SCHEDULE-003`、`SCHEDULE-006`、`LINE-004`退出runtime anomaly；
- 退役碼的正常owner validation、focused tests、transaction guard、migration readback仍保留，但不得建立第二套manual recovery framework。

Canonical anomaly規格：`../01_規格基線/06_Anomalies_Domain.md`。
Current anomaly計畫：`../../功能開發計畫/PROV-20260829-current-state-anomaly-slimming-execution-plan.md`。

## 2. Current 執行順序

2026-08-30既有主鏈仍保留序列dependency，但Stage 3／4依2026-08-31產品裁決縮小：

1. **Local DB 1003→current**：完成開發DB ordered upgrade／resume／preserve-data／normal startup；不得以fresh reset、SQLite、mock、`union_db`或production替代。
2. **LINE backend prerequisites**：完成M1～M4目前仍屬Task 96的owner backend gate。`LINE-006`既有owner readback／delivery evidence保留，但需按最新裁決把predicate縮到「automatic path已無法繼續且需要人工」。
3. **唯一剩餘 anomaly owner gap**：`GOVSUB-007`保留為真實可達的外部超額政府退款；Government Subsidy必須有最小正式人工disposition boundary。原`CUR-ANOMALY-OWNER-BACKEND-PREREQUISITES-01`的13-code要求superseded。
4. **Anomalies closure**：registry／typed union／API／React／recheck exact set只保留`GOVSUB-007`與縮限後`LINE-006`；`BECLASS-001`移owner follow-up，12個退役碼零runtime producer／public definition／React current mapping。
5. **其他既有Task 96 lanes**：依本表current priority繼續；所有功能terminal後才做`CUR-UI-STITCH-UNIFICATION-01`。

前一stage因external／DB Authority blocked時，不得把後一stage runtime標為terminal；但已明確授權且不依賴該external effect的repository-local規格／source工作，仍依各自current Authority判斷，不由本表額外擴權。

| 順序 | Lane | Current IDs | Current terminal gate |
|---:|---|---|---|
| 1 | Local DB 1003→current | `CUR-LOCAL-DB-1003-CURRENT-01`、`CUR-LOCAL-DB-PORTABILITY` | ordered release chain、resume、preserve-data、normal startup有fresh合法`lu_test_*` evidence |
| 2 | LINE backend | `CUR-LINE-MODULES-1-4-CLOSURE-01` | M1～M4 current requirements terminal；`LINE-006` transient／retry-only狀態不再產生business issue |
| 3 | Government real anomaly owner | `CUR-ANOMALY-OWNER-BACKEND-PREREQUISITES-01`（縮限） | 只剩`GOVSUB-007`最小owner manual disposition；不補其餘12碼recovery contracts |
| 4 | Anomalies product closure | `CUR-P0-ANOMALY-RECOVERY-01` | runtime exact 2-code set＋`BECLASS-001` owner follow-up＋12碼runtime absence＋fresh removal oracle |
| 5 | 其他Task 96 lanes | 本表其餘active IDs | 各自canonical acceptance |

## 3. Current 未完成執行清單

| ID | 優先級 | 狀態 | Owner／正式規格 | Current scope | 下一個material gate |
|---|---:|---|---|---|---|
| `CUR-LOCAL-DB-1003-CURRENT-01` | S1 | `blocked` / `BLOCKED_DB_TEST_ENV` | Global Migration／`10`、`18` | current release chain已超過1003；需在合法localhost `lu_test_*`完成ordered upgrade／resume／preserve-data／normal startup | 提供具project dependencies、`APP_ENV=development`與明確`lu_test_*` identity的MySQL環境後重跑current chain |
| `CUR-LOCAL-DB-PORTABILITY` | S1 | `blocked` / `BLOCKED_DB_TEST_ENV` | Global Migration／`10` §4.5 | target不得綁特定host／reference DB；每台機器Apply前仍需release-scoped dump／receipt與row evidence | 與上一列同一合法環境完成launcher dry-run、read-only plan、Apply／resume與readback |
| `CUR-LINE-MODULES-1-4-CLOSURE-01` | S2 | `in-progress` / repository-local evidence preserved / `DB_CHANGE_NOT_READY` | LINE／Access／`17`、`20`、`23`、`26` | M1 role-scoped identity、M2 deterministic backend、M3 workbench／recipient、M4 ops與既有`LINE-006` readback成果保留；最新裁決只改`LINE-006` business predicate，不重做已完成owner work | 移除`LINE-006` pending／processing／retryable／readback-only false-positive；DB／provider/runtime acceptance仍依原gate |
| `CUR-ANOMALY-OWNER-BACKEND-PREREQUISITES-01` | S3 | `in-progress` / `SCOPE_REDUCED_TO_GOVSUB007` | Government Subsidy／`06`、`14` | 原13-code prerequisite superseded。只保留`GOVSUB-007`：實際government refund outgoing超過existing payable remaining時需要human disposition | 固定最小owner Query／Preview／Apply或既有合法owner command，使fresh readback能證明超額處置terminal；不得擴張成generic government recovery framework |
| `CUR-P0-ANOMALY-RECOVERY-01` | S4 | `in-progress` / `PRODUCT_SCOPE_REVISED_2_CODES` | Anomalies／`06` | exact current set=`GOVSUB-007`,`LINE-006`。`BECLASS-001`移Case Import owner follow-up。12碼退出runtime anomaly；不再要求15-code terminal matrix | future source execution只做2-code registry／typed union／API／React與recheck alignment；12碼零runtime producer／mapping；predicate false＋complete後row delete |
| `CUR-P0-HISTORICAL-PAYMENT-SETTLEMENT-01` | P0 | `in-progress` / `OWNER_UI_LOCAL_PASS` / `DB_CHANGE_NOT_READY` | Finance Import／Client Finance／Staff Payables；`04`、`05`、`16` | pre-system historical case的owner-specific`paid | settled`保持owner work item，不屬current anomaly pruning | 合法`lu_test_*`完成read-only plan／fresh／preserve-data／developer acceptance |
| `CUR-CONTRACT-01` | P0 | `in-progress` | Contract Signing／LINE；`21` | external signing successor DB gate已ready；仍缺enabled persisted-human Chrome正向chain | 完成unsigned PDF download→completion reports→final PDF Preview／Apply→receipt／metadata／storage readback |
| `CUR-FILE-NAS-01` | P0 | `in-progress` | Global controlled files／`00`、`17`、`18`、`20`、`21` | typed storage contract與local DB qualification已有證據；真NAS／production不在本包 | enabled-human Session fresh Chrome正向list／download |
| `CUR-LIFF-PROFILE-01` | P0 | `approved` / `CLIENT_CONTRACT_READY` / `BOUNDARY_REQUIRED_PUBLIC_API` / `DB_CHANGE_NOT_READY` | Client／LINE；`20` §6.1、`23` | 第一階段只做Client；不擴張Staff | 另行public endpoint Authority仍是material boundary；不得旁路到LINE legacy route |
| `CUR-LINE-RICHMENU-01` | P-after-S4 | `blocked` | LINE Rich Menu／Media；`17`、`20` | provider qualification不插隊主鏈 | Stage 4後依合法publication lineage做Browser／provider qualification |
| `CUR-CONTRACT-FULL-PREVIEW-01` | P1 | `in-progress` / `OWNER_SOURCE_GAPS_REMAIN` / `BOUNDARY_REQUIRED` | Contract／Orders／Scheduling／Finance／Payables；`21` | template mapping已編譯；部分owner typed facts與public preview entry仍缺 | 只補仍無current owner source的material cells與public-entry boundary，不重算公式 |
| `CUR-LINE-RICHMENU-AUTH-01` | P-after-S4 | `blocked` | Access／LINE Rich Menu；`17`、`25` | authenticated user與source tests已有；provider execution後置 | Stage 4後以enabled Session完成queue→worker→sandbox receipt／readback |
| `CUR-UX-01` | P1 | `in-progress` | Global UX／各owner；`00`、`12`、`15` | presentation slices local evidence保留；Anomalies UI目標改成2碼，不再維護15-code current presentation | runtime恢復後完成remaining responsive／keyboard／WCAG與owner語意對照 |
| `CUR-UI-01` | P2 | `approved` | React presentation；`12` | 功能收斂後逐頁視覺／responsive／WCAG對齊 | 依保留設計做fresh Chrome comparison |
| `CUR-PERF-01` | P2 | `blocked` / `BLOCKED_RUNTIME_BENCH_ENV` | Global／React；`12` | 無可重跑API／React／DB runtime，不建立假baseline | runtime可用後量測同環境before／after |
| `CUR-INTERNAL-UI-UNMASKED-01` | P3 | `approved` | Global UX／Access／各owner；`12`、`15`、`25` | authenticated enabled內部UI顯示owner Query完整一般業務值；不擴張secret/raw evidence | 依current priority分批盤點／驗收 |
| `CUR-UI-STITCH-UNIFICATION-01` | P-last | `proposed` / `SPEC_GAP` | Global UX／React | 只在全部前順位功能terminal後啟動 | terminal後重新收斂surface inventory與design adoption |

## 4. 已授權但仍受外部／執行 gate 約束

下列既有Task 96 Authority保持原意；本次anomaly裁決不擴張也不撤銷它們：

| ID | 狀態 | Current gate |
|---|---|---|
| `CUR-LIFF-E2E` | `approved` | DB release chain與verified-token環境就緒後驗收 |
| `CUR-LINE-PROVIDER` | `approved` | 每次執行前回讀exact environment／target／recipient／quota／worker isolation；production recipient不在blanket approval |
| `CUR-LINE-BABYLOG-MEDIA-01` | `approved` | 依賴受控NAS staging／digest／cleanup／readback |
| `CUR-LINE-AI-FEEDBACK-01` | `approved` | 先有正式feedback owner contract；不得用browser-local counter假造 |
| `CUR-LINE-QA` | `approved` | workbook只作review input；逐題answer仍需owner review才publish |
| `CUR-CLOUD-01` | `approved` | external deployment前仍需exact project／operator／budget／rollback scope |
| `CUR-RETIRE-01` | `approved` | production entry switch／不可逆retirement仍需exact target與rollback gate |

## 5. Anomaly pruning acceptance

Task 96的Anomalies lane不再以「完整15-code matrix」為terminal。最低充分 acceptance固定為：

1. current runtime registry exact set=`{GOVSUB-007, LINE-006}`；
2. `LINE-006`只有automatic path耗盡／無法合法繼續且需要人處理才active；pending／processing／retryable／readback incomplete本身不產生新issue；
3. `GOVSUB-007`只由actual outgoing government refund超過existing payable remaining產生；
4. `BECLASS-001`只在Case Import／Client owner follow-up顯示；
5. `PAYOUT-002`、`GOVSUB-001`～`005`、`IMPORT-003`、`IMPORT-006`、`SCHEDULE-002/003/006`、`LINE-004`零runtime current producer／public definition／React mapping；
6. customer＋staff雙角色、同一Client多案件、normal same-type replacement不產生`LINE-004`；
7.退役碼仍有必要的owner validation／focused tests／transaction guard／migration readback，不因退出Anomalies而刪除正式business evidence；
8. predicate false且authoritative complete時current row實際delete；
9. strict UTF-8、focused regression、governance／reference scan、`git diff --check`通過；需要DB／Browser／provider evidence的gate仍如實標`blocked`或`not_run`。

## 6. Superseded current work

下列舊Task 96要求不得再形成待辦：

- 13-code anomaly owner backend prerequisite；
- 15-code manual action／terminal matrix；
- PAYOUT-002 late-event recovery；
- GOVSUB-001～005 anomaly repair surfaces；
- IMPORT-003 original-review→new HCM anomaly lineage；
- IMPORT-006 deterministic rebuild／corrected-source recovery branches；
- Scheduling invariant repair UI；
- LINE-004 duplicate-root anomaly recovery；
- 把 automatic LINE retry、replay in progress或readback incomplete顯示成business anomaly。

舊source／tests／receipts若能證明owner correctness仍可保留為evidence；不得因歷史投入成本反向保留已無current causal need的產品概念。

## 7. 維護與停止條件

- 本表只記current未完成工作；completed／superseded細節不重抄。需要稽核時讀正式spec、Git history或既有evidence。
- 新需求先找current正式owner；possibility不自動升格成requirement。
- 缺少會改變owner、public contract、schema、external effect或irreversible action的Authority才停止；局部可安全推導的施工細節直接依current contract處理。
- 前端驗收使用真Chrome；provider lane需真provider receipt；DB lane需合法明確target。mock、單一exit code、file existence或舊session evidence不得冒充current PASS。
- Task 96 current acceptance全部滿足後停止，不新增future hardening／roadmap作為completion gate。
