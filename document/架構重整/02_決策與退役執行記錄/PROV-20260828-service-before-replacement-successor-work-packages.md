# Service-before replacement successor work packages

- `package_set_id`: `PROV-20260828-service-before-replacement-successor`
- `declared_status`: `approved`
- `package_status`: `PACKAGE_READY`
- `specification`: `PROV-20260828-service-before-replacement-successor-contract-spec-gap.md`
- `spec_revision`: `CONFIRMED-2026-08-28`
- `storage_contract_revision`: `STORAGE-CONTRACT-20260828`
- `convergence`: `READY`
- `authority_digest`: 2026-08-28 人工採用 spec §3.1～3.6與§4 complete bundle，並明確「核准 RPRE API」採用§8.5 typed public contract；R-01～R-04/R-07既有行為不重開。
- `effect_ceiling`: 本機source、versioned additive schema及`lu_test_*`development驗收；不含actual-service改寫、`union_db`、production、provider、deployment或generic assignment/status旁路。

## 1. Entry、necessity 與 reuse

| Candidate | Necessity | Source basis | Decision |
|---|---|---|---|
| Scheduling replacement generation/event + exact supersession | `required_now` | spec §3.1～3.2、§8；R-01～R-04/R-07 | owner-specific additive persisted contract；不複製Matching/Assignment SSOT |
| server Q/P/A + idempotency/receipt/outbox/readback | `required_now` | spec §3.3～3.5 | copy-adapt current Scheduling Q/P/A/UoW patterns |
| Orders/React/Browser manual action | `required_now` | spec §3.6／§6／§8.8 | typed projection/minimal glue |
| LINE-request anomaly terminal | `conditional_deferred` | spec §8.8 | only after explicit LINE request event exists |
| 放寬generic assignment空service-date、改actual service、重算Finance/Payroll | `remove` | spec non-goals/safe stop | reject |

Current Matching `rematch_required` event/receipt可作intent evidence，但不是successor completion；current assignment、waiting lock、commitment與matching roots只能由owner ports消費。

## 2. `PKG-RPRE-OWNER-SUCCESSOR`

- `objective`: 在official/actual service=0時，以Scheduling-owned append-only replacement event建successor matching round與current projection。
- `requirements`: spec §3.1～3.5、§8；R-01～R-04、R-07、HOB-A6/A7。
- `in_scope`: Query facts；zero-write Preview root delta/reuse/resume step；fresh Apply；immutable replacement event、exact root relation、successor binding；strictly newer generation/event；exact retained/superseded/created root set；receipt/internal outbox/readback。
- `write_set`: Scheduling replacement lineage/current projection；successor matching round；R-03/R-04必要waiting-lock/effective-generation transition；immutable receipt/internal outbox。
- `exclusions`: actual-service、Orders terms、deposit/Finance/Payroll/provider、舊歷史改寫、原地替換staff id。
- `schema_gate`: inventory已證明現有generation/rebuild/receipt與Matching lineage只能部分重用；Scope／Change inventory／Static release／Descriptor／read-only plan／Engine與本機Developer acceptance PASS。Scheduling-owned additive release 1012已註冊，system-seed／business-row-backfill／destructive均為none；另一台實體電腦的preserve-data升級驗收仍NOT_RUN，不得宣稱全部Developer acceptance完成。
- `steps`: late-bind schema part/release/descriptor→static assembly/plan gates→fresh＋preserve-data engine gates→Query actual-service/versions/roots→Preview branch/root delta/reuse→fresh lock→append event/root relations/successor binding/receipt/internal outbox→fresh Scheduling/Matching/Orders readback→developer-local acceptance。
- `branch_oracles`: R-01 candidate only；R-02 accepted plan；R-03 lock/commitment/signback；R-04 assignment+zero service；R-07 successor+zero candidates blocked。
- `safe_stop`: any actual service→typed substitution referral/zero write；stale/cross-case/occupancy/unknown root/reuse proof/missing successor/readback/partial outcome→rollback或保留active。
- `retry`: same key+same payload回原receipt/readback；same key+different payload拒絕；unknown只same-key reconciliation。
- `verification`: pure branch/root delta；workflow UoW/replay/rollback；repository/API contract；disposable MySQL fresh/preserve gates if schema。
- `persisted_contract`: event保存zero-service proof與strict versions；root relation逐筆保存三種disposition並可重算receipt set digest/count；successor綁既有Matching round；outbox只指向Orders/Anomalies projection，不含provider effect。

