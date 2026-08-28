# Historical baseline projector contract 規格缺口

- `spec_gap_id`: `PROV-20260828-historical-baseline-projector-contract`
- `declared_status`: `approved`
- `authority_status`: `CONFIRMED-2026-08-28`
- `terminal_status`: `SPEC_READY`
- `owner`: Orders / Anomalies，並由各 owner Domain 確認 root contract
- `controlling_spec`: `PROV-20260827-historical-order-operational-baseline-spec.md`
- `related_spec_gap`: `PROV-20260827-historical-operational-storage-and-supplement-spec-gap.md`
- `related_scenario_matrix`: `PROV-20260827-historical-order-business-scenario-gap-matrix.md`
- `affected_package`: `PKG-H-BASELINE`
- `storage_contract_revision`: `STORAGE-CONTRACT-20260828`
- `catalog_v2_amendment_status`: `proposed`

本文件只提出 projector／minimum-required-facts／typed API 的規格缺口，不能覆寫已核准的
Historical baseline storage、Orders domain 或 Anomalies domain 契約。2026-08-28 人工已回覆
「採用」；本文 2.2～2.7 的推薦候選因此全部轉為 current Authority，2.1 與 2.8 維持
原 current Authority。本採用不自動核准 production、`union_db`、provider 或跳過 DB gates。

## 1. 為何需要本 gap

current controlling spec §4 的 11 步表已定義各步不可由 baseline 偽造的 root facts，但沒有把
root contract 編成可由 projector 逐步驗證的 versioned catalog。scenario matrix 的 H-01～H-06
（特別是 H-02／H-03 的 occurrence closure、H-05 的 successor、H-06 的
`earliest-invalidated-root`）因此仍缺少共同的 identity、version、terminal 與 readback 邊界。

fresh read-only 盤點的具體 evidence：

- `domains/orders/historical_operational_baseline.py` 的 Facts 只有 Orders/provenance 與單一
  owner-binding fingerprint，沒有 11 步 owner root vector。
- `infrastructure/mysql/historical_operational_baseline_repository.py` 已在 fresh review 後限定
  `adoption.outcome = 'adopted'`，但目前 `baseline_binding_fingerprint` 只包含 Orders version與
  adoption provenance，仍沒有讀取各 owner root identity/version。
- `api/schemas/historical_operational_baseline.py` 的 Query／Preview view 沒有
  minimum-required-facts、owner root、active occurrence 或 successor readback。
- baseline outbox 尚未有獨立 consumer/projector contract；existing historical adoption 與 review
  remediation consumers 不能冒充 baseline projector。
- `api/routes/historical_operational_baseline.py` 雖存在，current `api/main.py` 尚未註冊該 router；
  `ui_react/src` 也尚無 baseline client/workbench。這些是 implementation/runtime evidence，不是
  本 gap 自行授權施工的理由。

上述證據使 H-01～H-06 目前維持 `AUTHORITY_REQUIRED`，而非以 live code 反推規格。

## 2. 最小待裁決項

以下八項是完成 projector contract 所需的最小契約集合。2.1 可由既有正式
Historical Order 契約收旂，2.8 已由 2026-08-28 Task 96 人工指示收旂；只剩 2.2～2.7
需要新的人工確認，才能轉成 `SPEC_READY`。不可把推薦候選視為已採用行為。

### 2.1 Historical eligibility（current Authority 已收旂）

根據 controlling spec 的 Historical Orders 邊界與 B1 source lineage，baseline eligibility 固定為：
canonical Order identity 綁定一筆
`historical_order_adoption_receipts`，且 adoption outcome 必須為 `adopted`；source event identity、
source version 與 case/order identity 必須相互一致。只接受 `outcome = adopted` 的
canonical adopted receipt；不存在、
不一致、非 adopted 或 source identity 跨案時，Query／Preview／Projector 回 typed unavailable 或
integrity conflict，不建立 baseline anomaly。

### 2.2 Versioned owner-root contract catalog

每個 step 的 catalog entry 至少要固定下列欄位：

| 欄位 | 必須回答的問題 |
|---|---|
| `contract_id`、`contract_version` | 這個 root contract 的 immutable identity 與版本是什麼？ |
| `step`、`owner_domain` | 由哪個 11-step 與哪個 owning Domain 負責？ |
| `root_identity_kind`、`root_identity_path` | canonical root identity 與 exact field/path 是什麼？ |
| `source_event_identity`、`source_version` | fresh readback 的來源與單調版本是什麼？ |
| `terminal_predicate_id`、`terminal_predicate_version` | 何種 owner-owned predicate 才算已補齊？ |
| `repair_target`、`repair_capability` | 操作者應進入哪個 owner Q/P/A 與 capability？ |

