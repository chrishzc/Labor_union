# 服務前 replacement successor contract 規格缺口

- `spec_gap_id`: `PROV-20260828-service-before-replacement-successor-contract`
- `declared_status`: `approved`
- `authority_status`: `CONFIRMED-2026-08-28`
- `terminal_status`: `SPEC_READY`
- `owner`: Scheduling／Matching Coordination；Orders 與 Anomalies 僅消費 typed projection
- `controlling_spec`: `PROV-20260827-historical-order-operational-baseline-spec.md`
- `controlling_package`: `PROV-20260827-historical-order-operational-work-packages.md`
- `affected_package`: `PKG-R-PRE`
- `related_matrix`: `PROV-20260827-historical-order-business-scenario-gap-matrix.md`
- `storage_contract_revision`: `STORAGE-CONTRACT-20260828`

本文件不重開已核准的 R-01～R-04／R-07 行為。2026-08-28 人工已回覆「採用」；
本文 3.1～3.6 與第4節推薦 bundle 因此全部轉為 current Authority。2026-08-28
人工另回覆「核准 RPRE API」，因此第 8.5 節 typed public contract 也轉為 current Authority。本採用不自動核准
production、`union_db`、provider effect 或跳過 DB gates，也不替換 H-projector 的裁決。

## 1. 問題與邊界

`PKG-R-PRE` 要求服務前整案換人時建立新的 Matching successor round，並由 Scheduling owner
以 append-only、版本單調的 replacement lineage 使 Orders current operational step 回到
合法媒合 gate。現況 `ApplyRematch` 只保存 M3 handoff／`rematch_required`，不建立 successor、
不 supersede caregiver-bound roots，也不做 current step 或 anomaly readback，因此不能視為
HOB-A6／R-01～R-04／R-07 完成。

已核准且不重開的行為：

1. official service facts 為零時，服務前案件才可整案回媒合；已有任何 actual service 時固定
   轉既有 Leave／Substitution（HOB-A7）。
2. replacement event／successor version 必須大於舊版；不得倒退或改寫歷史。
3. 預設 current step 為 Step 2；只有同一 replacement round 的 owner readback 證明合法候選池
   可沿用時，server 才可投影 Step 3／4。
4. 舊候選回覆、特定月嫂簽回、recipient confirmation、waiting lock、commitment、排班與
   assignment history 保留，但不滿足新 round gate。
5. R-07 在 successor round 已建而合法候選為零時，維持 Step 2 blocked；不得恢復舊月嫂或假推進。

## 2. Static evidence

| 證據 | 觀察 | 影響 |
|---|---|---|
| `PROV-20260827-historical-order-operational-work-packages.md:42-51` | WP-HOB-B 已定義 Query／Preview／Apply、supersession、successor、readback 與負例 | 行為範圍已足夠，不需重開 R scenarios |
| 同檔 `:119-124,143-147` | `PKG-R-PRE` 為 required package；owner workflow、persistence、API／React／runtime 尚未完成 | implementation evidence 為 BLOCKED |
| `PROV-20260827-historical-order-business-scenario-gap-matrix.md:54-60,133-136` | R-01～R-04／R-07 的 expected outcome 已固定；current ApplyRematch 只回 handoff | 需要 owner successor contract，不是新增業務分支 |
| `subsystems/scheduling/matching_coordination_workflow.py:290-293` | `PreviewRematch` 只回目前 package view | Preview 未提供 root delta、service proof 或 resume step |
| 同檔 `:511-519` | `ApplyRematch` 僅回 `rematch_required` | 沒有 replacement event／round／supersession／readback |
| `subsystems/scheduling/matching_coordination_contracts.py:281-295` | 現有 command 只有 criteria/package/fingerprint 等 M3 欄位 | public replacement input/output 尚未收斂 |
| `infrastructure/mysql/matching_coordination_repository.py:458-501` | event/outbox 仍是 `rematch_required`／`rematch_requested` handoff | 沒有 Scheduling owner consumer 或 successor persistence |
| `db/schema_parts/1003_matching_coordination_successor.sql:80-217` | M3 event、receipt、outbox 可保存 handoff lineage，但不擁有 assignment／service roots | 不可把 M3 schema 當 replacement storage |
| `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md:67-81` | Scheduling 擁有 replacement event、matching round、effective projection；actual service 決定分流 | owner 邊界已有證據，但 exact root mapping 尚缺 |
| `domains/scheduling/assignment_plan.py:203-215` | 一般 Assignment Plan 拒絕空 official service dates | R-04 不能直接重用 generic assignment API |
| `infrastructure/mysql/scheduling_replacement_writer.py:71-79` | 空 assignment 僅容許 cancellation／terms rebuild | R-04 empty-service representation 需 owner 裁決 |
| `ui_react/src/components/MatchingCoordinationWorkbench.tsx` 與 `ui_react/src/tests/*matching_coordination*` | standalone JSON workbench 只測 handoff；未由 Orders page 掛載 | 沒有 R-PRE 人工入口或 post-Apply owner readback |

