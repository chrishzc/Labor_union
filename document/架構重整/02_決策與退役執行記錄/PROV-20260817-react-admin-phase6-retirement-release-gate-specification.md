---
doc_type: implementation-specification
declared_status: proposed
identity: PROV-20260817-react-admin-phase6-retirement-release-gate
date: 2026-08-17
owner: Global Deployment / Entry Point Governance
authority: awaiting-exact-human-approval; validator installation may precede Phase5 completion
approval_required: 核准此 exact Phase 6A Work Package
absorbs: PROV-20260817-react-admin-phase6a-validator-installation-gate-amendment
prerequisites: none for validator installation; release readiness still requires all readiness_prerequisites
readiness_prerequisites: PROV-20260817-react-admin-phase5a-entry-governance-rollback PASS; PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation PASS; PROV-20260817-react-admin-phase6b-production-hosting release-approved; PROV-20260817-react-admin-phase6b-runtime-integration release-approved; per-entry production switch and closed observation receipts
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Phase 6A：Streamlit retirement release gate 規格

## 0. Minimal validator installation（最新優先裁決）

本節取代本文任何把「validator安裝」與「Phase6 release ready」綁成同一前置的舊讀法；既有final三態機、
navigation switch、observation與retention gate仍完整保留。

Phase6A分為兩個互不替代的mode：

1. **Installation mode**可在Phase5A/5B、production switch、hosting、observation與retention尚未完成時執行。
   它只讀checked-in requirements／entry registry／receipt schemas與negative fixtures；不得產生、補寫、重排或修復
   registry、queue、requirements、receipts或source inventory。成功輸出固定同時包含
   `validator_installation_status=VALIDATOR_INSTALLED_NOT_READY`與`overall_status=PHASE6_NOT_READY`。
2. **Release-readiness mode**才執行本文G0→G7並可能輸出既有三態。Installation PASS不得預先PASS任何G0→G7，
   不得使Phase6A completed，也不得授權source retirement或dependency cleanup。

Installation gates固定`I0→I1→I2→I3→I4`：

| Gate | PASS condition |
|---|---|
| I0 | exact Phase6A approval；write set只有validator/schema/tests/installation receipt |
| I1 | strict requirements／registry／receipt schema與missing-input failure |
| I2 | missing／extra／duplicate／stale／unknown／producer mismatch回stable machine code |
| I3 | 0 DB engine、0 browser、0 services、0 inventory generator、0 source/queue/registry write |
| I4 | 同時輸出`VALIDATOR_INSTALLED_NOT_READY`＋`PHASE6_NOT_READY`，installation receipt與release receipt分離 |

`--installation-check`可在I0～I4 PASS時exit 0；default release-readiness在Phase5缺件時仍須非零並輸出
`PHASE6_NOT_READY`及完整codes。任何mode都禁止刪除／搬移／retire／修改source bytes、navigation target、retention state或dependency。

React page-slice的query完成只依該頁typed GET／browser／安全證據，不要求Phase6 validator或global DB engine；
bounded mutation只遵守自己的Work Package DB gate。只有Phase5 entry switch與Phase6 retirement使用final mode。

## Responsibility

建立一個唯讀、fail-closed、可重跑的retirement readiness validator及release inventory。它只能證明
Phase6是否可開始，不能自行刪除source、修改queue disposition、停止服務或部署artifact。

## Required inputs

- 10個Streamlit legacy entries，加上Phase5A baseline 11個React entries與其後每一個已核准identity amendment
  所形成的latest canonical registry revision及逐entry dispositions。
- 每個entry的browser、rollback、forward-written-data與focused regression receipt。
- 每個legacy entry及完整one-to-many replacement group的Phase5 runtime switch production receipt：signed
  manifest revision、`previous_target=streamlit`、`current_target=react`、one-entry CAS/audit、成功switch-back
  rehearsal及已完成的post-switch observation window。Candidate/readiness receipt不得代替。
- React production artifact version/digest/health/CSP/API compatibility/rollback identity。
- launcher、monitor、rehearsal、dependency與current-doc successor inventory。
- exact source retirement manifest；每個path具caller／replacement／test disposition。

`react_admin_retirement_requirements.json`是由Contract Scout／Integration Owner維護並人工review的
checked-in canonical input；validator與entry queue generator都不得建立、回寫、補全或重排它。
`retirement-source-inventory.json`則由另一個inventory owner依latest worktree產生candidate evidence。
前者必填`requirements_producer`，後者必填`inventory_producer`，兩者必須是不同owner且共用同一
`registry_revision`。producer相同、revision不一致、欄位缺失，或同一工作執行同時生成expected/candidate時固定
`INDEPENDENT_MANIFEST_MISMATCH`，不得自動選一側或改expected。

