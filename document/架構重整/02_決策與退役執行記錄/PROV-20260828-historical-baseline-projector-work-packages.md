# Historical baseline projector work packages

- `package_set_id`: `PROV-20260828-historical-baseline-projector`
- `declared_status`: `approved`
- `package_status`: `PACKAGE_READY`
- `specification`: `PROV-20260828-historical-baseline-projector-contract-spec-gap.md`
- `spec_revision`: `CONFIRMED-2026-08-28`
- `storage_contract_revision`: `STORAGE-CONTRACT-20260828`
- `catalog_v2_amendment_status`: `ADOPTED`
- `convergence`: `READY`
- `authority_digest`: 2026-08-28 人工採用 spec 第2.2～2.7推薦候選；2.1 adopted-only eligibility與2.8 Task96 no-auth維持current Authority。
- `effect_ceiling`: 本機source、versioned additive schema及`lu_test_*`development驗收；不含`union_db`、production、provider、deployment、generic resolve或任意status editor。

## 1. Entry、necessity 與 reuse

| Candidate | Necessity | Source basis | Decision |
|---|---|---|---|
| versioned owner-root catalog＋whole-vector fingerprint | `required_now` | spec §2.2～2.3；H-01～H-03／H-06 | 各Domain descriptor＋Orders composition，`minimal-glue` |
| deterministic occurrence／umbrella＋successor projector | `required_now` | spec §2.4～2.6、§8；H-02／H-03／H-05／H-06 | 專屬baseline consumer與additive persisted projection，不重用generic resolve |
| typed API／React／Browser closure | `required_now` | spec §2.7～2.8；HOB-A1～A3／N1～N2 | copy-adapt existing owner Q/P/A/readback patterns |
| 新的業務公式、跨域scalar version、provider或production開關 | `remove` | non-goals/effect ceiling | reject |

Existing B1 1010 storage、Domain candidate、workflow與未註冊typed route可重用；其只證明baseline assertion，不得冒充minimum-facts projector。

## 2. `PKG-HCAT-OWNER-VECTOR`

- `objective`: 將Step 1～11必要根事實編成versioned owner descriptor，產生canonical whole-vector與server current-step projection。
- `requirements`: spec §2.1～2.3、§2.6；H-01、H-02、H-04、H-06。
- `in_scope`: contract id/version/step/owner/root identity+version/predicate/repair target；deterministic ordering/fingerprint；adopted-only eligibility；earliest invalidated root。
- `exclusions`: 不改owner業務公式；不寫anomaly、DB或UI；不接受前端ordinal。
- `preconditions`: 各descriptor只引用current Domain SSOT與typed read port；未知owner/predicate/repair target即fail closed。
- `steps`: 建立catalog→組合fresh root vector→產生fingerprint/minimum-facts→依owner successor/reversal重算current step。
- `safe_stop`: catalog/version/root identity不完整、cross-case、stale、unsupported predicate或readback unavailable時不產生terminal。
- `verification`: H-01 all-complete；H-02 single missing；H-04 evidence-unavailable不假造root；H-06 baseline immutable/current step regression；permutation-stable fingerprint與identity/version negatives。
- `evidence`: focused Domain/Subsystem stdout與canonical vector fixtures；不保存PII。

## 3. `PKG-HPROJ-OCCURRENCE`

- `objective`: 消費已提交baseline intent，以單一outer UoW投影occurrence、umbrella、successor與terminal readback。
- `dependencies`: `PKG-HCAT-OWNER-VECTOR`；B1 event/receipt/outbox exact；current anomaly registry邊界。
- `requirements`: spec §2.4～2.6、§8；H-02、H-03、H-05、H-06、HOB-N1。
- `in_scope`: deterministic identities；immutable occurrence、umbrella membership、successor relation、projector receipt；claim/replay/failure/dead-letter；3→2→1→0；verified newer successor與active/inactive readback。
- `exclusions`: generic claim/resolve不是terminal；不寫owner roots；不把receipt/provider success當完成。
- `schema_gate`: inventory已證明current structures只能部分重用；Scope／Change inventory／Static release／Descriptor／read-only plan／Engine與本機Developer acceptance PASS。專屬additive release 1011已註冊，system-seed／business-row-backfill／destructive均為none；另一台實體電腦的preserve-data升級驗收仍NOT_RUN，不得宣稱全部Developer acceptance完成。
- `steps`: late-bind schema part/release/descriptor→static assembly/plan gates→fresh＋preserve-data engine gates→claim exact intent→重讀event/receipt與fresh vector→atomic append occurrence/membership/successor/projector receipt→fresh readback→delivery metadata→developer-local acceptance。
- `retry/reconciliation`: same event+same payload回原receipt；same identity+different payload為data-integrity conflict；unknown保留active，只允許same intent retry。
- `verification`: H-03 umbrella只在最後terminal；H-05 strictly newer successor；missing owner/predicate/readback、stale、cross-case、malformed、partial write全fail closed。
- `evidence`: before/after occurrence counts、projector receipts、rollback/readback result，去敏並scoped。
- `persisted_contract`: occurrence使用typed available/unavailable observation；umbrella current projection重用`anomaly_current_alerts`但membership另存；exact set保存canonical identity digest/count；B1 source artifacts有FK binding；JSON不得替代identity/version/relation。

## 4. `PKG-HAPI-UI-RUNTIME`

