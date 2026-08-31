# M1 role-scoped LINE identity work package

- `package_id`: `PKG-20260830-LINE-M1-ROLE-SCOPED-IDENTITY`
- `declared_status`: `completed`
- `task_id`: `CUR-LINE-MODULES-1-4-CLOSURE-01`
- `semantic_owner`: LINE Identity
- `canonical_spec`: `01_規格基線/23_LINE身分管理與解除正式規格.md` §9
- `current_consumer`: Task 96 Stage 2 M1 backend prerequisite closure
- `close_condition`: §6 acceptance 與 DB gate table有current evidence；未通過的engine gate明確保留blocked
- `retention`: 完成後由Task 96 register、canonical spec、release artifacts與durable tests吸收；本包轉`completed`

## 1. Objective 與 exact Authority

在不建立customer／staff平行架構的前提下，使同一LINE User ID可持久化customer與staff
兩個role-scoped binding，提供共用event／readback／application contract、單一目前角色狀態，
並將同scope連續兩次binding failure以單一bounded streak幂等連接現有Customer Service
escalation。

授權只包含repository-local additive schema／migration／code／test、必要的minimal Arch Map
leaf／canonical test root與current register狀態。不授權production／`union_db`、provider／deployment、
public API／entry point、legacy `line/line_bot.py` workflow、Staff retirement owner接線或`LINE-006`。

## 2. Invariants 與非目標

1. binding key為`(line_user_id, subject_type)`；每個role獨立version與event lineage。
2. customer／staff可共存；同type multiple active與admin共存fail closed。
3. customer／staff共用同一Domain model、ports、application與repository，不新增役種專屬service。
4. 目前角色只是LINE user的一個nullable `customer | staff`狀態，不擴張為framework。
5. 雙角色未選擇或stale選擇不構成授權；其他Domain不得推論選定角色。
6. failure streak每個LINE user最多一筆，只記current scope、generation、count與ticket reference；
   不保存永久attempt history、window或generic policy。
7. 第二次失敗只透過現有`CreateHumanEscalation`開單，不新增escalation engine或
   provider effect；success reset後新generation可另行觸發一張新單。
8. 解除saga的state machine、retry／manual-complete／provider-success語意不變；Rich Menu只產生
   既有typed intent，worker／transport不變。

## 3. Ordered write set

### WP1 — additive persistence successor

- 新增單一shared role-binding successor root；舊`line_identity_bindings`降為migration／compatibility
  read surface，不再是writer。
- 沿用單一shared binding event stream，補role-scoped stream index／readback所需靜態契約。
- 在LINE user root新增一個nullable active-role state。
- 新增一張current binding-failure streak table，強制每個LINE user最多一筆。
- preserve-data只搬運舊canonical root；不從owner projections補造第二role root。
- 依`10_Global_保留資料Migration與Cutover_Subsystem.md` §9更新schema part、release chain、
  descriptor、plan與focused static tests。

### WP2 — shared Domain／application／repository

- 將binding snapshot／claim／version讀寫改為role-scoped identity，保留一個shared code path。
- 新增internal typed active-role Query／Preview／Apply／receipt／readback，使用現有LINE UoW。
- current-fact readback回傳全部role bindings，並移除「single-row persistence limited」作為current
  成功路徑的表示；既有LINE-004 consumer仍只消費typed current facts。
- menu selection只append既有Rich Menu binding intent；不改provider worker或transport。
- revocation/replacement/review application只做必要role key adaptation；不改狀態機、UoW owner
  或external side-effect語意。

### WP3 — bounded failure streak與既有客服單

- 失敗記錄只擁有current scope比對、`1 → 2`、success reset與generation。
- threshold transition在現有LINE-owned failure-recording UoW內呼叫Customer Service typed gateway；
  source identity／idempotency key只由scope／generation產生。
- 只傳masked context／fingerprint；實作不新增Customer Service public contract。

### WP4 — scoped verification 與 closure

- 新durable tests先補最小LINE Identity Module／Model Arch Map leaf，並放入其宣告的
  canonical root。
- 先跑Domain／Module focused tests，再跑只受影響的LINE subsystem tests、DB metadata／release tests、
  `git diff --check`與architecture closure validator。
- 只在可驗證的development `lu_test_*`與disposable MySQL環境存在時執行fresh／preserve-data／
  developer acceptance；否則Engine／Developer gates保留`BLOCKED`，總結`DB_CHANGE_NOT_READY`。

## 4. DB change inventory

| Class | Source → target | Data effect | Replay／rollback |
|---|---|---|---|
| `schema-only` | shared role binding successor、LINE user active-role column、bounded streak table、event index | additive objects／column／index | release journal幂等；rollback不刊舊root，未切換前可回到舊application |
| `system-seed` | none | none | not applicable |
| `business-row-backfill` | 舊canonical `line_identity_bindings` → role successor | 每個已有non-unbound root搬運一筆；不讀projection補造 | deterministic insert-if-absent；source保留，drift fail closed |
| `destructive` | none | none | 本包禁止drop／truncate／projection重算 |

