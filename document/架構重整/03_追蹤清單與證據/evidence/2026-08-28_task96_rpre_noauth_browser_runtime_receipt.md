# Task 96 RPRE no-auth Browser runtime receipt

- `package_id`: `PKG-RPRE-PROJECTION-UI-RUNTIME`
- `scenario_slice`: `R-01 candidate unavailable`／`R-02 accepted matching package`／
  `R-03 waiting lock + commitment + signback`／
  `R-04 assigned before service`／`R-07 confirmed zero-candidate successor`／
  `actual-service referral`
- `status`: `passed`
- `target`: `APP_ENV=development`／`lu_test_task96_rpre_browser_r3_20260828`
- `auth_profile`: `local_bypass`；server actor `system:local_bypass`
- `scope_limit`: 本 receipt 已完成 R-01、R-02、R-03、R-04、R-07及actual-service referral。
  R-07 Matching owner entry與RPRE均由正式Q/P/A建立；未以SQL fixture假造owner lineage。

## Final behavior evidence

- Query回讀zero actual-service proof、4筆current Matching roots與fresh accepted-candidate reuse proof。
- Preview為zero-write，建立新`successor-round:115960402:3`候選；公開response可由React完整重算
  actual-service、reuse、root delta與preview fingerprints。
- Apply使用Browser產生的單一Idempotency-Key；先前fail-closed嘗試均未commit，修正版最終提交一次。
- final owner readback：generation／event／aggregate `2→3`、retained `0`、superseded `4`、created `1`、
  Matching package lineage／event `4／5`、`complete=true`。
- immutable identities：receipt `replacement-receipt:115960402:3`、outbox
  `replacement-outbox:115960402:3`、generation `replacement-generation:115960402:3`、event
  `replacement-event:115960402:3`。
- UI成功後直接使用Apply response內的complete readback；未重新Query已消耗的舊R-02 scenario，也未推定或
  自動關閉不存在的anomaly occurrence。

## Corrections proven by the runtime

- Domain將受影響roots依identity canonical排序，API序列化後仍可重算preview fingerprint。
- React Apply request改為單一strict object schema，避免兩個strict schema intersection互相拒絕欄位。
- no-auth actor與server固定同為`system:local_bypass`。
- Matching criteria snapshot digest與其歷史source tuple成對傳遞；current package source tuple維持自身owner
  lineage，不與criteria snapshot tuple混為同一契約。
- frozen Domain criteria中的mapping／tuple與MySQL JSON object／array以canonical fingerprint比較；內容漂移
  仍由digest、source tuple與stored binding fail closed。
- reuse source proof先fresh驗證，再產生綁新successor round的typed proof；coverage／availability／
  willingness與expected generation/event版本保留，DB same-round constraint未放寬。
- R-07 Query對既有zero-candidate successor直接投影`zero_candidate_successor_disposition`與Step 2；
  post-Apply Query不再把同一successor同時列為impacted與retained。

## R-07 confirmed zero-candidate successor evidence

- `target`: `lu_test_task96_rpre_browser_r3_20260828`；case `115960417`；future service dates
  `2027-01-11`～`2027-01-15`；no-auth runtime為5183 UI→8016 API。
- Matching先以正式zero-candidate Preview／Apply建立current `no_candidate` package、
  `package_proposed` event、receipt與`rematch_requested → assignment_workflow` intent；RPRE Query再讀取
  該owner proof，沒有SQL注入owner lineage。
- RPRE Preview：Step 2、actual service 0、superseded 0、created successor 1、versions `1→2`；
  Browser核對reason／evidence後Apply，complete owner readback為generation／event／aggregate `2／2／2`。
- before／after Matching counts完全不變：package `2→2`、event `3→3`、receipt `3→3`、outbox `1→1`；
  RPRE event／successor／receipt／outbox各由`0→1`。1012綁既有Matching numeric identities `6／8`與
  string identities `matching:115960417:no-candidate:9ec773ef965f4e58b567f897`／
  `task96:rpre:115960417:r07-confirm:zero-candidate-confirmed`。