- `objective`: 註冊完整typed Q/P/A，接通React owner referral與Task96 no-auth H-01～H-06。
- `dependencies`: `PKG-HCAT-OWNER-VECTOR`、`PKG-HPROJ-OCCURRENCE`；必要DB gates PASS。
- `requirements`: spec §2.7～2.8；HOB-A1～A3／N1～N2。
- `in_scope`: eligibility/catalog/vector/minimum facts/occurrence/repair target typed views；zero-write Preview；fresh Apply/readback；React full issue/owner action/outcome-unknown；API registration。
- `exclusions`: raw dict穿透；UI推導terminal；generic status editor；production auth/provider。
- `steps`: typed API與client decoder→React workbench→owner action交接→post-Apply owner/11-step/anomaly readback→versioned H scenarios→real no-auth Browser。
- `safe_stop`: typed schema drift、permission/stale/timeout/decode/outcome unknown時不顯示假成功；使用原idempotency identity對帳。
- `verification`: Module→Subsystem→Domain→Global；真MySQL/API/React/build；Browser H-01～H-06、same-key mismatch、stale、missing readback、no fake owner events。
- `cleanup`: 只清理或明確保留unique Task96 scenario rows；不全庫清理。

## 5. Coverage matrix

| Requirement / acceptance | Source | Package step | Direct oracle |
|---|---|---|---|
| H-01／HOB-A1 | spec §2.2～2.3、§3 | HCAT vector + HAPI Preview/Apply | Step N projection、full facts、zero fake events |
| H-02／HOB-A2 | spec §2.2、§2.4、§3 | HCAT missing entry + HPROJ occurrence + HAPI repair | exact owner/path/action；fresh repair後單筆inactive |
| H-03／A-02 | spec §2.4～2.5 | HPROJ umbrella/successor | 3→2→1→0；無一次清空 |
| H-04 | spec §2.2、§3 | HCAT evidence applicability + HAPI view | 只解除document-search；signed/paid/delivered仍false |
| H-05／HOB-A3 | spec §2.5 | HPROJ successor validation | newer owner version + terminal readback才解除 |
| H-06 | spec §2.6 | HCAT invalidation + HPROJ successor | baseline immutable；current step回server earliest root |
| HOB-N1／N2 | spec §5 | HPROJ retry + HAPI reconciliation | status/receipt-only不解除；same-key semantics exact |
| H storage exactness | spec §8 | HPROJ additive artifact＋DB gates | occurrence/member/successor/receipt可機械對帳；seed/backfill/destructive皆無 |

## 6. Readiness

Entry、necessity、source basis、coverage、failure behavior、dependencies、effect ceiling與evidence gates已完整；不在本文選擇DDH topology。

```yaml
package_status: PACKAGE_READY
blockers: []
```

## 9. 優先縮減與重新驗證門（2026-08-28 使用者裁決）

本節記錄目前候選實作的優先收斂方向。它是後續工作的執行限制，不表示本次 checkpoint
內的所有候選程式碼已獲得永久採用，也不直接授權刪除檔案、縮減 public contract、套用
資料庫 migration 或發布。這次 commit 只保存可檢閱的現況與裁決；實際清理前仍須先確認
current consumer、inbound references、migration／rollback 保留責任及 focused regression。

| 優先序 | 範圍 | 後續處置與判定門檻 |
|---|---|---|
| P0 | HPROJ 專用 delivery、retry、dead-letter、lease、checkpoint 與 worker stack | 暫停擴張。先逐項比較 `shared_kernel/durable_job_queue.py`、`infrastructure/mysql/background_job_repository.py` 與 `subsystems/jobs/durable_job_worker.py`；只有既有 durable-job 契約無法滿足且有正式 producer／consumer 證據時，才保留無法合併的最小差異。 |
| P0 | 完成狀態與 production wiring | 在第一個正式 owner-event producer、實際 production consumer，以及可操作的 repair action／deep-link 接通前，不得把 HPROJ runtime 標示為 completed。`HISTORICAL-BASELINE-ROOTS-001` 目前沒有可用 action，屬 completion blocker。 |
| P1 | HPROJ public API、Python dataclass、Pydantic、Zod 與 route mapping | 以實際 operator consumer 為準，優先只保留 delivery／reconciliation status、active count、earliest blocked step 與 repair referrals；未被 current consumer 使用的 receipt、digest、lease 及內部 lifecycle 欄位先證明必要性，否則縮減或留在內部模型。 |
| P1 | 一次性 Browser runner、raw receipt、重複 evidence | `scripts/run_task96_rpre_browser_scenario.py` 與只服務該 runner 的逐步 receipt 優先移往 ignored `scratch/` 或刪除；保留前須證明有 current consumer、稽核、migration／rollback 或不可重建需求。共享區只留最小 final receipt。 |
| P1 | runtime／環境修正 | Docker PATH、Windows／PowerShell、Vite、reset、dotenv 載入順序與 `wait_for_db` 等全域啟動語意，後續必須與 anomaly／Domain 功能分開檢閱、驗證及提交，不能以 anomaly 驗收代替。 |
| P2 | repository 與 DB schema 體積 | 不以檔案行數直接機械拆分。先縮減重複 lifecycle、資料模型與未證明必要的 receipt／membership／delivery／checkpoint/readback 契約，再依保留下來的責任決定 repository 和六張表／十二個 trigger 是否仍必要。 |