## Independent registry boundaries

Validator必須同時驗證兩個互不替代的集合：

1. `ui_cutover_registry`：exact 10個Streamlit legacy identities＋latest approved React identity set；
   Phase5A的11個React只是minimum baseline，不是Phase6永久總數。manifest必須含`registry_revision`、
   每個後續identity amendment與source receipt。
2. `full_entrypoint_registry`：current API／CLI／UI discovery必須與entry queue完全一致。

目前queue 526而generator discovery 530，已知漏4個API；另有1個Streamlit與11個React未被current
generator發現。Validator不得把21當永久總數、不得用受測generator產生expected，也不得忽略
missing／extra／duplicate／stale／unknown identity。Phase5A未完成前此gate固定fail。

例如System Status successor若依獨立exact WP新增`ui-react:#system-status`，requirements必須由該核准
identity amendment更新為新的exact set；若Form Management另有dedicated identity亦同。Validator不得自行
推測或吸收新route，也不得因舊requirements仍寫21而忽略已核准source registry。

Expected sources必須逐一保存source locator與extraction method，至少包含：

- Streamlit：`ui/app.py::PAGE_REGISTRY`（不是page-local `title` heuristic）。
- React：`MasterLayout.tsx` route registry、`App.tsx::PAGE_SECTION_MAP`／render wiring及`PageType`。
- API：`api/main.py`、`api/routes/**/*.py`及`line/line_bot.py`的mounted public entries。
- CLI/runtime：`scripts/**/*.py` operator entries、`scripts/launchers/**`、monitor、smoke及migration rehearsal callers。

不得只以`rg "streamlit"`、單一AST heuristic或目前queue generator冒充完整registry。

## Receipt provenance contract

每個entry receipt至少含：`entry_id`、source path、replacement identity、base ref、candidate changed-path
inventory、source/artifact digest（僅作內容完整性與freshness，不作task identity或衝突裁決）、執行時間、
observation window、operator／approver、exact command、HTTP status／response contract、browser URL／DOM
identity／Network evidence、真帳密→TOTP auth mode、failure／timeout／outcome-unknown結果、focused tests及
linked rollback／forward-data receipts。任一source、artifact或base drift使receipt失效並fail closed。

另須獨立保存`phase5_navigation_switch_production_receipt`與`phase5_observation_receipt`。前者必須證明
canonical admin entry map在核准manifest revision把該entry解析到React，且只改一個entry；後者必須證明
切換後觀測期已完整結束。只有docs-only navigation decision或candidate測試一律視為缺件。

Observation/retention欄位為closed contract：`observation_started_at`、`observation_ended_at`、closed outcome、
`retention_end`、`retention_state`與release-owner deletion approval。`retention_state`只允許
`pending | active | completed_not_expired | expired_approved`；只有`expired_approved`可授權刪除source bytes。
只有start receipt、單張截圖或尚未到期的觀測不得被validator視為完成。

`observation_outcome`只允許`closed_success | closed_failure | outcome_unknown`；缺失、未知或矛盾值固定
fail closed，且只有`closed_success`可進入`completed_not_expired`或`expired_approved`。Retention合法轉移固定為
`pending → active → completed_not_expired → expired_approved`，不得跳態、倒退或由source數量推導。
`expired_approved`必須同時滿足：observation已`closed_success`、`retention_end <= BusinessClock`、
release-owner approval已綁定entry／source digest／manifest revision，且目前沒有active rollback trigger。

Phase6A gate順序固定`G0 → G1 → G2 → G3 → G4 → G5 → G6 → G7`，不得平行或倒置。G6先驗證完整
observation close與retention state；只有G6 closed且retention到期後，G7才能以fresh BusinessClock與source
inventory重新評估deletion readiness。

Receipt expected schema必須來自checked-in independent requirement manifest；validator不得產生自己的
expected再驗證自己。只存在Markdown、截圖、unit test、`npm run build`或人工文字「PASS」均不足以通關。

Validator installation使用獨立狀態`VALIDATOR_INSTALLED_NOT_READY`，只證明schema、negative vectors及
machine-readable拒絕行為已安裝；不得映射成下述任何`PHASE6_READY_*`狀態，也不得把Phase6A release gate標completed。

## Bidirectional rollback／forward-data proof

每個mutation entry必須使用disposable/test fixture完成：React Apply→canonical re-query／receipt／outbox→
entry-specific Streamlit rollback URL re-query／正式能力的repair或replay→切回React再觀察。同一root fact、
version、receipt、outbox、anomaly與audit projection必須語意一致。mismatch、stale、timeout或outcome unknown
固定fail closed；不得操作既有`union_db`或回滾Domain data來製造相容。