catalog 必須涵蓋 current controlling spec §4 的 Step 1～11，並將每步可免除的歷史操作軌跡與
不可免除的 root fact 分開。catalog 若缺 entry、版本、owner、predicate 或 repair target，必須
fail closed。

推薦候選（非 Authority）：catalog 由各 Domain owner 提供 immutable contract descriptor，Orders
只組合與保存 descriptor fingerprint，不自行定義跨 Domain predicate。

### 2.3 Whole-vector fingerprint 與 fresh Apply

裁決 `owner_binding_fingerprint` 是否改為 canonical、排序穩定的 whole-vector fingerprint，至少
包含 Order/provenance 與 selected step 所需的每個 owner root identity、source version、contract
version、terminal result。Query／Preview 回傳此 fingerprint；Apply 必須重新鎖定並重建 vector，
fingerprint 不一致即 stale/conflict，不能由 Orders version 單獨放行。

推薦候選（非 Authority）：fingerprint payload 使用 catalog entry 的完整 canonical tuple，排除
顯示文字、PII 與可變 delivery metadata；同一 facts vector 必須產生同一 digest。

### 2.4 Deterministic occurrence 與 umbrella identity

裁決 H-02/H-03 的 occurrence identity 是否由下列 immutable tuple 決定：canonical order/case、
baseline generation/event identity、contract id/version、step、root identity/path、source version。
並裁決多問題 umbrella 是否另有 aggregate identity，以及 occurrence 修正後如何保留 successor
link。

推薦候選（非 Authority）：occurrence identity 對 canonical tuple 做 domain-owned SHA-256；umbrella
identity 對 case + baseline generation + contract catalog version 做 SHA-256。不得以顯示文字、
tracking status 或任意人工 key 作 identity。

### 2.5 Successor 與 terminal semantics

裁決 H-05 的 predecessor/successor 必須具備同案 binding、prior identity、嚴格遞增 owner source
version、同一 contract lineage 與 owner terminal predicate readback。必須定義：

- predecessor 何時變 inactive；
- successor 何時必須 active；
- projector retry/replay 如何避免兩者同時消失或重複；
- source version gap、identity drift、unknown predicate、readback unavailable 的結果。

推薦候選（非 Authority）：只有 verified newer successor 且 terminal predicate/readback 全部通過
才 supersede predecessor；任何 unknown 保持 predecessor active 並產生 typed unavailable。

### 2.6 H-06 earliest-invalidated-root

裁決 owner typed replacement/reversal/reopen event 的 minimum payload 與計算責任。必須明確：
baseline selected step 與 immutable lineage 不變；current projection 由 server 使用 owner catalog
計算最早失效 root；不允許 arbitrary status editor 或前端 ordinal。

推薦候選（非 Authority）：owner Domain 產生 version 更大的 typed event，並提供 invalidated root
set；Orders/Anomalies projector 依 catalog 順序選第一個未達 terminal predicate 的 root，若 event
缺少 set 或 catalog version 不相容則 fail closed。event type、set encoding、predicate 名稱仍待
人工裁決。

### 2.7 Typed API 與 readback

裁決 Query／Preview／Apply 的最小 typed view 是否必須包括：historical eligibility/provenance、
catalog version、完整 11-step projection、每步 minimum facts、owner/root identity、source version、
terminal result、occurrence/umbrella identity、合法 repair target、preview fingerprint、receipt、
outbox intent 與 post-Apply fresh readback。

Apply 必須維持單一 outer UoW、idempotency、fresh lock、immutable receipt/outbox；200 或 receipt
存在不等於 anomaly terminal。outcome unknown 必須能以同一 idempotency identity reconciliation，
不得換 key 盲送。

推薦候選（非 Authority）：新增 baseline-specific typed client/view；不讓 raw dict 穿透 React，
不把 existing `HISTORICAL-ORDER-001` 或 `ORDER-HIST-*` 直接重用為 baseline missing-root code。

### 2.8 No-auth Browser acceptance（current Authority 已收旂）