- final fresh case `115960427`由Apply response內canonical owner readback直接顯示Step 2、candidate count 0、
  `blocked_no_candidate`、versions `2／2／2`及`complete=true`；UI明示只完成lineage、不代表異常已解除，
  也不會復活舊月嫂。沒有以已消耗scenario重新Query作為成功證據。
- DB final readback：successor為`R-07／step_2／0／blocked_no_candidate`，expected generation/event皆1；
  event／successor／receipt／outbox各exactly one。
- 無LINE request：case-scoped `anomaly_current_alerts=0`、`anomaly_workflow_events=0`；未建立或關閉
  anomaly occurrence，亦未復活舊staff。

## R-04 assigned-before-service evidence

- `target`: `lu_test_task96_rpre_r04_20260828`；case `115960404`；future official dates
  `2026-09-21`～`2026-09-25`，authoritative actual-service count為0。
- Query：scenario `R-04`、fresh accepted-candidate reuse、Step 4、exact impacted roots為
  `assignment`／`effective_generation`／`official_schedule`共3筆。
- Preview：`projection_kind=matching_only_zero_service`、root delta `0／3／1`、versions `2→3`、新
  successor round `successor-round:115960404:3`，zero-write。
- true Browser Apply：receipt `replacement-receipt:115960404:3`、outbox
  `replacement-outbox:115960404:3`、Matching lineage/event `2／3`、`complete=true`。
- DB readback：generation 1與2皆`cancelled`，generation 3為唯一`effective`；assignment 1筆及schedule
  5筆只保留在generation 2，新generation沒有假assignment／schedule；該case anomaly rows為0。

## R-03 waiting-lock／commitment／signback evidence

- `target`: canonical bootstrap release `labor-union-validation-schema-2026-08-28-v16` 建立的
  `lu_test_task96_rpre_r03c_20260828`；case `115960407`；future service dates `2026-10-19`～`2026-10-23`。
- fixture只走正式API：客戶LINE直接綁定；月嫂LINE進入pending review後，以管理端Review Preview／Apply正式
  核准；waiting lock、commitment、雙方簽回與Matching lineage均由owner API／production repository建立。
- Query：scenario `R-03`、actual-service 0、Step 4；exact roots為`waiting_lock`／`commitment`／`signback`／
  `recipient_binding`共4筆。legacy signback loader的`document_segment_id`欄位別名漂移已修正並有回歸測試。
- Preview：root delta `0／4／1`、versions `1→2`、successor `successor-round:115960407:2`、zero-write。
- true Browser Apply：receipt `replacement-receipt:115960407:2`、outbox
  `replacement-outbox:115960407:2`、Matching lineage/event `2／3`、`complete=true`。
- DB owner readback：generation 1為`cancelled`、generation 2為唯一`effective`；waiting-lock header為
  `cancelled`／inactive，5筆lock days全部inactive且由`system:local_bypass`釋放；immutable history為原
  `lock_acquired`加唯一`lock_cancelled`。commitment 1筆、commitment days 5筆、staff signback 1筆保留，
  case anomaly projection為0。
- Apply於同一outer UoW先鎖case aggregate，再以sorted staff IDs取得occupancy mutex，再重讀fresh owner roots；
  complete readback反向驗證lock header、全部days、deterministic event key/payload及superseded waiting-root identity。

## R-01 candidate-unavailable evidence

- `target`: canonical bootstrap release `labor-union-validation-schema-2026-08-28-v16` 建立的
  `lu_test_task96_rpre_r01_20260828`；case `115960408`；future service dates `2026-10-26`～`2026-10-30`。
- fixture以正式candidate-pool API建立唯一candidate並記錄`unwilling/service_date_conflict`；未建立matching plan、
  commitment、assignment或schedule。M3暫無package Apply public entry，因此沿用既有validation-only typed
  application/repository/UoW injection保存`candidate_pool_open` parent與rejected customer-decision lineage；未直接寫SQL。
- Query：scenario `R-01`、actual-service 0、Step 2、reuse proof無；exact roots為`candidate_binding`／
  `willingness`共2筆。
- Preview：root delta `0／2／1`、versions `1→2`、successor `successor-round:115960408:2`、zero-write。
- true Browser Apply：receipt `replacement-receipt:115960408:2`、outbox
  `replacement-outbox:115960408:2`、Matching lineage/event `2／3`、`complete=true`、successor candidate count 0。