## 3. `PKG-RPRE-PROJECTION-UI-RUNTIME`

- `objective`: 用replacement lineage/successor/current-step owner readback終止或轉換異常，並提供Orders/Anomalies人工操作入口。
- `dependencies`: `PKG-RPRE-OWNER-SUCCESSOR`；H current-step composition只在已核准H projector contract接通後整合；未接通時回typed unavailable而非假terminal。
- `requirements`: spec §3.6、§6、§8.5；R-01～R-04/R-07 runtime acceptance。
- `in_scope`: deterministic replacement projection/successor identity；typed API client；Orders React impact/reason/evidence/reuse/resume/readback；versioned scenarios/no-auth Browser。Anomalies entry只在explicit LINE request event存在時另包接入。
- `exclusions`: tracking resolve/receipt-only success/UI-selected step；C-05 generic case binding；provider/persisted-human gate。
- `steps`: projector/read model→spec §8.5 typed Q/P/A API/strict decoder→Orders exact-case entry→驗證Apply
  response內complete full owner readback→R scenarios→real Browser；不得為一般RPRE建立或自動關閉anomaly，
  也不得用已套用的舊scenario再Query取代canonical Apply readback。
- `api_write_set`: `api/schemas/service_before_replacement.py`、`api/routes/service_before_replacement.py`、
  `api/dependencies/service_before_replacement.py`、`api/main.py`及 focused tests；route 只組合既有
  Scheduling workflow/repository，不新增 Domain 規則或 raw-dict response。
- `terminal`: service=0；strictly newer event/prior binding；successor exists；old caregiver roots retained but non-current；server Step 2/3/4；Apply receipt與server post-commit readback完整對帳且`complete=true`；R-07維持concrete blocked successor。
- `safe_stop`: schema drift、permission、stale、timeout/decode/outcome unknown或readback unavailable不顯示成功。
- `verification`: API typed errors/readback；React拒絕receipt-only與不完整readback，成功後不重Query已消耗
  scenario；`lu_test_*` DB before/after；no-auth Browser R-01～R-04/R-07 + actual-service negative；無explicit LINE request時驗證anomaly零新增/零更新。
- `cleanup`: unique scenario identity與owned-row scoped cleanup/保留receipt；不清他人rows。

## 4. Coverage matrix

| Requirement / acceptance | Source | Package step | Direct oracle |
|---|---|---|---|
| R-01 | matrix/spec §3.2 | OWNER exact candidate delta | 只新增successor；其他candidate history retained |
| R-02 | matrix/spec §3.2 | OWNER plan/segment supersession | old accepted plan non-current；new round exact |
| R-03 | matrix/spec §3.2 | OWNER lock/commitment/signback transition | history retained；deposit untouched；successor exists |
| R-04 | matrix/spec §3.4 | OWNER replacement-specific zero-service representation | generic assignment invariant不放寬；resume step server-owned |
| R-07 | matrix/spec §3.6 | OWNER zero-pool + UI terminal projection | Step 2 blocked with concrete disposition；不復活舊staff |
| HOB-A6/A7 | controlling spec | OWNER service gate + PROJECTION readback | zero service replacement；any service substitution referral/zero write |
| stale/replay/unknown | spec §3.5／§5／§8.5.3 | OWNER idempotency + UI reconciliation | same-key exact；Apply complete readback為canonical observation；unknown無假成功且不重Query已消耗scenario |
| R storage exactness | spec §8 | OWNER additive artifact＋DB gates | event/root/successor/receipt/outbox可機械對帳；seed/backfill/destructive皆無 |

## 5. Readiness

Entry、necessity、source basis、coverage、failure behavior、dependencies、effect ceiling與evidence gates已完整；不在本文選擇DDH topology。

```yaml
package_status: PACKAGE_READY
blockers: []
```

## 5.1 Production loader task pack（approved）

- `entry`: spec §8.6。
- `status`: `approved`；2026-08-28 人工已核准 spec §8.6 source-map。實作完成並通過驗收前，
  dependency 仍須維持 honest 503，不得以 partial loader 假成功。