明確保留的核心是：owner-specific Query／Preview／Apply 修復流程、純 deterministic historical
baseline projector、必要的 typed failure、fresh-fact readback、transaction boundary、focused tests，
以及 migration／rollback 真正要求的 schema/release evidence。最早的失控點認定為：原始目標
「所有異常都有 owner-specific、人工可完成的修復路徑」在尚未證明既有 durable-job 能力不足、
也尚未接通正式 producer 前，擴張成新的通用六 owner event-processing platform。後續修改必須
從原始異常修復驗收重新推導最小範圍，不得從目前候選平台的既成形狀反推需求。

## 6.1 Concrete owner adapters task-pack correction（2026-08-28）

- `entry`: spec §8.1.1～8.1.2；既有 Authority 可執行的 source-map，不新增 DDL。
- `status`: `approved`；2026-08-28 人工已核准 Contract legacy append-only recovery mutation；
  incomplete legacy evidence 在 recovery 完成前仍回 typed unavailable。
- `shared_boundary`: 六個 owner adapters 使用同一 borrowed connection；Query/Preview
  唯讀，Apply/projector fresh read 由 outer UoW 傳入 locked mode；adapter 不
  begin/commit/rollback/close。
- `write_set`:
  - `domains/orders/historical_operational_baseline.py`（owner/cardinality/version live-drift）；
  - `subsystems/orders/historical_baseline_owner_vector.py`（explicit read mode propagation）；
  - `infrastructure/mysql/matching_coordination_repository.py`（schema-defined
    `criteria_snapshotted` event enum live-drift）；
  - `infrastructure/mysql/historical_baseline_*_owner_adapter.py` 六個 owner-specific adapters；
  - owner focused/integration tests 與 existing catalog/vector regressions。
- `acceptance`: 21 descriptors 的 exact RI/EI/SV，multi-owner/multi-observation complete set，
  Matching cross-descriptor completeness，Contract precedence，typed unavailable/referral，same-connection
  lock propagation，permutation-stable fingerprint，真 `lu_test_*` MySQL readback。
- `excluded`: legacy recovery mutation/API/UI，1011/DDL/backfill，production/provider。

```yaml
package_status: PACKAGE_READY
blockers: []
```

## 6.2 Contract legacy manual recovery task-pack correction（2026-08-28）

- `entry`: spec §8.1.3；2026-08-28 人工明確核准 append-only recovery。
- `status`: `approved`。
- `objective`: 對缺少 persisted Preview fingerprint 的 preserved historical manual signing，建立
  可驗證的新 recovery lineage，讓 Contract Signing owner readback 可在不改寫歷史資料下 terminal。
- `write_set`: Contract Signing recovery Q/P/A、repository/composition、typed API、React owner referral、
  focused tests及 `lu_test_*` integration scenarios；若 current schema 已可完整表達則不得新增 DDL。
- `required behavior`: 採每個 target 獨立 Query／Preview／Apply 的 resumable saga；首筆 staff
  Apply 建立 deterministic recovery external session，後續 staff、client 各自 append 完整
  `manual_attested` report 與 receipt，最後沿用 final PDF staging／Preview／Apply。legacy
  `media_assets.sha256` 為 immutable controlled evidence；recovery Preview fingerprint 與 legacy/current
  lineage 存於既有 `result_snapshot.recovery` versioned JSON，不冒充 command/source digest。
- `safe_stop`: legacy/current lineage conflict、文件/plan/commitment漂移、stale fingerprint、cross-case、
  missing controlled file或post-commit readback不完整時不得假成功；同 key 只能 exact reconcile。
- `forbidden`: 改寫 legacy document/event、推測 Preview fingerprint、generic resolve、provider success、
  `union_db`／production／backfill。
- `verification`: fail-before-fix legacy unavailable；Q/P zero-write；Apply/replay/stale/conflict；真
  `lu_test_*` before/after；no-auth API/Browser完整人工修復與owner重新投影。

```yaml
package_status: PACKAGE_READY
blockers: []
```

### 6.2.1 `PKG-HCAT-LEGACY-RECOVERY-REACT`

- `status`: `in-progress`；`dependency`: recovery backend final r12 fresh PASS。
- `scenario`: 既有歷史人工簽回缺少現行 recovery lineage 時，操作者在訂單的外部簽約工作台逐一補齊
  未完成 staff、再補 client，最後沿用既有 final PDF staging／Preview／Apply；不得要求操作 generic resolve。
- `write_set`: `ui_react/src/api/orders/contract_external_signing_client.ts`、
  `ui_react/src/components/ContractExternalSigningActions.tsx`及其直接 tests；不改 schema、owner rules、
  provider、production或 legacy rows。
- `typed client`: strict decode recovery Query／Preview／Apply；target scope/cardinality、合法state、
  case/segment/legacy document-event-receipt、media digest、session/status、Preview fingerprint與receipt
  identity全部綁定；raw dict不得進入render。
- `operator flow`: 只列server Query回傳且`reported=false`的target；reason/method須人工輸入；Preview先
  顯示current與legacy lineage、blockers及明確確認，才可Apply。same-key outcome unknown只用原identity
  查receipt/reconcile，不換key盲送。
- `fresh readback`: 每次Apply後重新Query同案並顯示remaining/reported targets、session/status；staff未全
  完成時client保持disabled；全部reports完成後明確導向同頁既有final PDF流程；不得以callback或HTTP 200
  冒充HCAT terminal。
- `acceptance`: strict/adversarial client tests、staff→client resume UI tests、stale/mismatch/outcome-unknown、
  fresh Luna/high、`lu_test_*` no-auth API與真Browser完整流程，最後再回讀六owner/HCAT projection。