## 3. 已採用的最小 owner／public contract

以下契約已由 2026-08-28 人工「採用」。R-01～R-04／R-07 的業務結果維持不變。

### 3.1 Scheduling replacement generation／event 的 owner contract

請確認推薦 bundle：由 Scheduling 建立 owner-owned replacement generation／event，保存：

- case identity、prior generation／event identity、replacement reason/evidence；
- strictly greater aggregate／generation version；
- impacted caregiver-bound root identities 與 supersession relation；
- successor matching round identity；
- authoritative official-service proof、source versions、fingerprint、actor、idempotency；
- immutable receipt／outbox reference 與 post-commit readback binding。

此處只需決定 owner、immutable payload、版本與 lineage 關係；不需要在本 gap 命名 Python class、
route function 或 table。必須另外裁決 replacement event 應完全使用既有 Scheduling generation／
rebuild lineage，或允許一個明確的 additive owner artifact；在此之前不得新增 schema enum／table。

### 3.2 Exact root set 與 supersession semantics

請由 Scheduling／Matching owner 固定各情境的 exact root set：

| 情境 | 必須處理的 current roots | 必須保留但不得滿足新 round 的歷史 |
|---|---|---|
| R-01 | 受影響 candidate binding／willingness state | 其他合法 candidate contact history、Orders／Finance roots |
| R-02 | accepted matching plan、segments、replies、recipient confirmations | 舊 plan／decision lineage、無關 Orders／Finance roots |
| R-03 | waiting lock、commitment、signback、recipient binding 及其 current references | immutable lock／commitment／signback history、定金根事實 |
| R-04 | effective generation、assignment、official schedule current projection | 舊 assignment／schedule generation history；不得偽造 service fact |
| R-07 | successor round 與 zero-candidate disposition | 舊月嫂及舊 round history；不得回復為 current |

需裁決 superseded 是由 append-only event／relation 投影，還是由既有 owner current-state event
表示；不得以 generic status update、DELETE＋INSERT 或原地改 staff id 代替。無關的 Orders terms、
Client Finance deposit／obligation、實際服務、Payroll facts 不在本 replacement write set。

### 3.3 Server Query／Preview／Apply public contract

推薦提供 Scheduling-owned、server-authoritative typed Q/P/A；現有 `/preview/rematch` 與
`/apply/rematch` 可繼續作 M3 handoff 的歷史相容證據，但不能宣稱為本 bundle 的完成 API。

已採用的 public semantic shape：

- Query 回傳 exact case identity、actual-service proof、official service-day count、current
  generation／aggregate versions、candidate pool／round、所有 impacted roots、可保留／可
  supersede 集合、合法 resume step 與 active blocker。
- Preview 必須 zero-write，回傳 replacement candidate、root delta、successor round candidate、
  candidate-pool reuse proof、resume step、expected versions、fingerprint 與不可執行原因。