## 5. Required oracles

1. 同一User ID建立customer後再建立staff，兩者的subject／version／events／owner projections
   都可獨立readback，且共用同一application／repository。
2. 同type第二active subject、admin與customer／staff共存、stale role version均fail closed且零旁路寫入。
3. 雙角色未選擇回傳typed selection-required；選擇Apply幂等，只產生一個menu intent，
   選擇已revoked role失敗。
4. 第一次失敗不開單；同scope第二次只開一單；replay不重複；success reset後再兩次
   失敗可開新單；更換scope不沿用舊count。
5. migration只搬運舊root；projection-only的第二role不被自動建立，並可由readback辨識缺口。
6. 既有replacement／review／revocation／Rich Menu worker／Customer Service escalation focused tests不退步；
   `LINE-006`不在diff。

## 6. Completion 與現行 blocker

WP1～WP4靜態與focused oracle、representative-data preserve migration、current DB readback與normal
local runtime均已`passed`。M1 backend prerequisite已terminal；provider、verified-token LIFF、Rich Menu
qualification與其他LINE surface仍由Task 96 register的獨立後順位項目管理，不由本包外推。

## 7. Current execution evidence（2026-08-31）

- repository-local implementation／baseline propagation：`passed`。1019 已成為 current fresh-schema
  terminal；6 個 living release/schema assertions只刷新 terminal／chain baseline，未改 business oracle。
- affected verification：`passed`，LINE canonical subsystem、M1 Module、Customer Service escalation、
  LINE first-release與受影響schema/release tests合計 `607 passed in 3.23s`。
- M1 Module focused verification：`passed`，`15 passed`；包含shared role persistence shape、descriptor
  exactness、selection fail-closed、admin排他、revoked-role拒絕、bounded streak與replacement。
- 獨立 verifier 指出的兩項 repository-local noncompliance 已修正：1019 parent column 改為
  metadata-guarded replayable DDL，management detail 只在兩個 active role 時要求選角；直接受影響的
  preserve-data runner／plan／schema assembly／MySQL repository regression 為 `105 passed, 1 skipped`。
- 獨立 verifier final readback：`M1_REPOSITORY_LOCAL_PASS`，未發現剩餘 repository-local blocker；
  DB engine gate 仍獨立為 `DB_CHANGE_NOT_READY`，不可由上述證據外推。
- validation manifest／generated release check、Python compile、`git diff --check`：`passed`。
- architecture closure：current slice owner／test routing `passed`；validator整體仍因24個本包外既有
  `DUPLICATE_TEST_ROOT_OWNER`回傳`failed`，本包未新增source／test ownership error，亦未擴張修正。

| Gate | Status | Current evidence |
|---|---|---|
| 1 Scope | PASS | 本package、`23` §9與人工最小化裁決固定owner／write set／acceptance。 |
| 2 Change inventory | PASS | §4已分開schema-only、business-row-backfill、system-seed與destructive。 |
| 3 Static release | PASS | 1019 part、manifest、descriptor、fresh assembly、generated validation release與runner registration互相hash-bound。 |
| 4 Descriptor | PASS | canonical descriptor exact test通過；新三表、parent column、indexes、FK、checks與trigger set可機械比對。 |
| 5 Read-only plan | BLOCKED | workspace沒有明確configured `lu_test_*` target（只有`.env.example`）；runtime default為禁止的`union_db`，因此未啟動plan。 |
| 6 Engine verification | BLOCKED | 無合法disposable／preserve-data MySQL target與engine evidence；607個repository tests不能替代。 |
| 7 Developer acceptance | NOT_RUN | Gate 5／6未PASS，不得執行launcher acceptance、switch或任何DB mutation。 |

2026-08-31 current supersession：Gate 5～7已由Stage 1後的可解析Docker test target收旂。

| Gate | Status | Current evidence |
|---|---|---|
| 5 Read-only plan | PASS | 獨立`lu_test_task96_m1_source_r1`由verified 1003 backup還原；plan證明1019～1021 absent、candidate absent與ordered current chain ready。 |
| 6 Engine verification | PASS | source加入一組合成legacy customer binding／event後，canonical backup→restore→1004～1021 apply→verify為`verified`；1019 owned object exact、view mismatch 0，legacy root／event與role successor逐欄一致，source仍無successor tables。 |
| 7 Developer acceptance | PASS | official same-name replacement後`--require-current`=1021；normal no-auth launcher的FastAPI／React、monitor、durable worker與incident worker通過，Browser `/admin/`與same-origin API GET皆200 evidence已在Task 96 register收旂。 |

Current DB conclusion：`DB_CHANGE_READY`。一次性source／candidate已scoped cleanup；未操作
production／`union_db`／provider／deployment。