依 2026-08-28 Task 96 人工指示，H-01～H-06 驗收固定使用隔離的 development
validation profile no-auth/local-bypass Browser。此 Authority 不改寫 production authorization；
production API 越權仍必須 fail closed，且 Browser evidence 不得成為唯一的業務
contract source。只允許 `APP_ENV=development` 且 database 通過 `lu_test_*` allowlist 的
no-auth local-bypass；每個 scenario 使用唯一 identity、保存 before/after/readback，結束時 scoped
cleanup 或明確保留，禁止觸及 `union_db`/production。

## 3. H-01～H-06 projector contract 交接邊界

在上述裁決完成前，以下只作為待收斂的 contract shape：

1. **H-01**：accepted historical provenance + Orders identity/version + selected step 所需完整
   root vector；全齊才建立 baseline projection，不產生 fake owner event。
2. **H-02**：單一 missing catalog entry 產生一筆 occurrence，帶 exact path、owner、version 與
   repair target；owner Apply fresh readback 後只清該筆。
3. **H-03**：多筆 occurrence 各自可 replay／successor；umbrella 只在最後一筆 terminal 後消失。
4. **H-04**：evidence unavailable 只作 document-search disposition；不建立 signed、delivered、
   paid、allocation 或 completion root。
5. **H-05**：baseline immutable；合法 owner successor 必須驗證 prior identity、strictly newer
   version、same case/catalog lineage 與 terminal readback。
6. **H-06**：typed owner event 可使 current projection 回到 earliest invalidated root；baseline
   selected step、prior event 與 immutable evidence 不回寫。

## 4. Non-goals

- 不決定 11 步各 Domain 的業務公式、金額、日期或法律語意；這些仍由各 Domain 正式規格擁有。
- 不新增或修改 schema、migration、seed、backfill、production data、release chain 或現有 anomaly
  registry。
- 不把 baseline 變成 LINE/provider、簽章、付款、allocation、assignment 或 lifecycle 假事件。
- 不替換既有 adoption review、review remediation、HCM import aggregate 或 generic tracking resolve。
- 不實作 owner repair command、replacement workflow、leave/substitution 或 cancellation/finance
  contract。
- 不以 Browser/UI 行為覆寫 current SSOT，也不因本 gap 直接授權 API route、worker 或 React 施工。

## 5. Safe stop 與 fail-closed

下列任一情況發生時，consumer/projector 必須停止該 intent、rollback 或保持既有 active occurrence，
並回傳 typed error；不得清 alert、推進 current step 或建立 successor：

- historical eligibility、catalog entry/version、root identity、owner、predicate 或 repair target
  缺失/未知；
- whole-vector fingerprint、source version、case/order binding 或 baseline event/receipt 不一致；
- stale、version rollback、source version gap、same key 不同 payload 或同 identity 跨案；
- owner terminal predicate、successor readback 或 anomaly projection readback unavailable；
- malformed payload、unsupported contract version、permission denied、timeout/network/decode outcome
  unknown；
- projector receipt、outbox intent、prior/successor lineage 無法以 immutable facts 對帳。

只有同一 intent/key 的 retry/reconciliation 可處理 unavailable；stale/conflict 必須回到 Query／
Preview。不可使用 generic resolve、status editor、receipt-only 或 provider success 代替 terminal。

## 6. Write-set 與協作邊界

### 可平行（前提：先凍結本 gap 的裁決結果）

- 各 owning Domain 各自提供其 root contract descriptor、source version、terminal predicate 與
  repair capability evidence；每 lane 只寫自己的 domain-owned 文件／測試。
- Orders baseline adapter 與 Anomalies projector 可分 lane 設計 typed port；不得同時改 shared
  registry、global catalog 或 public index。
- API typed schema/client 與 no-auth Browser acceptance 可分 lane；兩者以已核准的 API contract
  作唯讀輸入。

### 不可平行

- historical eligibility、catalog version、occurrence/umbrella identity、successor semantics、
  H-06 invalidation algorithm 未裁決前，不得並行實作 schema、worker、API public route 或 React
  rendering。
- release manifest/schema assembly/catalog/index 只可由 integration writer 在裁決後統一更新。
- projector readback、receipt/outbox persistence 與 worker retry policy 必須由同一 owner 交接一個
  transaction／idempotency contract；不可各自發明 closure semantics。

## 7. Acceptance 與 evidence gates

### Specification acceptance

- [x] 2.1 與 2.8 保持 current Authority；人工已確認 2.2～2.7，且每個
  contract/predicate/identity 有 canonical name、version、owner。