- Apply 只接受同一 Query／Preview identity 的 reason、evidence、expected versions、fingerprint、
  actor/capability 與 idempotency key；在 fresh lock 後驗證所有 owner roots，於一個 outer UoW
  完成 append／supersede／successor／receipt／outbox，再做 fresh readback。
- response 必須明確區分 applied、replayed、blocked、stale/conflict、actual-service referral、
  outcome-unknown；`200` 或 M3 `rematch_required` 不能單獨表示 anomaly terminal。

精確 field set、穩定 error vocabulary、capability atom 與 readback 邊界依第 8.5 節；
route/class 名稱仍是 implementation detail。

### 3.4 Actual-service=0 gate 與 candidate-pool reuse

推薦以 Scheduling assignment-owned official service facts 作唯一分流根事實：

- official service day／actual-service tuple 為零，才允許 replacement candidate；
- 任一正式 service fact 存在時，Preview 固定 zero-write 並 referral 到既有 substitution；
- Step 2 是預設 resume；Step 3／4 只有當同一 successor round 的 candidate pool identity、
  coverage、availability、willingness 與 version 可 fresh-read 證明仍合法時才可使用。

待裁決的最小 owner detail 是「candidate pool reuse proof」的完整欄位與 version binding，以及
R-04 0 official service days 是否用 empty effective generation、matching-only current state，
或其他既有 Scheduling representation。不得為了通過 generic Assignment Plan 而放寬其 non-empty
service-date invariant。

### 3.5 Idempotency、receipt／outbox、readback

推薦沿用 Global 單一 outer UoW 與同 key replay：

- same key＋same canonical payload 回同一 receipt/readback；same key＋different payload 拒絕；
- fresh lock 依 Scheduling 既有 case／staff／generation／lock 順序，不能信任 UI snapshot；
- outbox 只發已提交的內部 successor／readback intent，不產生 LINE/provider 或付款效果；
- post-Apply 必須重新讀 Orders current step、Scheduling effective generation／assignment、
  matching successor round 與 active anomaly；receipt 只是證據之一。

需裁決 receipt 的 canonical owner、outbox target／intent vocabulary、outcome-unknown reconciliation
邊界，以及 missing successor／readback failure 是否由原 occurrence 保持 active、另建 successor，
或回 typed unavailable。Agent 不自行新增 enum 或跨域 receipt 欄位。

### 3.6 Anomaly terminal predicate

推薦 anomaly 只有在以下 conjunction 全部成立時 inactive：

1. official service proof 為零；
2. replacement event version 嚴格遞增且 prior identity／case binding 可追溯；
3. successor round 已存在；
4. 舊 caregiver-bound roots immutable retained 且明確不再滿足新 round；
5. current Orders projection 為 server 計算的 Step 2／3／4；
6. fresh Scheduling、Matching 與必要 Orders readback 完整；
7. R-07 的 zero-candidate 情況則維持 Step 2 blocked 並有具體 successor disposition。

以下任一情況保持原 occurrence active 或回 typed unavailable：actual service、stale、identity
drift、occupancy conflict、successor missing、partial write、receipt/outbox 對帳失敗、readback
unknown。不得由 tracking status、generic resolve、receipt-only 或 provider success 清除。

待裁決的是 occurrence／successor identity 的 canonical tuple、R-07 blocker code／disposition schema、
以及 Anomalies 是否消費 Scheduling event 或透過 owner read model；predicate 的安全方向不得放寬。

## 4. 已採用 bundle

3.1～3.6 已由人工確認，採用下列單一 bounded bundle：

1. Scheduling-owned replacement generation/event，append-only、版本單調、可追溯 prior／successor。
2. Scheduling server Query／Preview／Apply；M3 Matching Coordination 只提供 typed facts／intent，
   不直接寫 Assignment／service-day／Payroll。
3. exact root set 由 owner descriptor 提供；Apply 在同一 transaction supersede caregiver-bound
   current roots、建立 successor round，並保留所有 immutable history。