## Production hosting prerequisite

G4只接受已人工核准且完成的Phase6B production hosting successor：唯一topology、same-origin `/admin/`
hash-route static serving與reload（禁止root wildcard，且不得攔截`/api`、`/health`或LINE routes）、artifact
version/digest、health、CSP、cache、API compatibility、真challenge→TOTP→API browser、
immutable previous artifact、rollback selector、maintenance window、owner／trigger與observation receipt。
Vite 5173、`npm run build`或自造artifact receipt不得取代。未完成固定
`BLOCKED_REACT_PRODUCTION_HOSTING_CONTRACT`。

HOST與RUN各自必須提供machine-readable `release_approval_receipt`，不能只寫文字`release-approved`。
HOST receipt至少包含package/base/artifact/manifest/API compatibility/current+previous bindings與retention、
approver/time、browser及rollback rehearsal、closed outcome；RUN receipt至少引用HOST、Phase5A/5B receipts，
並包含pre-child local attestation、post-API private active-mounted attestation、caller inventory、queue integrity、
approver/time與closed outcome。任一receipt stale、過期、identity mismatch或只有implementation tests即fail closed。

## Retirement source manifest contract

每個候選path必須記錄tracked／modified／untracked狀態、dynamic callers、launcher／monitor／rehearsal
callers、dependency owner、test disposition、current SSOT inbound references、content digest（完整性用途）、
`retain | migrate_then_remove | remove`分類、release identity與deletion authorization。禁止整目錄刪除、
依`rg "streamlit"`批次刪除、只刪dependency、只改launcher、刪／skip tests或把failure改warning。
ignored path也必須列入`git_state`盤點；無法判定tracked／modified／untracked／ignored／deleted時固定
`SOURCE_RETIREMENT_MANIFEST_INCOMPLETE`。候選數量必須附可重跑command、scope、exclude rules、base ref、
generated time及`files | matches`計數種類；沒有這些metadata的舊摘要不得成為release input。
current／previous React artifacts也必須各自列release identity、manifest digest、retention identity/state/end、
restore trigger與release-owner approval；previous仍被任一entry rollback/observation依賴時不得清除或覆蓋。

## Fail-closed codes

- `ENTRY_NOT_READY`
- `ROLLBACK_RECEIPT_MISSING`
- `FORWARD_DATA_COMPATIBILITY_MISSING`
- `REACT_ARTIFACT_CONTRACT_MISSING`
- `RUNTIME_SUCCESSOR_MISSING`
- `SOURCE_RETIREMENT_MANIFEST_INCOMPLETE`
- `HUMAN_RELEASE_APPROVAL_MISSING`
- `FULL_ENTRY_REGISTRY_DRIFT`
- `RECEIPT_PROVENANCE_INVALID`
- `BIDIRECTIONAL_ROLLBACK_NOT_PROVEN`
- `CURRENT_SSOT_SUCCESSOR_MISSING`
- `ARCHIVE_GATE_INCOMPLETE`
- `INDEPENDENT_MANIFEST_MISMATCH`
- `DEPLOYMENT_SSOT_CONFLICT`
- `PHASE5_ENTRY_SWITCH_MISSING`
- `PHASE5_ENTRY_SWITCH_OBSERVATION_INCOMPLETE`
- `PHASE5_ENTRY_TARGET_NOT_REACT`
- `ROLLBACK_RETENTION_ACTIVE`

任一錯誤存在時結果固定`PHASE6_NOT_READY`。

## Machine status

`overall_status`是closed三態，未知值固定fail closed：

1. `PHASE6_NOT_READY`：任一required gate、receipt、registry、runtime、rollback、observation或人工批准缺失。
2. `PHASE6_READY_FOR_ENTRY_RETIREMENT`：Phase5每一legacy entry均有fresh production switch／observation
   receipt且current target為React，HOST、RUN及本validator gate均PASS，但仍至少有一個
   Streamlit legacy entry未完成獨立retirement；只允許依6C template一次處理一個entry。
3. `PHASE6_READY_FOR_FINAL_DEPENDENCY_CLEANUP`：第二態全部條件持續PASS，且另有exact 10個per-entry removal
   receipts、每筆rollback retention已到期並有release owner批准、fresh caller inventory為0 remaining Streamlit
   runtime owner、所有歷史evidence與restore provenance仍保留。缺一即不得進入此態。

後兩態互斥；validator不得因source數量為0自行推進，必須同時驗證receipt identity、retention與owner批准。