- [x] H-01～H-06 可由 catalog、occurrence、successor、terminal、readback 規則逐項演繹。
- [x] candidate 與已核准 Orders／Anomalies／storage 規格逐項對照，無覆寫或 speculative field。
- [x] `declared_status` 已轉為 approved，terminal 為 `SPEC_READY`。

### Implementation/runtime evidence（本文件不執行）

- [ ] Module／Domain focused tests：catalog、fingerprint、identity、predicate、H-06 regression。
- [ ] Subsystem tests：consumer claim、replay、successor、retry/dead-letter、single-UoW/readback。
- [ ] API typed tests：Query／Preview／Apply、same-key reconciliation、stale/conflict/unavailable。
- [ ] React tests：occurrence/umbrella detail、owner repair target、no generic resolve、outcome unknown。
- [ ] 真實 MySQL fresh/preserve-data evidence；若涉及 schema，另須通過專案 AGENTS.md §3.1 全部 DB gates。
- [ ] 受控 no-auth Browser（或人工核准的 test principal）H-01～H-06：每個 scenario 保存最小去敏
  receipt、before/after/readback、active anomaly 結果；不得用 mock 代替 engine evidence。

規格驗收已收旂為 `SPEC_READY`；runtime evidence 仍由後續 task package 驗收，未通過前不得
宣告 implementation 完成。本文件不授權 deployment 或外部副作用。

## 8. Additive persisted contract supplement（2026-08-28）

### 8.1 Evidence-supported storage decision

2026-08-28唯讀inventory確認B1 event／receipt／outbox、`anomaly_current_alerts`、
`anomaly_workflow_events`與consumer checkpoint只能部分重用；現有Finance occurrence、import warning
task與root-fact snapshot/receipt都無法機械表達本規格2.4～2.5的baseline identity、successor與
umbrella membership。依已採用2.2～2.7與task-pack既有`schema_gate`，選擇一個專屬additive
projector artifact；這是既有可觀察契約的持久化投影，不新增業務結果或第二套owner root。

### 8.2 Required persisted records

1. **Immutable occurrence**：保存occurrence identity、canonical order/case、B1 baseline event與
   receipt binding、catalog version、完整descriptor canonical tuple、typed owner observation、
   owner-binding fingerprint、terminal predicate/result、repair target/capability及created time。
2. **Umbrella membership**：每筆occurrence綁定唯一umbrella identity；umbrella identity固定由
   case、baseline event與catalog version計算。current aggregate狀態重用`anomaly_current_alerts`，
   membership relation不得以alert的顯示狀態或tracking status取代。
3. **Immutable successor relation**：保存predecessor/successor occurrence、owner event、prior/new
   source versions、predicate version與fresh readback fingerprint。same-case、same-contract、same
   descriptor lineage及strictly newer source version全部成立後才可使predecessor inactive。
4. **Immutable projector receipt**：保存source intent、payload digest、idempotency、baseline event／
   receipt／outbox binding、whole-vector fingerprint、exact occurrence identity set digest/count、
   umbrella identity、result state與post-commit readback digest。

typed owner observation使用兩種canonical variant：available保存root identity、source event/version與
terminal result；unavailable保存descriptor的identity kind/path及typed unavailable code，root identity與
source version為明確空值。不得把顯示文字或任意sentinel字串放入identity。occurrence identity由
order/case、baseline event、catalog version、descriptor canonical tuple及此typed observation tuple計算。

### 8.3 Constraints、reuse與failure behavior

- source event／receipt／outbox、order/case、occurrence、umbrella及predecessor/successor必須有可驗證
  FK／unique關係；同source intent＋同payload只回原receipt，同identity＋不同payload固定integrity conflict。
- exact occurrence set以canonical排序後identity集合計算digest並保存count；JSON只能保留去敏snapshot，
  不能取代identity、FK、unique、version與set digest/count。
- `anomaly_current_alerts`只作current umbrella projection；`anomaly_workflow_events`只作合法
  predicate-driven reopen/auto-resolve audit；checkpoint只記進度，三者都不是immutable projector receipt。
- H-03每次只根據fresh terminal occurrences把count由3→2→1→0；readback、successor或set對帳未知時
  保持原active projection並回typed unavailable。
- 不修改已發布1010 artifact，不做system seed、business-row backfill或destructive migration；只有新
  baseline intent及其後續owner event會建立新records。

### 8.4 Acceptance and source map