- `write_set`:
  - 新增 `infrastructure/mysql/service_before_replacement_loader.py`；
  - `infrastructure/mysql/service_before_replacement_repository.py`（typed loader handoff）；
  - `api/dependencies/service_before_replacement.py`（real composition）；
  - `api/routes/service_before_replacement.py`（typed Query construction）；
  - facts/matching loader、persistence、API 與 `lu_test_*` integration tests。
- `acceptance`: same connection/read mode，actual-service positive referral/future negative，predecessor identity，
  13-source tuple/criteria/package/event exact binding，R01～R04/R07 root set，Step2/3/4 reuse，
  missing/ambiguous/stale/partial zero-write，replay/readback exact。
- `composite source correction`: `candidate_binding` 為 current candidate pool exact set；`signback`
  的 canonical evidence owner 為 Contract Signing；`recipient_binding` 複合 schedule recipient snapshot
  與 LINE Identity current binding。1012 `owner_domain` 只表示 replacement relation transition owner，
  不轉移 source SSOT，不授權 Scheduling 改寫 Contract/LINE 根事實。
- `excluded`: Domain behavior、DDL/migration/backfill，Orders/Finance/Payroll writer，provider/production。

```yaml
package_status: PACKAGE_READY
blockers: []
```

## 8. Matching package compatibility task-pack correction（2026-08-28）

- `entry`: spec §9；修正現有 Matching reader 與 RPRE successor package 的 persisted-contract
  漂移，不改 schema 或 R scenario 結果。
- `required_now`:
  1. repository Apply 強制使用同一 UoW 的 fresh Matching loader，驗證 canonical criteria
     fingerprint、source tuple、parent package 與 source-event binding；
  2. successor package 使用既有 `MatchingPackage` canonical payload；Matching domain／reader
     補上 schema 已有的 `candidate_pool_open` typed state，並只允許此狀態有空 package；
  3. Step 3／4 完整複用 fresh candidate／segment facts；Step 2 不假造 candidate／assignment；
  4. 同一 UoW 完成 prior-generation cancel、empty successor activation、aggregate CAS、
     replacement event／successor／receipt／outbox；失敗時由 outer owner rollback。
- `write_set`:
  - §7 已列三個 production paths 與 focused tests；
  - `domains/scheduling/matching_coordination.py`（只限已有 schema state 與 empty-open invariant）；
  - `infrastructure/mysql/matching_coordination_repository.py`（只限 canonical package parser 往返相容）。
- `excluded`: API／React／provider／1012 schema／public route／actual-service writer／新的
  Matching 業務分支。
- `safe_stop`: fresh source 無法提供完整 typed candidate／segment facts，或 prior generation
  current transition 無法對帳時，維持 package `in-progress`，不進 DB／API／Browser。
- `fail_before_fix`: invalid criteria digest、bundle snapshot bypass、source-event drift、existing reader
  decode failure、empty package state confusion、generation CAS rollback。
- `verification`: focused domain／adapter／repository → Matching/RPRE cross-regression → fresh Luna/high
  verifier → `lu_test_*` real-MySQL transaction/readback。

```yaml
package_status: PACKAGE_READY
blockers: []
```

## 6. Execution ledger（2026-08-28）

- `PKG-RPRE-OWNER-SUCCESSOR-domain`: `completed`。R-01／R-02／R-03／R-04／R-07 pure branch、
  exact root delta、authoritative service proof、candidate reuse、resume step、R-07 disposition與R-04
  matching-only zero-service representation已完成；generic Assignment Plan invariant未放寬。
- current evidence：主代理H/R cross-regression`81 passed`；fresh Luna/high R r3 `21 passed`＋
  adversarial probes，P0=0、P1=0。
- `PKG-RPRE-OWNER-SUCCESSOR-qpa`: `completed`。Query／zero-write Preview、fresh-lock Apply、outer
  UoW、idempotency、immutable receipt/outbox bundle與exact fresh owner readback application contract已完成。
- current subsystem evidence：主代理H/R cross-regression `105 passed`；fresh Luna/high R r5 focused
  `36 passed`、targeted `13 passed`＋adversarial probes，P0=0、P1=0。
- `PKG-RPRE-OWNER-SUCCESSOR-schema`: `completed`。additive part 1012、release manifest、owned-object
  descriptor、fresh assembly、cutover catalog與generated full release已完成；fresh Luna/high static
  review為P0=0／P1=0。