4. actual-service=0 是 replacement 的硬 gate；actual service 存在固定 referral substitution。
5. server 計算 candidate-pool reuse 與 resume Step 2／3／4，不接受前端任意 step。
6. same-key idempotency、immutable receipt、post-commit outbox、fresh owner readback；不以 M3
   `rematch_required` handoff 宣稱完成。
7. Anomaly terminal 由 replacement lineage、successor、current step 與 owner readback 組合判斷。
8. React 從 Orders／Anomalies exact case 入口呈現 impact、blocked disposition 與 readback；Browser
   驗證回原 Orders workspace 後可繼續，而非只顯示 receipt。

上述為已採用業務契約；schema、table、route/class 與 implementation detail 仍由 task package
依現有能力與 DB gates 收旂，不得改變可觀察行為。

## 5. Non-goals、write set 與 safe stop

### Non-goals

- 不改變 R-01～R-04／R-07 的 expected business outcome。
- 不處理已有 actual service 的整案 replacement；該情況只走既有 Leave／Substitution。
- 不重算或建立新的金額、日期、Payroll、Client Finance、Contract、LINE、provider 或 assignment
  business formula。
- 不改寫舊 matching round、assignment、schedule、waiting lock、commitment、signback 或 receipt。
- 不新增 generic anomaly resolve、status editor、tracking shortcut 或跨 Domain writer。
- 不在本 gap 內決定 route/class 名稱、table/column 名稱、migration release、worker topology 或
  React component 名稱。

### Intended write set after approval

- Scheduling replacement event／generation 與 successor lineage；
- owner-defined supersession relation／current projection；
- successor Matching round；
- R-03/R-04 必要的 waiting-lock／effective-generation current transition；
- immutable receipt、內部 outbox、Anomaly／Orders fresh projection input。

不包含 actual-service、unrelated Orders／Finance／Payroll facts、deposit obligation 或 provider effect。

### Safe stop

以下任一情況必須 zero-write／rollback，保留既有 active blocker，並回 typed unavailable/conflict：

- actual-service proof 非零或無法取得；
- candidate／round／assignment／lock／commitment identity 不唯一或跨案；
- expected version、fingerprint、aggregate generation 或 idempotency payload stale；
- occupancy、coverage、willingness 或 candidate-pool reuse proof 不一致；
- exact root set、supersession relation、successor round 或 owner contract version 未知；
- receipt、outbox、prior／successor lineage 或 post-Apply readback 無法對帳；
- timeout、permission、decode、partial write 或 outcome unknown；
- same key 不同 payload。

禁止以新 key 重送 unknown、以 generic Assignment Plan 放寬空 service dates、以 receipt 取代
readback，或在 current Authority 未核准前新增 schema／route／worker／React public flow。

## 6. 最小驗收與 evidence gates

### Focused／Module／Subsystem

- R-01～R-04／R-07 的 pure branch oracle：actual-service=0、actual-service negative、candidate
  reuse、resume Step、R-07 zero-candidate。
- exact root set／supersession candidate 的 retained／created／invalidated lineage；舊歷史不可變。
- fresh version／fingerprint／identity／occupancy validation；stale、cross-case、missing successor、
  readback unavailable 均 zero-write。
- same-key same-payload replay 與 same-key different-payload rejection；outcome-unknown reconciliation。
- R-04 驗證不繞過既有 assignment plan 的 non-empty service-date invariant。

### Runtime／API

- 受控 `APP_ENV=development`、`lu_test_*` scenario；不得使用 `union_db`，每一 R case 有唯一 scenario
  identity 與 owned-row before/after receipt。
- Query／Preview 證明零寫入；Apply 證明單一 outer UoW、generation／round／lock lineage、fresh Orders
  step 與 Anomaly readback。
- API typed decoder／error envelope 證明 handoff `rematch_required` 不被當成 terminal success。
- R-01～R-04 正向、R-07 blocked、actual-service substitution referral、stale／identity／timeout／
  readback negative 全部有可重跑證據。

### React／Browser