| Requirement | Current source/evidence | Observable oracle |
|---|---|---|
| H-02 exact occurrence | §2.2、§2.4；storage inventory | same facts replay同identity；cross-case/tampered descriptor拒絕 |
| H-03 umbrella membership | §2.4～2.5；`anomaly_current_alerts` current projection | 3→2→1→0且無一次清空；membership/readback可對帳 |
| H-05 successor | §2.5；owner source version contract | only same-lineage strictly-newer verified successor可inactive predecessor |
| HOB-N1 retry/readback | §2.7；B1 immutable source artifacts | same intent exact replay；different payload conflict；unknown保持active |

本supplement沒有新的使用者結果、public API或external effect；current Authority足以決定此最低持久化
projection，無需新增人工裁決。

```yaml
convergence:
  status: READY
  blockers: []
```

## 10. 1011 projector persistence v2 重建契約（2026-08-28）

本節依 2026-08-28 人工「1011核准重建」成為 current Authority，並取代 §9.2(7) 對「預期不新增
DDL」的舊假設。現行 1011 只能保存 immutable occurrence／單次 membership，不能表達 occurrence
解除、membership 3→2→1→0、owner repair retrigger或可靠 projector delivery，因此不得直接
requalify。這是 T3 schema／worker／current projection 變更；不改 HCAT 的 11-step、owner root或
terminal predicate。

### 10.1 Requirements

- `HPROJ-RB-01 Occurrence state`：保留既有 immutable occurrence與successor；另以 append-only
  state event保存 `opened | resolved | superseded`。每筆event綁prior state event、同案同descriptor／
  contract／predicate lineage、owner event identity/version與fresh readback fingerprint。只有同lineage
  strictly-newer owner version可使predecessor inactive；owner regression以新occurrence `opened`，不改舊列。
- `HPROJ-RB-02 Exact active membership`：每次projector receipt保存一份append-only active-set snapshot；
  同一occurrence可出現在不同receipt，但同receipt不得重複。receipt保存active membership set
  digest/count；0筆必須可表達。舊snapshot不可update/delete，3→2→1→0由連續receipt機械讀回。
- `HPROJ-RB-03 Durable trigger/delivery`：初始baseline confirmed與六owner已提交repair event都必須成為
  typed trigger。owner event必須由owner Apply同一UoW的既有immutable event/receipt/outbox產生；projector
  只按source-specific checkpoint讀取新event，不做全表猜測或以UI callback代替durable trigger。
  normalized delivery狀態固定為 `pending | processing | retryable_failed | committed_unverified | processed |
  dead_letter`，保存payload digest、partition、source version、projection sequence、lease與錯誤。
- `HPROJ-RB-04 Receipt/readback`：v2 immutable receipt分開保存emitted occurrence set與active membership
  set的digest/count、projection sequence、alert fingerprint、expected readback digest與result state
  `projected | held_active`。commit後另append actual readback；只有receipt、state、snapshot、current alert、
  workflow與successor全部exact，delivery才由`committed_unverified`轉`processed`。
- `HPROJ-RB-05 Current alert`：重用`anomaly_current_alerts`，definition固定
  `HISTORICAL-BASELINE-ROOTS-001`／version `1`、source domain `historical_baseline`、source identity為
  umbrella identity、source version為case-local projection sequence。active count>0時open/reopen；0時只由
  fresh exact projection auto-resolve。display snapshot只含case、earliest blocked step、active count、typed
  repair referrals及projection fingerprint；不得重用`HISTORICAL-ORDER-001`或generic resolve。
- `HPROJ-RB-06 Replay/gap/recovery`：same trigger identity＋same payload只reconcile原delivery/receipt；different
  payload為integrity conflict。partition version gap、stale vector、lease loss、unknown owner、partial read或
  post-commit mismatch固定fail closed。retry只處理明確transient錯誤；超過該次execution package設定的
  `max_attempts`轉dead letter，沿用Anomaly Maintenance typed retry/supersede Q/P/A，不能靜默跳過。
- `HPROJ-RB-07 Compatibility/release`：不backfill、不重寫既有1010／1011資料，不刪舊table/index/trigger。
  以successor v2 tables／release保存新receipt、state、membership snapshot、delivery、checkpoint與readback。
  先唯讀確認任何非disposable target是否曾套用舊1011；若已套用，仍只走additive successor。舊descriptor
  hash drift不得以既有qualification冒充通過；新candidate建立新release identity並重跑全部DB gates。

`max_attempts`、lease duration與retry delay是每次execution package的`IMPLEMENTATION_DEFAULT`，不在本規格
固定數值；owner為projector runtime，revision trigger為真實worker calibration或operational policy變更。
`HISTORICAL-BASELINE-ROOTS-001`與definition version是已核准架構契約，不是execution default。