```yaml
package_status: PACKAGE_READY
blockers: []
```

## 6.3 HPROJ persistence semantic-audit correction（2026-08-28）

- `package_id`: `PKG-HPROJ-PERSISTENCE-V2`；`status`: `approved`。
- `objective`: 依 spec §10 將 pure projector 接到可重播的 append-only persistence，使六 owner 逐筆
  修復後 active membership 可由 3→2→1→0，並正確更新、auto-resolve 或 reopen baseline current alert。
- `requirements`: `HPROJ-RB-01`～`07`；`acceptance`: `HPROJ-RB-A1`～`A8`。
- `authority_digest`: 2026-08-28 人工「1011核准重建」；只涵蓋未發布 projector successor candidate、
  local/disposable 驗證與既有 owner event consumer，不含 `union_db`、production、backfill、reset 或 switch。
- `specification`: `PROV-20260828-historical-baseline-projector-contract#10`，`SPEC_READY`／convergence READY。
- `dependencies`: catalog-v2 pure projector與六owner adapters；read-only applied-target inventory；canonical
  migration chain late-bind新provisional identity。非disposable target若已套舊candidate，只走additive successor。
- `in_scope`: pure projector emitted/active-set語意；v2 occurrence state、receipt、membership snapshot、
  delivery/checkpoint/readback schema；baseline與六owner event source adapters；worker/reconcile；typed current
  alert與Anomaly Maintenance dead-letter integration；focused/property/concurrency/DB/API/Browser evidence。
- `excluded`: owner business rules、11-step結果、legacy row rewrite、system seed、business backfill、provider、
  `union_db`／production、另一台DB upgrade、generic resolve。
- `effect_ceiling`: tracked source與disposable/allowlisted `lu_test_*` owned scenarios。schema execution先只在
  disposable fresh/preserve candidate；developer-local replacement需七個DB gates全部PASS且另有current Authority。
- `execution_defaults`: 本次candidate暫定`max_attempts=5`、lease `60s`、retry base `15s`且cap `300s`；
  分類為`IMPLEMENTATION_DEFAULT`，owner為本package runtime，只在此次驗證有效，真實calibration或
  operational policy改變即重訂，不升格為product requirement。
- `steps`:
  1. 唯讀盤點舊1011 applied targets、current release/hash/descriptor exactness與六owner committed event sources。
  2. 修pure projector：分開emitted occurrence set與active membership set，對齊result state與exact digests/counts。
  3. late-bind additive successor schema/release：保留舊objects，新增v2 state/receipt/snapshot/delivery/checkpoint/readback，
     同步assembly、descriptor、manifest、catalog與read-only plan。
  4. 建立source-specific checkpoint adapters；只讀已提交baseline/owner events並normalize durable delivery；
     duplicate、gap、out-of-order與different-payload fail closed。
  5. 建立single-UoW projector worker與post-commit reconcile，寫current alert與typed workflow event；dead letter
     只透過既有Anomaly Maintenance Q/P/A retry/supersede。
  6. 接HOB-E API/React fresh readback；UI只顯示server typed referral/count/state，不提供generic resolve。
  7. 跑static→fresh bootstrap→preserve-data candidate→developer acceptance，再做`lu_test_*` no-auth API/Browser
     3→2→1→0、reopen、retry/dead-letter與outcome-unknown。
- `safe_stop`: owner event缺durable identity/version、source gap、non-disposable applied-state未知、descriptor/
  manifest drift、partial/unknown object、post-commit mismatch或current alert binding不exact時停止；不得重算
  既有qualification、跳event、掃描猜source或以UI/receipt-only宣稱terminal。
- `evidence`: 保留一份aggregate migration/final receipt與release artifacts；intermediate stdout、HTTP dump、
  plan/retry journal只放ignored scratch，完成後依規範清理。

| Requirement / Acceptance | Package step | Oracle |
|---|---|---|
| RB-01/A2/A3 | 2,3,5 | same-lineage newer resolution；regression新occurrence；history immutable |
| RB-02/A1 | 2,3,5 | snapshot rows與digest/count逐版exact 3→2→1→0 |
| RB-03/A4/A5 | 4,5 | duplicate/gap/lease/retry/dead-letter transition tests |
| RB-04/A6 | 2,3,5 | `committed_unverified`直到post-commit exact reconcile |
| RB-05/A7 | 5,6 | definition/source/version/display exact；0才auto-resolve；regression reopen |
| RB-06/A4/A5 | 4,5 | original identity replay；different payload zero-write conflict |
| RB-07/A8 | 1,3,7 | DB gate table全部PASS，否則`DB_CHANGE_NOT_READY` |

```yaml
package_route:
  status: PACKAGE_READY
  package: PKG-HPROJ-PERSISTENCE-V2
  blockers: []
```

## 6.4 HPROJ six-owner source runtime（2026-08-28）

- `package_id`: `PKG-HPROJ-SIX-OWNER-SOURCE-RUNTIME`
- `package_status`: `PACKAGE_READY`
- `objective`: 依 canonical spec §11 將 baseline confirmed 與六 owner 已提交 repair Apply，透過
  dedicated shared source stream／outbox 正規化為可重播 HPROJ trigger，完成正式 runtime 與 3→2→1→0。