- React 從 Orders／Anomalies exact case 開啟 replacement view，顯示 root impact、reason/evidence、
  candidate reuse、resume step、blocked disposition 與 fresh readback。
- Apply 後重新 Query owner roots／current step／active anomalies；不得以 receipt-only 或任意 step
  更新畫面。
- Task96 development `local_bypass` no-auth Browser：R-01～R-04、R-07 及 actual-service negative，
  驗證回原 Orders workspace 可繼續；每 case 保存最小去敏 receipt、before/after/readback。
- Browser 不得成為唯一 contract evidence；沒有 API／DB／owner readback 時固定 `NOT_RUN` 或 `BLOCKED`。

## 7. Convergence

本文件已收旂為 `SPEC_READY`，可進入 task-pack。既有 R-01～R-04／R-07 行為不重開；
後續若改變 owner、public contract、schema、write set 或
external effect，才需回到本文件及相關 package 重新收斂。

## 8. Additive persisted contract supplement（2026-08-28）

### 8.1 Evidence-supported storage decision

2026-08-28唯讀inventory確認既有Scheduling generation/rebuild/receipt、Matching package/event/receipt/
outbox、lock/commitment lifecycle及assignment history可重用為owner facts，但無法機械表達3.1～3.5
要求的replacement event、跨root supersession、successor binding與exact replay readback。依第4節
已採用bundle及task-pack既有`schema_gate`，選擇一個Scheduling-owned additive replacement artifact；
它只建立lineage與proof，不複製Matching、Assignment、actual-service或Finance根事實。

### 8.2 Required persisted records

1. **Immutable replacement event**：保存case/scenario、prior與replacement generation/event identities、
   expected/resulting aggregate/generation/event versions、authoritative zero-service proof identity/version/
   digest、reason/evidence digest、actor/capability、command/preview fingerprints、idempotency/correlation及
   successor round binding。
2. **Exact root relation**：每個event逐筆保存root identity、owner/root kind、canonical ordinal與
   `retained | superseded | created` disposition；同event+root只能出現一次，三組不得重疊，history不可更新或刪除。
3. **Successor binding**：保存replacement event與既有Matching successor package/round、Scheduling
   generation及R-07 disposition的受約束relation；其case與resulting versions必須和event一致。
4. **Immutable receipt**：保存event binding、idempotency、command/preview fingerprints、三組root identity
   set digest/count、resulting versions、successor binding、outbox identity與result state。
5. **Immutable internal outbox**：一個committed event/receipt只建立一個successor/readback intent，target
   固定為Orders/Anomalies projection consumer；不允許LINE、provider、payment或payroll effect。

Scheduling current effective generation／assignment仍使用既有owner projection；R-04 matching-only empty
successor不得建立假assignment或放寬generic Assignment Plan。Matching package/round仍由Matching owner
提供typed facts；additive artifact只保存跨owner binding，不成為第二套Matching SSOT。

### 8.3 Constraints、replay與failure behavior

- replacement event identity、prior identity、successor identity、case與versions必須有FK／unique／check
  或owned descriptor驗證；resulting aggregate/generation/event versions各自嚴格大於其expected/prior版本。
- receipt中的三組root IDs使用canonical排序集合digest＋count，並由逐筆root relation機械重算；JSON
  snapshot不能取代relation、version與readback binding。
- same key＋same canonical payload只回同一receipt並fresh-read三組root relation與successor；任一identity、
  version、digest、count或root set漂移固定`outcome_unknown`，不得回`replayed`。
- transaction內readback失敗rollback；commit後readback失敗不得rollback已提交event，固定
  `outcome_unknown`並只允許原key reconciliation。
- 不做system seed、business-row backfill或destructive migration；舊案件不批次猜測replacement，只有
  operator對受控case Apply時append新event。

### 8.4 Acceptance and source map