- `PKG-RPRE-OWNER-SUCCESSOR-concrete-source`: `completed`。concrete repository、same-UoW Matching
  successor、latest parent/source-event exact binding、canonical reader payload、generation transition與
  exact root／receipt／outbox readback已完成；主代理`93 passed`，第二位fresh Luna/high為P0=0／P1=0。
- `PKG-RPRE-OWNER-SUCCESSOR`: `completed`。指定`lu_test_*`已通過R-02 Apply／same-key replay、
  generation `8→9`、Matching numeric FK、canonical 5-root relation、receipt／outbox及fresh readback；
  immutable scenario採明確保留策略，fresh cleanup verifier P0=0／P1=0／P2=0。
- `PKG-RPRE-PROJECTION-pure`: `completed`。R-01～R-04／R-07 exact owner-root delta、
  actual-service substitution referral、Step 3／4 reuse、fresh readback digest／count／outbox與
  fail-closed semantics已完成；root與retained／superseded／created receipt identities均以
  canonical ordering計算fingerprint。主代理`68 passed`；fresh Luna/high P0/P1/P2=0，
  五個scenario各5000次隨機排列全部不變。
- `PKG-RPRE-API-contract`: `completed`。typed Query/Preview/Apply schema、strict success/error
  envelope、required idempotency key、proof/successor/root-delta cross-field fingerprint 與 closed
  §8.5 error vocabulary已完成；production loader未接時 TestClient誠實回
  `503 replacement_source_unavailable`。主代理`116 passed`；fresh Luna/high
  `133 passed, 1 skipped`，P0/P1/P2=0；skip為未設真MySQL env。
- `PKG-RPRE-PRODUCTION-LOADER-source`: `completed`（source／fresh E3）。request-aware
  composite loader、explicit R-01～R-04/R-07、BusinessClock started official moments、rebuild/RPRE
  predecessor、14 root sources、Matching 13-source/package-bound event、Contract signback 與
  schedule-recipient＋LINE binding 已接入 request-scoped connection/outer UoW；partial/missing/stale
  預期固定 typed `503 replacement_source_unavailable`。r1～r3 findings均已修正；final主代理
  focused `58 passed`、RPRE source suite `129 passed`。fresh Luna/high r4為P0/P1/P2=0、cross
  `221 passed`，並通過package-proposed exact binding、customer-decision 13-source parity、external
  signback source/receipt/session/result snapshot及rebuild predecessor五組adversarial probes。
  真MySQL integration因未提供env而`1 skipped`，不得外推為live runtime完成。
- `PKG-RPRE-PRODUCTION-LOADER-post-Apply`: `in-progress`。已修正有效successor generation沒有
  `scheduling_rebuild_events` row時仍被無條件判成malformed：存在latest RPRE event時改以其exact
  generation／aggregate／event binding作predecessor；首次換人無latest且無rebuild固定回
  `replacement_prior_event_unavailable`。主代理focused/broader `68 passed`，fresh Luna/high
  P0/P1=0、focused `133 passed`、broader `67 passed`。兩個retained R-02案件已跨過原
  `replacement_source_malformed`，下一個runtime結果為`replacement_matching_plan_unavailable`：
  Apply後successor已生效且不存在active accepted plan，UI post-Apply readback不可再把同一R-02當作
  未執行Query；durable receipt/successor readback入口仍待收斂，故runtime包不得標completed。
- `PKG-RPRE-PROJECTION-UI-RUNTIME`: `in-progress`；pure projector、production loader與React source已完成，
  `lu_test_*` no-auth API composition／fresh readback／真Browser仍未完成，不得外推為整包完成。