- `requirements`: `HPROJ-RB-03`、`HPROJ-RB-06`、`HPROJ-SRC-A1`～`A5`。
- `acceptance`: `HPROJ-RB-A1`、`A3`～`A8`、`HPROJ-SRC-A1`～`A5`。
- `authority_digest`: 2026-08-28 人工明確核准 dedicated shared HPROJ source stream／outbox；只涵蓋
  tracked source、additive schema、allowlisted `lu_test_*`、no-auth API／Browser，不含 `union_db`、
  production、legacy backfill、reset、switch、provider、generic resolve或owner business-rule變更。
- `specification`: `PROV-20260828-historical-baseline-projector-contract#11`；shared stream架構與
  §11.4 `catalog-v2.1` source semantics均已人工核准，`SPEC_READY`／convergence READY。
- `entry_baseline`: catalog-v2的21 descriptors／repair capabilities；1010 baseline exact event／receipt／outbox；
  1013 delivery/checkpoint/readback；人工核准的每-case dedicated stream contract。結案須同時對照此baseline與
  final canonical spec，不因schema／code／tests彼此一致就推定業務完成。
- `execution_constraints`:
  - `lu_test_*` allowlist為`EXECUTION_AUTHORITY`，owner為2026-08-21/28人工裁決，只限本Task 96驗收。
  - 每partition從0開始與strict `+1`為已核准`ARCHITECTURE_DECISION`，owner為spec §11，若stream
    partition語意改變即重新裁決。
  - worker `max_attempts=5`、lease 60s、retry 15s/cap 300s仍為`IMPLEMENTATION_DEFAULT`，只限本candidate，
    operational calibration改變即失效。

### 6.4.1 Necessity／source basis／reuse

Current Spec Pipeline gate：21 descriptors已完成唯讀mapping；其中13項有可直接沿用或強語意對應的owner
Apply，另8項依已核准canonical spec §11.4修正為formal Q/P/A、receipt或derived／router source語意。
`catalog-v2.1`已於2026-08-28人工核准；可進入ordered step 2，但release identity仍須由integration writer
在fresh chain上late-bind，不得預先假設1015。

| Step | Necessity | Source basis | Reuse decision |
|---|---|---|---|
| 21 descriptor→formal repair Apply inventory | `required_now` | catalog-v2 `repair_capability`與live owner Q/P/A；缺一entry會漏trigger | `reuse` typed catalog；exact mapping只接受owner UoW證據 |
| shared stream state＋outbox additive schema | `required_now` | spec §11 per-case contiguous source version；現有owner outbox不共通 | `minimal-glue` additive successor；無seed/backfill/destructive |
| baseline 1010 source adapter | `required_now` | existing exact event／receipt／outbox join | `reuse`；不複製或重寫1010 |
| six owner same-UoW envelope emission | `required_now` | spec HPROJ-SRC-A1；現況沒有共同durable repair source | `copy-adapt` shared typed port；owner仍擁有event/receipt |
| source claim／normalize／runtime composition | `required_now` | 1013 worker只接受typed trigger，尚無source poller | `minimal-glue` source-specific verification＋bounded consumer |
| dead-letter／reconcile UI readback | `required_now` | RB-06/A5-A7；既有1013 delivery/read API/React | `reuse`，不新增generic resolve |
| legacy row backfill、read-model scan、`MAX(id)`／timestamp inference | `remove` | spec exclusions與gap oracle | `reject` |

### 6.4.2 Ordered execution contract

1. 先完成`PKG-HISTORICAL-PAYMENT-OWNER-SETTLEMENT`：銀行對帳單優先；pre-system historical fallback依
   Client receivable／client refund／client subsidy return／staff payout分別建立owner Q/P/A。客戶已付款但
   Staff未付款的readback必須保持Step 11 false；未通過前不得開始HPROJ finance/staff adapter施工。
2. 以catalog-v2.1 21 descriptors的`repair_capability`逐項對到現有正式 owner Query／Preview／Apply、唯一outer
   UoW、committed event／receipt；Client／Staff mapping必須包含上述新owner events。無exact mapping者立即
   回到Spec Pipeline，不得自行選相似event或由Orders status／historical workbook推定付款。
3. Late-bind additive successor release：shared partition stream state與immutable source envelope/outbox；同步
   schema part、assembly、manifest、descriptor、generated release與developer upgrade chain。Change inventory固定
   schema-only，system seed／business backfill／destructive均為無。
4. 建立typed emission port；Orders、Matching、Contract Signing、Scheduling、Client Finance、Staff Payables
   的mapped formal repair Apply在原owner UoW內配置per-case/per-source連續version並append envelope。任何一筆
   owner event／receipt／envelope失敗即整個Apply rollback；exact replay不新增。
5. 建立1010 baseline與六owner source-specific adapter；claim後重讀event／receipt／envelope exact binding，
   normalize `HistoricalBaselineProjectorTrigger`。Missing、cross-case、identity/payload mismatch、gap、stale、
   out-of-order均fail closed、零projection write。
6. 將bounded consumer接入既有maintenance worker/runtime，明確管理connection lifetime；沿用1013
   delivery/checkpoint、retry/dead-letter與post-commit reconcile，不在HTTP request內假同步完成。
7. 先跑static／property／failure／concurrency focused tests，再跑fresh bootstrap與preserve-data candidate；
   所有schema gates PASS後才建立唯一 `lu_test_*` owner-repair scenario。