### 10.2 Transaction and failure boundary

worker claim使用短lease transaction；實際projection只有一個outer UoW，依case／delivery／alert順序鎖定，
fresh讀六owner vector後append occurrence/state、v2 receipt、active snapshot、current alert及必要workflow event，
再保存checkpoint並將delivery標為`committed_unverified`。commit後唯讀重算exact set／alert／receipt／successor
digest；第二個reconcile UoW只append readback並CAS delivery為`processed`。未知commit outcome只能以原trigger
reconcile，不能建立新identity。Domain失敗rollback全部projected state；post-commit readback失敗不得回滾
已提交owner或projector transaction，delivery保持可對帳狀態。

### 10.3 Acceptance

- `HPROJ-RB-A1`：同一case依owner修復依序產生active membership 3→2→1→0；每版digest/count與rows exact。
- `HPROJ-RB-A2`：unavailable→terminal只由strictly-newer same-lineage event解除一筆；其他occurrence不變。
- `HPROJ-RB-A3`：owner regression建立新opened occurrence並使alert reopen；舊history不可變。
- `HPROJ-RB-A4`：duplicate delivery exact replay；different payload、version gap、out-of-order與stale vector零寫入。
- `HPROJ-RB-A5`：transient retry、lease expiry、attempt exhaustion、dead-letter人工retry/supersede可重播且不跳事件。
- `HPROJ-RB-A6`：commit後readback mismatch維持`committed_unverified`／outcome unknown；原identity修復後才processed。
- `HPROJ-RB-A7`：current alert definition/source/version/display/referral exact；只有0 active可auto-resolve。
- `HPROJ-RB-A8`：static chain、descriptor、read-only plan、fresh bootstrap、preserve-data candidate及developer
  acceptance全部PASS；任何必要gate未過時結論固定`DB_CHANGE_NOT_READY`。

### 10.4 Change inventory and exclusions

- `schema-only`：successor v2 receipt、occurrence state event、active membership snapshot、delivery、checkpoint、
  post-commit readback及其constraints/indexes/triggers；source為new provisional release candidate。
- `system-seed`：none；definition由code registry擁有。
- `business-row-backfill`：none；只處理新baseline／owner events。
- `destructive`：none；舊1011 objects保留但不作v2 current truth。
- `excluded`：`union_db`／production、existing-row rewrite、generic anomaly resolve、provider effect、另一台DB upgrade。

```yaml
spec_route:
  status: SPEC_READY
  specification: PROV-20260828-historical-baseline-projector-contract#10
  requirements: [HPROJ-RB-01, HPROJ-RB-02, HPROJ-RB-03, HPROJ-RB-04, HPROJ-RB-05, HPROJ-RB-06, HPROJ-RB-07]
  acceptance: [HPROJ-RB-A1, HPROJ-RB-A2, HPROJ-RB-A3, HPROJ-RB-A4, HPROJ-RB-A5, HPROJ-RB-A6, HPROJ-RB-A7, HPROJ-RB-A8]
convergence:
  status: READY
  blockers: []
```

## 8.1 Concrete owner adapter source-map correction（2026-08-28）

### 8.1.1 Existing Authority 可直接修正的 live-drift

- Step 10 `effective_generation` 由 Scheduling 擁有，不是 Orders；root 必須綁定
  current `scheduling_aggregates.effective_generation_id`、effective generation 與 rebuild event。
- observation `source_version` 接受合法 nonnegative owner version；不得把初始版本 0
  當成 unavailable。
- Step 9 confirmed dates、Step 10 assignment official dates 的 cardinality 來自 current
  `orders.service_days` 與 exact date/assignment set，不使用 31／100 任意上限。
- Staff Payables Step 11 保存每個 typed source-version observation，不壓成一筆 scalar。
- Matching `criteria_snapshotted` 以 schema enum 為準；`criteria_snapshot` 是 live-drift。

### 8.1.2 Candidate Pool exact event version

Candidate Pool 不需要新 DDL。每個 observation 使用自己的 authoritative append-only
event：`event_key` 為 source event identity，該 exact event `id` 為 numeric source version。
`candidate_pool` 使用同一 transaction 寫入、payload 包含 entry ID 的最早
`candidates_added`；contact/willingness 使用該 candidate 的 latest exact info/willingness event。
不得使用整池 `MAX(id)`、timestamp 或 fingerprint 代替 observation vector。

