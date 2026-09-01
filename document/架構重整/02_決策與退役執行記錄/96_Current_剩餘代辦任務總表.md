---
doc_type: gap-register
declared_status: in-progress
date: 2026-09-01
owner: architecture-governance / product-and-domain-owners
priority_authority_date: 2026-08-31
---

# Task 96 剩餘代辦總表：current in-progress / bounded partial

> Task 96 仍是 active current register。本文件記錄截至目前的 source、runtime 與 terminal evidence，並把
> 尚未完成的 lane 保持為 `in-progress`、`partial` 或 `deferred/not_run`。`completed` 只表示明確 bounded
> slice，不表示 preserve-data upgrade、完整產品功能、真實 provider、Browser、production、deployment 或
> schema boundary 已完成。正式語意仍以 `01_規格基線` 與最新人工裁決為準，本文件不修改正式規格。

## 1. Current status and stopping language

- **Declared status：** `TASK96_REPOSITORY_LOCAL_IN_PROGRESS_WITH_PARTIAL_RUNTIME_EVIDENCE`。
- **Active／residual Task 96 IDs：** 仍有 `in-progress`、`partial`、`current CI passed` 與 `deferred/not_run` lanes；不得以文件狀態把未完成工作移出 current register。
- **Current CI status：** commit `859a77e718e1cc6af38318e7017d347239a4ce2f` 已在 `origin/main`；GitHub Actions run
  [`33463723309`](https://github.com/chrishzc/Labor_union/actions/runs/33463723309) 為 `completed / success` 且所有 jobs 綠燈。此結果只關閉 current CI gate，
  不外推 Task 96 整體、真 MySQL Staff 之外的 runtime、Browser、provider、NAS 或其他 deferred boundary。
- **DB upgrade boundary：** 使用者已明確要求停止修正 1019 preserve-upgrade script。下列 reset path 是
  development `lu_test_*` 的 disposable reset／current-schema bootstrap 與啟動證據，不是 1003→current
  preserve-data upgrade，也不宣稱 1019、1020 或 1021 qualification 通過。
- **Effect ceiling：** 本輪未操作 production、`union_db`、provider send／publication、NAS、deployment、entry switch、
  performance benchmark、destructive cutover 或 preserve-data upgrade；各 `lu_test_*` evidence 仍須依其明確 scope 解讀。

## 2. Current bounded evidence (not terminal product acceptance)

下列結果已由 current task evidence 支持，且只在所列 scope 內成立：

| Scope | Result | Boundary |
|---|---|---|
| Development reset／bootstrap | `completed` | `scratch/task96/lu_test_1-bootstrap.json` 記錄 `lu_test_1` reset/rebuild receipt 為 `committed`，再讀回 current canonical schema；這是 disposable reset，沒有 preserve-data upgrade claim。 |
| Current-schema guard | `completed` | updater 的 `--require-current` 對已建立的 `lu_test_1` readback 通過；此 readback 不證明 1019 preserve-upgrade。 |
| No-auth local startup | `partial` | source：no-auth launcher local wrapper 會自行產生 ephemeral cursor key；runtime：local API verified，`GET /health` 回 200、`GET /api/v1/anomalies` 回 200 空清單；terminal：full Docker canonical launcher 不可用，修復後 Browser UI 因 Browser tool unavailable 為 `not_run`，不外推完整 startup acceptance。 |
| Current CI | `passed` | source：commit `859a77e718e1cc6af38318e7017d347239a4ce2f` on `origin/main`；runtime：Actions run [`33463723309`](https://github.com/chrishzc/Labor_union/actions/runs/33463723309) `completed / success`，完整 React tests＋build、Clients canonical matrix、canonical owners、historical cancellation MySQL、historical order workbook、cross-domain、lint/governance jobs 全部成功；terminal：current CI gate `passed`，不外推其他 runtime／外部 boundary。 |
| LINE provider worker | `deferred/not_run` | source：provider worker 存在；runtime：本輪刻意跳過；terminal：無 provider／recipient／quota／external delivery receipt。 |
| LINE repository-local integration | `partial` | source：`03_追蹤清單與證據/evidence/PROV-20260830-line-anomalies-slimming-integration-receipt.md` 與 local focused contracts；runtime：repository-local M1～M4／typed boundary evidence；terminal：browser sandbox、provider、DB engine、production boundary 未驗收。 |
| Anomalies repository-local integration | `partial` | source：current-state registry／typed current-only mapping／退役碼 routing；runtime：repository-local integration evidence；terminal：canonical product 仍為 partial，LINE-006 完整人工 remediation 與其他 owner contracts 未形成 terminal acceptance。 |
| Historical Staff Payables settlement | `partial` | source：`tests/domains/staff-payables/subsystems/staff-payables/modules/historical-payment-settlement/integration/test_task96_historical_staff_payout_mysql_acceptance.py`；runtime：root rerun 1 passed on隔離 real MySQL `lu_test_task96_historical_staff_r2`、canonical release v23 bootstrap、Query→Preview→Apply→exact replay→readback，version 0→1／event／link／projection／receipt／outbox passed；terminal：Browser mutation `not_run`，Client owner MySQL仍未驗，不能外推完整 historical settlement。 |

## 3. All former Task 96 lanes

| ID | Status | Current source / runtime / terminal evidence and next gate |
|---|---|---|
| `CUR-LOCAL-DB-1003-CURRENT-01` | `superseded` | source：原 1003→current ordered preserve／resume／normal-startup chain；runtime：依使用者指示停止 1019 preserve-upgrade 修正；terminal：preserve-data qualification `not_run`，不得保留舊 PASS，未來須有明確 DB Authority、合法 `lu_test_*` target 與新 receipt。 |
| `CUR-LOCAL-DB-PORTABILITY` | `superseded` | source：舊 portability／preserve-upgrade lane；runtime：停止，不由 `lu_test_1` reset／current readback／no-auth startup 代替；terminal：portability／preserve acceptance `not_run`，不得升格為 production evidence。 |
| `CUR-CI-CODE-BASELINE-ACTIONS-01` | `passed` | source：commit `859a77e718e1cc6af38318e7017d347239a4ce2f` on `origin/main`；runtime：Actions run [`33463723309`](https://github.com/chrishzc/Labor_union/actions/runs/33463723309) `completed / success` 且所有 jobs 綠燈；terminal：current CI gate `passed`，不代表 current Task 96 全部 lanes 或外部 acceptance。 |
| `CUR-LINE-MODULES-1-4-CLOSURE-01` | `partial` | source：M1～M4 repository-local contracts／focused regression／typed owner boundary；runtime：local integration evidence；terminal：verified-token LIFF、provider、deployment、production DB、未核准 schema 與 external side effect 未驗收。 |
| `CUR-ANOMALY-OWNER-BACKEND-PREREQUISITES-01` | `superseded` | source：原 13-code anomaly owner prerequisite artifact；runtime：`GOVSUB-007` anomaly producer/public mapping retired，但 Government Subsidy 正常 owner operation 保留；terminal：不建立 Anomalies 第二套 manual-recovery framework，owner operation 依自身 acceptance。 |
| `CUR-P0-ANOMALY-RECOVERY-01` | `partial` | source：唯一 `LINE-006` registry／typed mapping、`BECLASS-001` owner follow-up、退役碼 routing；runtime：repository-local current-state integration；terminal：canonical Anomalies status partial，LINE-006 manual remediation／owner predicates 未全證。 |
| `CUR-P0-HISTORICAL-PAYMENT-SETTLEMENT-01` | `partial` | source：Staff Payables integration test與既有 owner package；runtime：root rerun 1 passed，`lu_test_task96_historical_staff_r2` real-MySQL lifecycle passed；terminal：Browser mutation `not_run`，Client owner MySQL仍未驗，current CI gate `passed`但不解除本 lane residual acceptance。 |
| `CUR-CONTRACT-01` | `in-progress` | source：Contract Signing owner contract／PDF-NAS adapter requirements；runtime：enabled persisted-human Chrome chain尚未完成；terminal：final PDF／metadata／storage readback與external signing evidence `not_run`。 |
| `CUR-FILE-NAS-01` | `in-progress` | source：controlled storage typed contract；runtime：local composition可讀但真 NAS未掛載；terminal：NAS list／download／readback `not_run`，需受控 target與credential。 |
| `CUR-LIFF-PROFILE-01` | `in-progress` | source：20 §6.1／23 contract與Client successor存在；runtime：repository-local candidate evidence，verified-token DB path尚未terminal；terminal：LIFF E2E與owner DB readback `not_run`，不得以 no-auth startup代替。 |
| `CUR-LINE-RICHMENU-01` | `in-progress` | source：Rich Menu configuration/publication contract；runtime：local preview／typed boundary可留；terminal：provider qualification、publication lineage與sandbox receipt `not_run`。 |
| `CUR-CONTRACT-FULL-PREVIEW-01` | `in-progress` | source：21 latest owner projections、requiredness與exact-target public entry已 settled；runtime：remaining source cells／implementation尚未完成；terminal：full Preview／PDF result／download acceptance `not_run`，不再聲稱 contract Authority缺失。 |
| `CUR-LINE-RICHMENU-AUTH-01` | `in-progress` | source：authenticated queue→worker→provider contract；runtime：repository-local source tests；terminal：enabled-session provider receipt／readback `not_run`。 |
| `CUR-UX-01` | `in-progress` | source：12 Global UX／accessibility requirements；runtime：局部 presentation evidence；terminal：fresh responsive／keyboard／WCAG Chrome acceptance `not_run`。 |
| `CUR-UI-01` | `in-progress` | source：12 UI contract與既有 surface owner；runtime：逐頁 comparison未完成；terminal：visual／responsive／WCAG acceptance `not_run`。 |
| `CUR-PERF-01` | `in-progress` | source：12 record-only performance contract；runtime：無可重跑同環境 baseline evidence；terminal：API／React／DB benchmark `not_run`，且不構成 release blocker。 |
| `CUR-INTERNAL-UI-UNMASKED-01` | `in-progress` | source：既有 `PROV-20260827-internal-admin-ui-unmasked-display-spec-gap.md` package與12/15 contract；runtime：分批 surface盤點未完成；terminal：完整值／permission／negative acceptance `not_run`。 |
| `CUR-UI-STITCH-UNIFICATION-01` | `deferred/not_run` | source：26 deferred-after-96／UI design adoption gap；runtime：fresh surface inventory尚未建立；terminal：design adoption acceptance `not_run`，不作 current Task 96 terminal gate。 |
| `CUR-LIFF-E2E` | `deferred/not_run` | source：17／20 verified-token contract；runtime：exact sandbox/token未就緒；terminal：verified-token LIFF E2E `not_run`。 |
| `CUR-LINE-PROVIDER` | `deferred/not_run` | source：LINE delivery worker contract；runtime：provider target／recipient／quota未確認；terminal：真實 provider delivery `not_run`。 |
| `CUR-LINE-BABYLOG-MEDIA-01` | `partial` | source：20 §5.4 media contract與Scheduling owner；runtime：純文字 lane可局部存在，media caller／controlled staging仍缺；terminal：NAS staging／digest／cleanup／readback `not_run`。 |
| `CUR-LINE-AI-FEEDBACK-01` | `in-progress` | source：20 §6.3 feedback owner／identity／receipt／ticket contract已存在；runtime：正式 source與implementation尚缺；terminal：feedback Query／record／receipt／readback與provider effect `not_run`，不得用local counter。 |
| `CUR-LINE-QA` | `deferred/not_run` | source：26／20 catalog與Knowledge source gap；runtime：workbook逐題 owner review未完成；terminal：owner sign-off／publish `not_run`。 |
| `CUR-CLOUD-01` | `deferred/not_run` | source：18 deployment governance；runtime：exact project／operator／budget／rollback target未確認；terminal：external deployment `not_run`。 |
| `CUR-RETIRE-01` | `deferred/not_run` | source：19 entry governance；runtime：replacement／exact target／maintenance window未完成；terminal：production entry switch／不可逆 retirement `not_run`。 |

## 4. Superseded anomaly requirements

下列舊要求已由最新 anomaly reachability／current-state 裁決取代，不再是 Task 96 待辦或 completion gate：

- 13-code anomaly owner backend prerequisite 與 15-code manual action／terminal matrix。
- `GOVSUB-007` anomaly owner stage、`PAYOUT-002`、`GOVSUB-001`～`GOVSUB-005` recovery surfaces。
- `IMPORT-003` original-review→new HCM anomaly lineage、`IMPORT-006` deterministic rebuild／corrected-source branch。
- Scheduling invariant repair UI、`LINE-004` duplicate-root manual recovery，以及把 automatic retry／replay in progress／readback incomplete 當成 business anomaly。

退役碼的正常 owner validation、focused tests、transaction guard 與必要 migration readback 可留在各自 owner evidence；
它們不會因退出 Anomalies 而產生新的 manual-recovery product。

## 5. Residual contradiction and continuation rules

- 任何 preserve-data upgrade（尤其 1019）、1020／1021 qualification、schema boundary、public entry、Browser、
  provider、NAS、deployment、production、performance 或 destructive cutover，均須另有新人工 Authority、exact target、
  bounded acceptance 與 fresh evidence。reset path 不得被重述成 upgrade PASS。
- 本表與 formal specs 不互相取代；deferred lane 仍是 Task 96 residual，後續依既有 owner package 或 current successor
  package 繼續，不得以本表自行創造新的 Authority。
- repository 外仍可能保留歷史 package／receipt 中的 `DB_CHANGE_READY`、preserve-data PASS 或 provider／Browser PASS
  結論；它們是 provenance，不是本 register 的 current acceptance。這些歷史文件本次不改寫；若需採用，必須由 successor
  以 current target 重新驗證。
- Current CI 已由 commit `859a77e718e1cc6af38318e7017d347239a4ce2f`／Actions run `33463723309` 驗證為 `completed / success`；此完成只適用 CI gate，
  不解除 1019 preserve-upgrade deferment 或任何外部／人工／schema-boundary 的 `deferred/not_run` 狀態。

## 6. Current register verification

- 本文件維持 strict UTF-8；完成本次修改後須執行 readability／status scan 與 `git diff --check`。
- 本 lane 只更新本 register；不宣稱 Task 96 complete，不把 CI gate evidence 外推為其他 lane passed。