8. 以正式owner APIs依序使active membership 3→2→1→0；至少包含Client terminal／Staff open時不歸零、
   client subsidy return不誤投Government、最後Staff terminal才歸零。再驗regression reopen、duplicate、different payload、
   gap、lease expiry、retry exhaustion、dead-letter與committed-unverified；API／React／no-auth真Browser及DB
   before-after/readback全部exact。
9. 同步aggregate receipt與current task ledger；configured developer DB／另一台電腦未通過前維持
   `DB_CHANGE_NOT_READY`，不得以disposable candidate取代Developer acceptance。

### 6.4.3 Safety／handoff／evidence

- `dependencies`: approved §11、catalog-v2.1、1010 exact source、1013 persistence/API/React bounded slice，
  以及`PKG-HISTORICAL-PAYMENT-OWNER-SETTLEMENT`先完成Client Finance／Staff Payables歷史owner Q/P/A、
  persistence、receipt/outbox與source envelope；HPROJ不得先自行實作付款shortcut。
- `safe_stop`: descriptor無formal Apply、owner UoW不明、existing source identity/version不唯一、schema
  partial/drift、cross-case、version gap、payload mismatch、post-commit mismatch、target非`lu_test_*`時停止。
- `transaction`: owner mutation與envelope共用該owner唯一outer UoW；projector在已提交後的獨立UoW執行；
  外部失敗不回滾已提交owner transaction，也不得偽造projector success。
- `reconciliation`: same identity＋same payload只重播原delivery；different payload為integrity conflict；
  committed-unverified只以原trigger identity reconcile。
- `cleanup`: 只清理或保留明確scenario-owned rows；不全庫清理、不刪既有disposable evidence DB。
- `evidence`: final receipt保留descriptor→Apply mapping、DB gate table、fresh/preserve receipts、runtime
  before-after、Browser readback與console；原始dump/journal只放ignored scratch。

### 6.4.4 Bidirectional coverage

| Requirement／Acceptance | Source | Package step | Direct oracle |
|---|---|---|---|
| HPS-A3-A10前置 | historical payment spec／owner package | 1 | Client／Staff付款分離、補助退款歸Client、Step11不跨owner推定 |
| RB-03／SRC-A1 | spec §11；catalog repair capabilities | 2～4 | 21 descriptors全覆蓋；owner event/receipt/envelope同UoW commit或全rollback |
| RB-03／SRC-A2-A3／RB-A4 | per-case stream architecture | 3～5 | version 0→1；exact replay；different payload/gap/stale/cross-case零寫入 |
| RB-06／RB-A5-A7 | 1013 delivery/checkpoint/readback | 5～8 | retry/dead-letter/reconcile/alert exact，0 active才auto-resolve |
| RB-A1/A3／SRC-A4 | historical import repair outcome | 7～8 | formal owner APIs 3→2→1→0；Client terminal／Staff open不歸零；regression reopen |
| RB-07/A8／SRC-A5 | Global DB gates | 3,7,9 | static、descriptor、plan、fresh、preserve、developer acceptance table |

```yaml
package_route:
  status: PACKAGE_READY
  package: PKG-HPROJ-SIX-OWNER-SOURCE-RUNTIME
  blockers: []
```

## 7. Execution ledger（2026-08-28）

- `PKG-HCAT-OWNER-VECTOR-domain`: `completed`。Step 1～11 catalog、root vector、whole-vector
  fingerprint、H-04 unavailable guard與typed H-06 invalidation boundary已完成。
- current evidence：主代理H/R cross-regression的一部分`81 passed`；fresh Luna/high H r4 `52 passed`，
  P0=0、P1=0。
- `PKG-HCAT-OWNER-VECTOR`: 仍`in-progress`；typed owner read ports與whole-vector subsystem composition
  的純composition slice已完成；六個owner concrete read adapters尚未接線，不能外推整包完成。
- `PKG-HCAT-CATALOG-V2-domain`: `completed`。Canonical 21 descriptors、Step 3/5/9 owner
  修正、Step 6/8/10/11 multi-owner，multi-observation collection，canonical ordering/fingerprint、
  owner referral與typed unavailable已完成；v1 persisted contract保持相容。主代理`59 passed`；
  第二輮fresh Luna/high re-verifier為P0/P1/P2=0，22項adversarial probes與100次隨機排列PASS。
- `PKG-HCAT-CATALOG-V2-vector`: `completed`。v2 typed request預設版本、mapping／iterable-pair
  owner ports、duplicate／unknown／missing／malformed fail-closed，multi-observation canonical
  collection與whole-vector fingerprint已完成；v1 request預設仍為1。主代理`75 passed`；
  fresh Luna/high re-verifier P0/P1/P2=0，21 descriptors、adversarial probes與100次隨機排列PASS。
  這是bounded composition slice；六個owner concrete read adapters仍未接線。
- `PKG-HCAT-MATCHING-EVENT-ENUM`: `completed`。Matching initial criteria event 已對齊
  released `criteria_snapshotted`；八個 Apply command 都顯式對應 schema enum，未支援
  command fail closed，不再 fallback 成 `rematch_required`。主代理`71 passed`；
  fresh Luna/high P0/P1/P2=0。
- `PKG-HCAT-ADAPTER-BOUNDARY`: `completed`。Step 10 effective generation owner、zero-based
  observation version、dynamic date/staff-payout collection cardinality與explicit whole-vector locked read mode
  已對齊 source-map；v1 相容。主代理`78 passed`；fresh Luna/high `98 passed`，
  P0/P1/P2=0，100次隨機排列PASS。六個concrete adapters仍是後續包。
