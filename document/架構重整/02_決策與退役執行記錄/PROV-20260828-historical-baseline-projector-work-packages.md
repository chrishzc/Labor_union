# Historical baseline projector work packages

- `package_set_id`: `PROV-20260828-historical-baseline-projector`
- `declared_status`: `approved`
- `package_status`: `PACKAGE_READY`
- `specification`: `PROV-20260828-historical-baseline-projector-contract-spec-gap.md`
- `spec_revision`: `CONFIRMED-2026-08-28`
- `storage_contract_revision`: `STORAGE-CONTRACT-20260828`
- `catalog_v2_amendment_status`: `BLOCKED_AUTHORITY`
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

## 6.1 Concrete owner adapters task-pack correction（2026-08-28）

- `entry`: spec §8.1.1～8.1.2；既有 Authority 可執行的 source-map，不新增 DDL。
- `status`: `approved`；Contract legacy repair mutation 另為 `AUTHORITY_REQUIRED`，不阻擋
  adapters 對 incomplete legacy evidence 先回 typed unavailable。
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
  unavailable；append-only recovery仍待Authority，真MySQL readback仍屬六owner integration gate。
- `PKG-HCAT-CONCRETE-OWNER-ADAPTERS`: `completed`（source／focused）。Scheduling、Orders、Matching、
  Contract Signing、Client Finance、Staff Payables六個adapter均已通過fresh verifier；下一個必要gate為
  同一borrowed connection composition與真`lu_test_*` current-schema readback。本狀態不代表projector、
  API、React、Browser或legacy recovery完成。
- `PKG-HCAT-SIX-OWNER-COMPOSITION`: `completed`（source／negative runtime）。Exact六owner、同一
  borrowed connection、catalog-v2與lock propagation已完成；真MySQL先揭露Staff typed event/version
  drift並修正。主代理final`174 passed`；fresh static與兩個`lu_test_*` mixed/canonical-current negative
  readback均P0/P1/P2=0，21 collections／64字fingerprint且無storage drift。Adopted-positive與projector
  仍`NOT_RUN`，不得由此外推整包完成。
- subsystem evidence：主代理H/R cross-regression `105 passed`；fresh Luna/high H r4 focused
  `41 passed`＋adversarial probes，P0=0、P1=0。
- `PKG-HPROJ-OCCURRENCE-schema`: `completed`。additive part 1011、release manifest、owned-object
  descriptor、fresh assembly、cutover catalog與generated full release已完成；fresh Luna/high static
  review為P0=0／P1=0。projector repository／worker／真MySQL與readback仍`not_run`，不得把schema
  slice外推為整包完成。
- `PKG-HPROJ-OCCURRENCE`: `in-progress`；`PKG-HAPI-UI-RUNTIME`: `not_run`。
- HPROJ DB gates：Scope／Change inventory／Static release／Descriptor／read-only plan／Engine／本機
  Developer acceptance `PASS`；另一台實體電腦Developer acceptance `NOT_RUN`，總結仍為
  `DB_CHANGE_NOT_READY`。runtime必須在同一UoW以canonical
  membership重算exact set digest／count並於fresh readback核對，不能只信receipt欄位。
- receipts：`03_追蹤清單與證據/evidence/2026-08-28_task96_hcat_rpre_domain_slice_receipt.md`、
  `03_追蹤清單與證據/evidence/2026-08-28_task96_hcat_rpre_subsystem_slice_receipt.md`、
  `03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_hproj_rpre_static_release_receipt.md`、
  `03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_1011_engine_qualification_receipt.md`、
  `03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_local_noauth_runtime_receipt.md`。

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