- `PKG-RPRE-REACT-source`: `completed`（source／fresh E3）。專屬 strict Q/P/A client、
  R-01／02／03／04／07 明確選擇、reason/evidence、Preview 確認、actual-service
  substitution referral、server-owned resume step 與 same-key outcome-unknown 對帳已完成；
  producer focused Vitest `4 passed`、oxlint/build/diff-check PASS。現有 anomaly drawer 尚無
  typed `case_no + RPRE scenario` binding，本 slice 不從 `sourceIdentity` 猜情境、不假掛載；
  fresh Luna/high r1 重驗 focused `4 passed`、build/oxlint PASS，但未放行：尚需補
  fingerprint/root-digest 重算、request/response case・scenario・idempotency binding、
  referral proof、Preview/Apply race/abort 及 callback failure handling；且正式入口未掛載。
  r2 已補nested/root digest、request binding、abort/race與入口掛載，主代理`9 passed`＋build PASS，
  fresh Luna/high合計`55 passed`＋build/oxlint PASS但仍未放行：完整preview與command fingerprint未重算、
  Apply後未fresh Query、入口仍預設猜R-01，且UI未完整顯示root/reuse/readback/proof lineage。
  r3 exact repair已完成full fingerprint、Apply後fresh Query、explicit scenario與完整root/proof/readback；
  主代理r4 `59 passed`＋build PASS；fresh Luna/high r4 focused`13 passed`、backend adjacent`109 passed`、
  Orders direct`46 passed`且build/oxlint PASS。r5已補完整numeric versions與projection_kind，主代理
  `13 passed`＋build/oxlint PASS；fresh Luna/high r5 `13 passed`、build/oxlint/diff-check PASS，P0/P1=0。
  依人工§8.8裁決，一般RPRE不具有anomaly occurrence；沒有explicit LINE request時UI不推定、不建立、
  不關閉active anomaly。Orders Browser可獨立驗收；3個既有Orders錯誤文字test為P2且不在RPRE路徑。
  post-Apply r6依Spec Pipeline校正：Apply response內`receipt + complete readback`為canonical post-commit
  observation；React不再用已套用的舊scenario重新Query，receipt-only／不完整readback仍進
  outcome-unknown並只以原payload/key對帳。主代理focused `13 passed`；fresh Luna/high PASS、
  P0/P1=0、build/lint/diff-check/UTF-8 PASS。兩個retained R-02 case的舊scenario Query仍因successor
  生效後active accepted plan合法不存在而不可作fresh pre-Apply Browser fixture；新的未套用scenario
  Browser Apply仍`NOT_RUN`，故`PKG-RPRE-PROJECTION-UI-RUNTIME`維持`in-progress`。
- persistence DB gates：Scope／Change inventory／Static release／Descriptor／read-only plan／Engine／本機
  Developer acceptance `PASS`；另一台實體電腦Developer acceptance `NOT_RUN`，總結仍為
  `DB_CHANGE_NOT_READY`。
- receipts：`03_追蹤清單與證據/evidence/2026-08-28_task96_hcat_rpre_domain_slice_receipt.md`、
  `03_追蹤清單與證據/evidence/2026-08-28_task96_hcat_rpre_subsystem_slice_receipt.md`、
  `03_追蹤清單與證據/evidence/2026-08-28_task96_rpre_concrete_persistence_source_receipt.md`、
  `03_追蹤清單與證據/evidence/2026-08-28_task96_rpre_mysql_persistence_receipt.md`、
  `03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_hproj_rpre_static_release_receipt.md`、
  `03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_1012_engine_qualification_receipt.md`、
  `03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_local_noauth_runtime_receipt.md`。

## 7. Concrete persistence task-pack correction（2026-08-28）

- `entry`: spec §10；只補齊 1012 adapter contract，不改 R-01～R-04／R-07 結果。
- `necessary_changes`:
  1. request context 將 scenario／reason／evidence 交給 repository fresh facts read，並以 owner roots
     驗證，不猜 scenario；
  2. 新增 type-safe Matching successor persistence port，在同一 outer UoW 建立新 package
     lineage／`package_proposed` event 並回傳 numeric FK；
  3. 以 spec §10.3 descriptor 及 `sha256_newline_v1` 寫入 root relations，再從 rows 重算
     digest／count／ordinal 與 fresh readback；
  4. replay 必須 exact 核對 event／successor／descriptor／root sets／versions／outbox。
- `write_set`:
  - `subsystems/scheduling/service_before_replacement_workflow.py`（只限 type-safe request／bundle／readback 邊界）；
  - `infrastructure/mysql/service_before_replacement_repository.py`；
  - `infrastructure/mysql/matching_successor_persistence_adapter.py`；
  - 對應 focused tests。
- `excluded`: 1012 schema/release、Matching public API、actual service writer、Orders／Finance／Payroll／
  provider／React／production。
- `fail_before_fix`: adapter import、ambiguous roots、actual-service zero-write、missing Matching source、
  partial write rollback、empty/nonempty digest、ordinal／replay drift／post-commit unknown。
- `verification`: repository contract → R domain/workflow cross-regression → `lu_test_*` MySQL
  persistence/readback → fresh Luna/high verifier。

```yaml
package_status: PACKAGE_READY
blockers: []
```