- `PKG-HCAT-ADAPTER-scheduling`: `completed`。confirmed-date、effective generation、
  assignment-owned official dates 與 BusinessClock official-service observations已完成；主代理
  `85 passed`，fresh Luna/high cross-focused `170 passed`，P0/P1/P2=0。真MySQL readback
  仍屬六owner integration gate，不由此source slice取代。
- `PKG-HCAT-ADAPTER-orders`: `completed`。Step 1／10／11 exact Orders event、receipt、version、
  1008 no-op adoption及canonical lifecycle lineage已完成；第一輪fresh finding已修正，主代理
  `96 passed`，final fresh Orders `18 passed`／cross-suite `100 passed`，P0/P1/P2=0。真MySQL
  readback仍屬六owner integration gate，不由此source slice取代。
- `PKG-HCAT-ADAPTER-matching`: `completed`。Step 2～5／8 exact schema/payload lineage、
  cardinality、stale customer decision、candidate set及typed source tuple已完成；第一輪fresh
  5個P1／2個P2已修正，主代理`107 passed`，final fresh focused `11 passed`、cross `64 passed`、
  real-shaped probes `7/7 PASS`，P0/P1/P2=0。真MySQL readback仍屬六owner integration gate。
- `PKG-HCAT-ADAPTER-staff-payables`: `completed`。Step 11 多staff/version exact row-set、合法
  version 0及partial-payment nonterminal已完成，無MAX/scalar collapse；主代理`90 passed`，fresh
  focused `12 passed`、cross `120 passed`、reader/schema `69 passed`，P0/P1/P2=0。compact
  `db/schema.sql`缺該表組標記為既有live-drift；真MySQL current-schema readback仍屬六owner integration gate。
- `PKG-HCAT-ADAPTER-client-finance`: `completed`。Step 7／11 deposit、formal incoming bank＋receipt、
  multi-allocation、partial nonterminal、obligation event與exact reducer lineage已完成；第一輪fresh
  5個P1／2個P2已修正，主代理`125 passed`，final fresh `86 passed`，P0/P1/P2=0。真MySQL
  readback仍屬六owner integration gate，不由此source slice取代。
- `PKG-HCAT-ADAPTER-contract-signing`: `completed`。Step 6／8 external session、reporter、current
  document set、session version、accepted/active plan及final PDF exact lineage已完成；第一輪fresh
  4個P1已修正，主代理`128 passed`，final fresh focused `22 passed`、cross `81 passed`、
  signing/PDF `41 passed`、adversarial `14 PASS`，P0/P1/P2=0。Legacy Preview fingerprint維持typed
  unavailable；append-only recovery已核准但尚未實作，真MySQL readback仍屬六owner integration gate。
- `PKG-HCAT-CONCRETE-OWNER-ADAPTERS`: `completed`（source／focused）。Scheduling、Orders、Matching、
  Contract Signing、Client Finance、Staff Payables六個adapter均已通過fresh verifier；下一個必要gate為
  同一borrowed connection composition與真`lu_test_*` current-schema readback。本狀態不代表projector、
  API、React、Browser或legacy recovery完成。
- `PKG-HCAT-SIX-OWNER-COMPOSITION`: `completed`（source／negative runtime）。Exact六owner、同一
  borrowed connection、catalog-v2與lock propagation已完成；真MySQL先揭露Staff typed event/version
  drift並修正。主代理final`174 passed`；fresh static與兩個`lu_test_*` mixed/canonical-current negative
  readback均P0/P1/P2=0，21 collections／64字fingerprint且無storage drift。Adopted-positive與projector
  仍`NOT_RUN`，不得由此外推整包完成。
- `PKG-HCAT-LEGACY-RECOVERY-backend`: `completed`（source／fresh E3）。每 target
  typed Query／Preview／Apply、fresh legacy/current lineage、首筆 staff deterministic activation、
  每次單一 outer UoW、`result_snapshot.recovery.v1`、exact replay/mismatch/stale、
  final PDF 後 HCAT adapter exact terminal 與 typed API 已完成；不改 schema/legacy rows。
  歷次fresh findings已完成scope/session/segment/command/document lineage、target cardinality、legacy tuple
  all-or-none、unknown scope、malformed persisted receipt/evidence與typed API fail-closed tightening；主代理
  final cross `106 passed`。fresh Luna/high r12 focused `59 passed`、cross `131 passed`、18組adversarial
  probes、compile/diff-check均PASS，P0/P1/P2=0。遠端commit `a8565d4`已解除1011 digest blocker；真
  `lu_test_*`／React／Browser尚為`in-progress`，不得外推整包完成。
- `PKG-HCAT-LEGACY-RECOVERY-REACT`: `in-progress`（React與兩方歷史簽回 runtime PASS）。Client／UI
  exact 綁定case、session、command、segment、receipt與next status version；outcome-unknown只用原identity
  reconcile。主代理focused `28 passed`，fresh Luna/high r6 PASS、P0/P1=0。`115960401`在
  `lu_test_task96_scenarios_20260827`以no-auth完成staff 0→1、client 1→2；same-key client replay
  `replayed=true`，DB readback只有兩筆report／receipt，legacy document/event/receipt lineage未改寫。
  真Browser 5183已可搜尋completed歷史案件並開啟契約工作台；預設清單仍只查unfinished，搜尋才查all。
  既有legacy contract completion使final PDF Preview以`contract_completion_already_recorded` fail closed，
  不得將此既有根事實改寫或以假完成繞過；六owner/HCAT terminal re-projection仍`NOT_RUN`。