| Requirement | Current source/evidence | Observable oracle |
|---|---|---|
| R-01～R-04 exact lineage | §3.1～3.4；storage inventory | event/root/successor同案同版；history retained；current projection exact |
| R-07 blocked successor | §3.2、§3.6；Matching package lineage | zero-candidate disposition綁同一event/round並維持Step 2 blocked |
| same-key replay | §3.5；RPRE Q/P/A r5 | exact三組root readback才`replayed`；任一漂移`outcome_unknown` |
| actual-service negative | §3.4～3.5；Scheduling official proof | any service fact zero-write referral；不建立event/root/receipt/outbox |

本supplement不變更owner、public contract、write set或external effect；current Authority已明確允許task
package在完整DB gates內late-bind additive artifact，因此無新增人工裁決。

```yaml
convergence:
  status: READY
  blockers: []
```

## 8.6 Production loader source-map proposal（2026-08-28）

本節只解除 current production dependency 固定 503，不改 R-01～R-04／R-07 結果、
Domain invariant、1012 schema 或 provider boundary。

- Query 必須明確傳入 `scenario=R-01|R-02|R-03|R-04|R-07`，不自動猜測。
- authoritative actual service 為 effective Scheduling generation 的 assignment-owned
  `staff_schedule(effective_marker=1,is_work_day=1)` 中，依 Global BusinessClock 已開始的
  official service moments；future schedule 不阻擋，service-day logs 只作 corroborating evidence。
- identity 固定為 `scheduling-aggregate:{case}`、
  `scheduling-generation:{case}:{id}:{number}` 與
  `scheduling.official-service:{case}:generation:{id}`；缺 version/identity/effective generation 就停止。
- 首次 replacement 必須綁定可驗證 Scheduling rebuild predecessor event；缺失時
  `replacement_prior_event_unavailable`，不虛構 genesis。
- R01～R04/R07 使用 current owner composite roots，whole-row-set fingerprint 與 immutable retained
  history；exact cardinality/owner/case/current 任一漂移就 fail closed。
- Matching 在同一 borrowed connection/outer UoW 重讀完整 13-source tuple、latest criteria、
  parent package 與 package-bound source event。Step 2 預設新 pool；Step 3/4 只在同一
  successor round 的 coverage/availability/willingness 都 fresh-valid 時 reuse。

```yaml
rpre_loader_source_map:
  status: AUTHORITY_REQUIRED
  schema_change_expected: false
  production_provider_effect: none
```

### 8.5 Typed public API contract（2026-08-28 人工核准）

#### 8.5.1 Route、權限與 request

- Query：`GET /api/v1/orders/{case_no}/service-before-replacement`，無 body。
- Preview：`POST /api/v1/orders/{case_no}/service-before-replacement/preview`；strict body 為
  `scenario`、trimmed `reason` 1..500 與非空、去重、排序的 `evidence`。
- Apply：`POST /api/v1/orders/{case_no}/service-before-replacement/apply`；strict body 為
  `scenario`、三組 expected version、prior generation/event/aggregate identity、
  `preview_fingerprint`、同一 `reason/evidence`；header 必須有 `Idempotency-Key`。
- `scenario` 只接受 `R-01|R-02|R-03|R-04|R-07`。Q/P/A 沿用
  `orders.historical_review.remediate`；actor/capability 由 server principal 推導，不接受 body 傳入。

#### 8.5.2 Query／Preview response

Query strict data 必須包含：case/scenario；`ready|blocked|substitution_referral`；actual-service
count/dates/proof；prior identities 與 generation/event/aggregate versions；impacted/retained roots；
nullable root delta、candidate-pool reuse proof、successor round；server-owned `step_2|step_3|step_4`；blockers。

Preview 在 zero-write 後回傳上述 case/scenario/outcome/prior facts，並精確加入 replacement
generation/event/successor identities、expected/resulting versions、retained/superseded/created roots、
resume step、reuse proof、service proof、blockers、`preview_fingerprint`、reason/evidence 與
`successor_matching|matching_only_zero_service` projection kind。UI 不得傳入 resume step。