- DB before/after：candidate pool／entry／events各自count `1／1／2`且SHA-256完全相同；matching plan、commitment、
  assignment、schedule全部維持0；generation 1 cancelled、generation 2唯一effective；case anomaly projection 0→0。

## Actual-service referral evidence

- `target`: `lu_test_task96_rpre_referral_20260828`；case `115960403`；official actual-service proof含5日。
- Query與Preview均為`substitution_referral`，replacement identities、roots、reuse與successor全部為空。
- forced Apply正確回409 `replacement_actual_service_exists`；1012 events／roots／successors／receipts／
  outbox五表的case rows前後均為0。
- true Browser顯示「已有實際服務，必須改走請假代班」，replacement Preview／Apply控制數為0；「前往請假
  代班」導向`#scheduling?tab=leave_sub&case_no=115960403`，並正確帶入案件編號。

## Verification

| Check | Status | Evidence |
|---|---|---|
| Python RPRE focused | `passed` | final R-01 broad affected suite `142 passed`；stage-label exact patch `96 passed`；R-03 final focused `80 passed` |
| React focused | `passed` | final service-before-replacement `16 passed`；R-07 canonical Apply readback具專屬UI regression |
| React production build | `passed` | TypeScript＋Vite build PASS；只有既有chunk-size warning |
| Persistence rehearsal | `passed` | production repository完整寫入至receipt/outbox後明確rollback，`PERSIST_PASS 3 4` |
| True Browser | `passed` | 5183 UI→8016 API；Query／Preview／Apply／complete readback |
| DB fresh readback | `passed` | versions 3／3／3、lineage/event 4／5、root counts 0／4／1 |
| R-04 true Browser＋DB | `passed` | Query／Preview／Apply；0／3／1；new generation empty/effective；anomaly 0 |
| R-03 true Browser＋DB | `passed` | Query／Preview／Apply；0／4／1；lock cancelled＋5 days inactive＋single cancellation event；owner history retained；anomaly 0 |
| R-01 true Browser＋DB | `passed` | Query／Preview／Apply；0／2／1；Step 2；candidate history fingerprints unchanged；plan/commitment/assignment/schedule 0；anomaly 0 |
| R-07 true Browser＋DB | `passed` | final case `115960427`：Matching owner Q/P/A；RPRE Query／Preview／Apply；Apply response顯示Step 2／0／`blocked_no_candidate`／complete；1012 event/successor/receipt/outbox各1 |
| Python R-07 readback focused | `passed` | `146 passed` |
| Actual-service referral | `passed` | Query／Preview referral；forced Apply 409；五表0→0；Browser只顯示代班轉介 |
| `git diff --check` | `passed` | 無whitespace error |
| Fresh Luna/high E3 | `passed` | final R-03候選P0/P1/P2均0；Python focused `188 passed`、React `25 passed`、build／py_compile／diff-check／strict UTF-8／secret scan PASS；鎖序、exact cancel、history retention與complete readback均獨立確認；`changed_files=[]`。 |
| Fresh Luna/high E3 — R-01 | `passed` | 初查P0/P1為0，唯一P2為fixture stage誤標；exact patch後複核P0/P1/P2均0，R-01／R-03／R-02+R-04 stage標籤正確；Python `80 passed`、React `25 passed`、py_compile／static assertion／diff-check PASS；`changed_files=[]`。 |

## Side effects and retention

- final R-02 event／successor／receipt／outbox是本次受控`lu_test_*`驗收資料，依immutable lineage保留。
- final R-03 event／successor／receipt／outbox與`lock_cancelled`是本次受控`lu_test_*`驗收資料，依immutable
  lineage保留；commitment／signback owner history未刪除或覆寫。
- final R-07 Matching package／event／receipt／intent與RPRE event／successor／receipt／outbox是本次受控
  `lu_test_*`驗收資料，依immutable lineage保留；Matching owner counts在RPRE Apply前後不變。
- 診斷使用的未commit transaction已rollback；未修改`union_db`、production DB、provider或LINE。
- 未執行schema／migration／seed／backfill／reset／`--switch`，未清理任何既有dirty changes。