- `PKG-HPROJ-OCCURRENCE-pure`: `completed`。Deterministic occurrence／umbrella membership／
  same-lineage strictly-newer successor／receipt／outbox純投影已完成；forged prior P1修正後主代理
  `66 passed`，fresh focused`20 passed`＋4 forged probes＋1000 permutations，P0/P1/P2=0。
  Persistence仍`NOT_RUN`；1011 descriptor／manifest／qualification已由遠端commit `a8565d4`統一為
  `5f01…75f3`，membership/projector delivery語意與runtime驗收仍未完成。
- subsystem evidence：主代理H/R cross-regression `105 passed`；fresh Luna/high H r4 focused
  `41 passed`＋adversarial probes，P0=0、P1=0。
- `PKG-HPROJ-OCCURRENCE-schema`: `completed`。additive part 1011、release manifest、owned-object
  descriptor、fresh assembly、cutover catalog與generated full release已完成；fresh Luna/high static
  review為P0=0／P1=0。projector repository／worker／真MySQL與readback仍`not_run`，不得把schema
  slice外推為整包完成。
- `PKG-HPROJ-PERSISTENCE-V2`: `in-progress`（schema／persistence／API／React／engine bounded slice
  `completed`）。Additive 1013、delivery/checkpoint、兩個UoW post-commit readback、retry/dead-letter、
  typed read-only API與Anomalies Drawer readback已完成；receipt現保存canonical emitted occurrence
  identities，逐筆identity／count／digest可exact核對。主代理integrated focused `73 passed`；React
  `19 passed`與production build PASS。Fresh bootstrap r3為140 parts／377 triggers／valid；preserve-data
  r2為1013 owned objects `exact`、`view_mismatches=0`、status `verified`。Fresh Luna/high source inventory
  另確認baseline confirmed有durable event／receipt／outbox，但六owner committed repair source並無共同
  durable trigger契約，canonical monotonic source version亦未定義；不得掃描或以其他用途outbox猜來源。
  因此正式runtime、真MySQL 3→2→1→0及Browser仍為`BLOCKED_SOURCE_CONTRACT`，需先由Spec Pipeline
  收斂owner Apply同一UoW的typed HPROJ source emission與版本規則。
- `PKG-HPROJ-OCCURRENCE`: `in-progress`；`PKG-HAPI-UI-RUNTIME`: `not_run`。
- 1011 reconciliation addendum：遠端commit `a8565d4`已採用current descriptor，manifest與published
  qualification均綁定`5f01…75f3`；舊`0c16…ed2e` blocker與未裁決Spec Pipeline receipt已stale，不再作current gate。
- HPROJ DB gates：Scope／Change inventory／Static release／Descriptor／read-only plan／Engine／本機
  Developer acceptance `PASS`；另一台實體電腦Developer acceptance `NOT_RUN`，總結仍為
  `DB_CHANGE_NOT_READY`。runtime必須在同一UoW以canonical
  membership重算exact set digest／count並於fresh readback核對，不能只信receipt欄位。
- receipts：`03_追蹤清單與證據/evidence/2026-08-28_task96_hcat_rpre_domain_slice_receipt.md`、
  `03_追蹤清單與證據/evidence/2026-08-28_task96_hcat_rpre_subsystem_slice_receipt.md`、
  `03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_hproj_rpre_static_release_receipt.md`、
  `03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_1011_engine_qualification_receipt.md`、
  `03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_local_noauth_runtime_receipt.md`、
  `03_追蹤清單與證據/evidence/2026-08-28_task96_hproj_v2_persistence_api_react_engine_receipt.md`。

## 8. Catalog-v2 amendment task pack（adopted 2026-08-28）

- `entry`: spec §9 adopted bundle。
- `authority`: 2026-08-28 人工明確核准 catalog-v2；只採用 spec §9 的 owner descriptor、
  multi-observation vector、collection predicate、fingerprint與owner referral contract。
- `status`: `approved`；既有 domain、subsystem、1011 schema 與 LDU engine evidence不重做。
- `execution`: Domain descriptor/collection slice `completed`；vector composition已進入序列寫入；
  concrete owner adapters、HPROJ/API/React/Browser 仍`not_run`。
- `reason`: v1 的 one-step／one-scalar-root 假設會遺失 Step 6／8／10／11 多 owner observations，
  且 Step 3／5／9 owner 與正式規格不一致。
- `after_adoption_write_set`:
  - `domains/orders/historical_operational_baseline.py`：catalog-v2 descriptor／collection contract；
  - `subsystems/orders/historical_baseline_owner_vector.py`：多 descriptor／observation composition；
  - owner-specific read adapters 與 focused tests；
  - 只在 static contract 證明 1011 不足時另立 schema package；不得直接改 1011。
- `fail_before_fix`: 同一步重複 descriptor、Step 3／5／9 owner drift、Step 8／10／11 partial vector、
  external/manual signing conflict、placeholder capability。
- `acceptance`: deterministic vector/fingerprint、owner-specific referral、typed unavailable、
  no fake delivery/status/receipt terminal、v1 history immutable。
- `excluded`: HPROJ writes、API／React／Browser、DDL、backfill、production、provider。

```yaml
package_status: PACKAGE_READY
blockers: []
```