Root 固定為 `kind/root_id/case_no/current/caregiver_bound`。Proof、successor 與 reuse 必須帶
case/identity/version/fingerprint；strict decoder 必須拒絕 cross-case、count 不等於 collection、
root set 相交、ready 卻有 blocker，以及 referral 卻帶 replacement facts。

#### 8.5.3 Apply response 與 fresh readback

Apply 成功只回 `200 applied|replayed`，data 固定包含 exact receipt 與 readback。Receipt 含
case/receipt/idempotency/command/preview identities、replacement generation/event/successor、resulting versions、
outbox、三組 root IDs/digest/count 及 nullable Matching numeric FKs。Readback 含同一 identities/
versions/root sets/digests/counts/outbox/FKs 與 `complete`；成功時必須 `complete=true` 且全部對帳。

Apply 必須依序做 fresh owner lock，重驗 proof/identity/version/reason/evidence/fingerprint，在一個
outer UoW append/supersede/successor/receipt/outbox，transaction-local 對帳，commit 後再做
Scheduling/Matching/Orders/Anomalies fresh readback。Commit 後不明回
`503 replacement_outcome_unknown`，只能同 key reconcile，不得假成功或回滾已提交交易。

#### 8.5.4 Stable error vocabulary

錯誤沿用 Global 八欄 envelope。`409` 只用 `replacement_blocked`、
`replacement_actual_service_exists`、`replacement_version_conflict`、`replacement_identity_drift`、
`replacement_reason_evidence_drift`、`replacement_preview_stale`、`replacement_idempotency_mismatch`；
`422` 為 request/scenario invalid；`503` 為 service-proof/persistence/readback unavailable 或
`replacement_outcome_unknown`；另保留 `401/403/404/500`。M3 `rematch_required` 仍只是 handoff，
actual-service 仍 zero-write referral 到 substitution；不新增 schema、provider、generic resolve 或 permission tier。

```yaml
convergence:
  status: READY
  blockers: []
```

## 9. Matching package compatibility correction（2026-08-28）

本節修正實作審查發現的 persisted-package 漂移；不改 R-01～R-04／R-07 結果、
public Q／P／A 語意、schema 或 external effect。

### 9.1 Fresh Matching source

- Apply 只接受 repository 在同一 outer UoW 內重讀並鎖定的 Matching source；
  workflow／UI／bundle 預載 snapshot 不能取代 fresh read。
- source 必須含 canonical criteria snapshot、完整 source-version tuple、latest parent package
  與其 source event identity。criteria digest 必須由
  `case_no + criteria + criteria_version + canonical source_versions` 重算；只驗證 64 位字串
  不足以通過。
- source event 必須和 case、criteria snapshot 及 parent package 同時綁定。任一缺失或
  漂移時整個 outer UoW rollback，不留下 generation、event、root、package、receipt 或
  outbox row。

### 9.2 Canonical successor package

- successor row 必須是既有 `MatchingPackage` reader 可解析的 canonical payload，包含
  `package_id`、`version`、`mode`、`segments`、`required_service_dates`、
  `candidate_results`、`criteria_snapshot_id`、`source_versions`、`state`、`blockers`、
  `warnings`、`fingerprint`；不另存第二種私有 JSON shape。
- Step 2 且尚無可重用候選時，package state 固定為 schema 已有的
  `candidate_pool_open`，可以是空 `segments`／`candidate_results`，且不得假造 assignment。
  Matching domain／reader 必須可以 typed 解析此狀態。
- Step 3／4 只能從 fresh source 複用完整且仍合法的 candidate／segment facts；不能從
  `candidate_count` 或 root identity 還原。R-07 維持已有的 concrete
  `no_candidate` successor，不由本 Apply 新建第二個 terminal package。
- `package_digest` 必須等於 canonical package payload fingerprint，而且 DB row 與
  payload 的 package identity／version／state／source tuple 必須一致。

### 9.3 Scheduling generation transition

- R-01～R-04 Apply 必須鎖定現有 effective prior generation 與 aggregate，在同一 outer
  UoW 建立 strictly newer 的 empty effective successor generation、取消 prior current marker，
  並原子更新 aggregate version／generation counter／effective generation。不建立假
  assignment 或 schedule。