### 8.1.3 Contract Signing precedence 與已核准的 repair policy

current external session 存在時，只接受該 session 的 provider-neutral completion reports、
final controlled file 與 receipt。沒有 external session 時，legacy manual evidence 必須同時具備
`signed_return` document/media digest、payload `command=record_manual_*_contract_attestation` 的
`signed_received` event、manual method/reason/actor/correlation 與 matching receipt。普通
`signed_received` 或 1005 `manual_attested` row 都不能假裝成此 fallback。

舊 manual workflow 未 persisted Preview fingerprint；因此既有資料只能先由 adapter fail-closed readback，
不能直接宣稱人工修復閉環。2026-08-28 人工已核准新增 append-only recovery：不改寫舊 document/event，
以 current plan/commitment 與 controlled signed file 建立 recovery external session，再寫入完整
`manual_attested` report、Preview fingerprint、actor/reason/evidence 與 receipt。兩條 lineage
不一致時 fail closed。

```yaml
contract_legacy_manual_recovery:
  status: ADOPTED
  authority: human_explicit_2026-08-28
  schema_change_expected: false
  mutation: append_only_external_session_recovery
  forbidden: [rewrite_legacy_document, rewrite_legacy_event, infer_preview_fingerprint]
```

### 8.1.4 Legacy manual recovery 多命令可續跑契約

Recovery 不以單一跨 workflow 大交易包住所有月嫂、客戶與最終 PDF。每個
target 使用一次 Query → Preview → Apply，每次 Apply 只有一個 outer Unit of Work；
已提交的 staff report 保留在 `staff_reporting`，中斷後由 Query 回傳已完成與待補
target，不回滾已提交的正當歷史，也不得假稱 terminal。

- Query 必須同時回傳 current accepted/active plan、commitment、current document set、
  staff segments、client target，以及 legacy `signed_return` document/media digest、
  `signed_received` event、matching command receipt 與目前 recovery session/report 進度。
- Preview 為零寫入 fresh read；輸入固定為 target、legacy document/event/receipt identity、
  manual method 與 reason。它必須重驗同案、同 plan、scope、`signed_return`、media digest、
  event payload command、receipt/result snapshot、current plan/commitment/document set 與 target 未重複；
  回傳 recovery Preview fingerprint、expected session/status version、lineage 與 typed blockers。
- 首筆 staff Apply 可在當次 UoW 建立 deterministic external session 並 append report/receipt；
  後續 staff 及 client 各自一個 UoW。client 只能在所有 staff reports 與 commitment
  complete 後寫入；之後沿用 final PDF staging → Preview → Apply。
- recovery report 的 `source_payload_sha256` 保留 canonical legacy tuple digest 語意；
  `manual_evidence_sha256` 保留 legacy `media_assets.sha256`。現行 report receipt 的
  `preview_fingerprint` 依 schema 必須為 NULL，因此 recovery Preview fingerprint、legacy event/
  receipt/document identity、media digest、current plan/commitment/document-set 必須存入既有
  `result_snapshot.recovery`，`kind` 固定為 `contract_legacy_manual_recovery.v1`。
- HCAT adapter 必須重讀並對帳該 versioned recovery snapshot、legacy immutable tuple、
  current report/final controlled-file lineage；不可把 command fingerprint 或 source payload digest
  當作 Preview fingerprint。
- 同 idempotency key 與相同 canonical command 回原 receipt；同 key 或 source identity
  但 target、lineage、digest、reason 或 Preview fingerprint 不同為 typed mismatch。狀態、plan、
  commitment 或 document set stale 時要求重做 Query → Preview。
- 只有 session completed、final controlled-file/readback、final receipt、recovery snapshots 與
  Contract Signing 三組 owner observations 全部 exact，並完成 fresh 六 owner vector readback，
  才能交給 HCAT projector 判定 terminal。

```yaml
contract_legacy_manual_recovery_execution:
  status: SPEC_READY
  command_model: resumable_per_target_qpa
  preview_storage: contract_external_signing_receipts.result_snapshot.recovery
  controlled_evidence: immutable_contract_archive_media_digest
  schema_change_expected: false
```

## 9. Owner source-map 與 catalog-v2 採用修正（2026-08-28）

2026-08-28 人工明確裁決「核准 catalog-v2」。本節 proposed bundle 因此成為 current
contract；Authority 只涵蓋本文 owner descriptor／multi-observation vector、fingerprint、collection
predicate 與 referral 修正，不擴張 DDL、backfill、provider、production 或 generic resolve。

### 9.1 為何 v1 不能直接接 concrete adapter

fresh owner/schema 盤點確認，v1 catalog 的「每個 Step 恰好一個 scalar root」無法保存已核准
minimum-required-facts：

- Step 3 的 candidate contact 根屬 Scheduling／Matching；LINE 只擁有 delivery adapter。
- Step 5 的 customer decision 根屬 Matching Coordination；Orders 只消費其 projection。
- Step 9 的 confirmed service dates 根屬 Scheduling；Orders 只提供 terms/version。
- Step 8、10、11 各自需要多個 owner root；Step 6 也可能依 active matching segments 有多筆
  signed evidence。若把它們壓成一個 digest 加單一 scalar version，會遺失 exact owner
  identity/version vector，違反本文 §2.2～2.3 與 Global source-version contract。

這是 v1 catalog live-drift，不改變 11 步業務結果，也不授權 generic resolve。

### 9.2 建議採用的 catalog-v2 bundle

1. catalog entry 改為「一種 owner root descriptor」，同一步可有多個 descriptor；每個 descriptor
   可回傳一或多筆 typed observation。canonical ordering 固定為
   `(step, contract_id, root_identity, source_event_identity, source_version)`。
2. 每筆 observation 仍保存自己的 root identity、source event identity 與單調 source version；
   whole-vector fingerprint 包含全部 observations。不得以 `MAX(id)`、timestamp、顯示文字或
   一個跨 Domain scalar version 取代 source vector。
3. terminal predicate 先在 owner adapter 驗證每筆 observation，再由 descriptor 的 collection
   predicate 驗證 cardinality／all-required；unknown、empty-required、duplicate、cross-case 或
   source-version drift 固定 unavailable。
4. owner/source map 修正為：
   - Step 1 Orders：Order／Client identity 與必要 current Terms；
   - Step 2 Matching：candidate pool entries 與 canonical caregiver identities；
   - Step 3 Matching：candidate contact/info evidence；LINE delivery 歷史可免除且不是 terminal；
   - Step 4 Matching：selected candidate 的 latest willingness binding；
   - Step 5 Matching：unique selected staff binding 與 latest accepted customer decision；
   - Step 6 Contract Signing：每個 required staff segment 的 signed evidence；
   - Step 7 Client Finance：deposit obligation、ledger/bank allocation 與 settlement；
   - Step 8 Matching＋Contract Signing：unique caregiver binding、commitment、client signed evidence；
   - Step 9 Scheduling：current confirmed-date version 與完整 date collection；
   - Step 10 Orders＋Scheduling：actual start、effective generation、assignment 與 official dates；
   - Step 11 Orders＋Scheduling＋Client Finance＋Staff Payables：completion、official service、
     client settlement 與 staff payout typed readbacks。
5. Contract Signing source precedence：存在 current external signing session 時只接受該 session 的
   provider-neutral completion reports 與 final controlled-file readback；沒有 external session 的
   preserved historical case 才可讀既有 `manual_attested` completion。兩條皆存在但 identity／
   document／commitment lineage 不一致時 fail closed；不得 merge 成假 terminal。
6. repair referral 必須由 descriptor owner 回傳 typed target/capability；移除所有 entry 共用
   `orders.historical_review.remediate` 的 placeholder。UI 只能顯示 server 回傳的 referral。
7. 1011 已可用 descriptor／observation identity 保存同一步多筆 occurrence，本修正預期不新增 DDL；
   concrete implementation 前仍須以 schema contract test 證明 cardinality、successor與receipt
   exact-set readback 可表達，若失敗才另立 DB change package。

### 9.3 採用後的最小驗收

- v1 同一步唯一 entry／11-root 假設先以 fail-before-fix 測試證明失敗。
- v2 catalog、vector、fingerprint、earliest invalidated root 支援同一步多 descriptor／多 observation。
- Step 3／5／9 owner 修正後，LINE delivery、Orders status 或 receipt-only 均不能形成 terminal。
- Step 8／10／11 任一 owner observation 缺失時，只產生 exact missing occurrence，不清其他 occurrence。
- v1 persisted baseline history 保持 immutable；v2 只影響新的 projector intent，不 backfill、不改 1011
  released artifact。

```yaml
catalog_v2_amendment:
  status: ADOPTED
  authority_required: false
  authority: human_explicit_2026-08-28
  schema_change_expected: false
```

```yaml
convergence:
  status: READY
  blockers: []
```