- prior effective generation 缺失、非 current、版本漂移或 aggregate CAS 失敗時 rollback；
  不自行合成 prior generation。

### 9.4 Acceptance correction

| Claim | Direct oracle |
|---|---|
| fresh source | 傳入 bundle snapshot 不影響 Apply；repository loader 缺失／cross-case／digest／event binding 漂移均 rollback |
| reader compatibility | 新 package 經既有 `load_current_package()` parser 可 typed 往返；Step 2 為 `candidate_pool_open` |
| no fabricated reuse | Step 3／4 精確保留 fresh candidate／segment／source versions；無 proof 不產生候選 |
| generation transition | prior 取消、successor effective、aggregate CAS 與 1012 event 在同一 UoW；任一失敗無 committed rows |

```yaml
convergence:
  status: READY
  blockers: []
```

## 10. Concrete persistence contract supplement（2026-08-28）

本節只收斂已採用的 Scheduling owner、Matching successor、單一 outer UoW 與 exact
readback 如何投影到 1012；不新增業務分支、public result、schema 或 external effect。

### 10.1 Request facts 與 owner 驗證

- Query／Preview request 的 `scenario` 是本次人工操作意圖；`reason` 與 `evidence` 是
  Preview／Apply 的 canonical command facts，不是 DB 內自動推測值。
- repository 以 request context 讀取 current owner roots，並驗證該 scenario 的 required root set、
  case binding、official-service proof 與 versions；root 多組歧義、缺失或較後階段衝突固定
  fail closed，不由 adapter 猜 scenario。
- Apply fresh lock 後必須用同一 request context 重讀；UI snapshot、receipt 或預先讀取
  都不能取代 current owner facts。

### 10.2 Matching successor persistence port

RPRE 在同一 borrowed connection／outer UoW 內使用 typed
`MatchingSuccessorPersistencePort`；輸入為 case、successor round、candidate disposition、
fresh Matching source snapshot、actor 與 idempotency，輸出必須包含：

- `package_lineage_id`、`matching_event_id` 兩個 1012 要求的 numeric FK；
- package／round／event immutable identities；
- Matching-owned package version 與 event resulting version。

successor 必須建立新的 `matching_coordination_package_lineage`（`lineage_kind='rematch'`）與
`matching_coordination_events`（`event_type='package_proposed'`）。它們的 version 由 Matching
lineage 獨立單調遞增，不套用 Scheduling generation/event version。既有 `rematch_required` 只是
handoff evidence，不是 successor completion；缺 criteria／parent package／source event 或 fresh
binding 時零寫入。

### 10.3 Root descriptor 與 exact readback

1012 的 owner／kind 關係為 canonical descriptor source：Matching 擁有 candidate binding、
willingness、plan、segment、reply、recipient confirmation 與 successor round；Scheduling 擁有
waiting lock、commitment、signback、recipient binding、effective generation、assignment 與 official
schedule。每種 root descriptor identity 固定為
`service-before-replacement.<owner>.<root-kind>`，descriptor version 為 `1`，fingerprint 由
owner、kind、identity path 與 version 的 canonical tuple 計算；repository 不得只從任意
`root_id` 猜 owner。

三組 root relation 分別以 `root_identity` 排序，`canonical_ordinal` 必須連續為 `1..N`。
digest 為 `SHA-256("\\n".join(sorted(ids)).encode("utf-8"))`；空集合為
`SHA-256(b"")`。receipt 的 digest/count 必須由已寫入 relation rows 重算，不信任
workflow／UI 傳入值。

same-key replay 必須 fresh 對帳 command fingerprint、event／successor、Matching numeric FK 與
string identities、owner descriptors、三組 root 完整集合／ordinal／digest／count、resulting
versions 與 outbox identity。任一漂移固定 `outcome_unknown`，不得回 `replayed`。

```yaml
convergence:
  status: READY
  blockers: []
```
