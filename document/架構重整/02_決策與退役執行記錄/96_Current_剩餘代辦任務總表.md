---
doc_type: gap-register
declared_status: completed-closeout
date: 2026-09-01
owner: architecture-governance / product-and-domain-owners
priority_authority_date: 2026-08-31
---

# Task 96 剩餘代辦總表：bounded closeout

> Task 96 已停止作為 active gap register。本文件只記錄本次明確收尾範圍、已被 current evidence 支持的
> repository-local 結果，以及移出 Task 96 的 deferred／not-run successor。`completed` 只表示表內列明的
> repository-local scope；不表示 preserve-data upgrade、完整產品功能、真實 provider、Browser、production、
> deployment 或 schema boundary 已完成。正式語意仍以 `01_規格基線` 與最新人工裁決為準，本文件不修改正式規格。

## 1. Closeout status and stopping language

- **Declared status：** `TASK96_REPOSITORY_LOCAL_CLOSEOUT_WITH_DEFERRED_EXTERNAL_WORK`。
- **Active Task 96 IDs：** 0。下表所有 ID 均為 `completed`、`superseded` 或 `deferred/not_run`，不再形成 Task 96 的施工隊列。
- **CI closure：** `completed`。commit `37c9d063` 已推送至 `origin/main`，GitHub Actions run
  [`33460244467`](https://github.com/chrishzc/Labor_union/actions/runs/33460244467) 已完成且所有 jobs 綠燈；此結果只關閉
  current CI gate，不外推 DB、provider、Browser、production 或其他 deferred boundary。
- **DB upgrade boundary：** 使用者已明確要求停止修正 1019 preserve-upgrade script。下列 reset path 是
  development `lu_test_*` 的 disposable reset／current-schema bootstrap 與啟動證據，不是 1003→current
  preserve-data upgrade，也不宣稱 1019、1020 或 1021 qualification 通過。
- **Effect ceiling：** 本次只更新本表。沒有 production、`union_db`、provider send／publication、NAS、deployment、
  entry switch、performance benchmark、destructive cutover 或其他資料庫操作授權。

## 2. Accepted bounded repository-local closeout evidence

下列結果已由 current task evidence 支持，且只在所列 scope 內成立：

| Scope | Result | Boundary |
|---|---|---|
| Development reset／bootstrap | `completed` | `scratch/task96/lu_test_1-bootstrap.json` 記錄 `lu_test_1` reset/rebuild receipt 為 `committed`，再讀回 current canonical schema；這是 disposable reset，沒有 preserve-data upgrade claim。 |
| Current-schema guard | `completed` | updater 的 `--require-current` 對已建立的 `lu_test_1` readback 通過；此 readback 不證明 1019 preserve-upgrade。 |
| No-auth local startup | `completed` | FastAPI、React、monitor、durable worker、incident worker 以 development no-auth path 啟動；`GET /health` 回 200，React `/admin/` root 可讀。 |
| Current-head CI | `completed` | `origin/main` commit `37c9d063` 對應 GitHub Actions run [`33460244467`](https://github.com/chrishzc/Labor_union/actions/runs/33460244467)；exact flake8、governance、React cancellation、disposable MySQL、canonical owner matrices 與 cross-domain boundary jobs 全部成功。 |
| LINE provider worker | `deferred/not_run` | 本次啟動刻意跳過 LINE provider worker；沒有 provider／recipient／quota／外部 delivery evidence。 |
| LINE repository-local integration | `completed` | `03_追蹤清單與證據/evidence/PROV-20260830-line-anomalies-slimming-integration-receipt.md` 支持 M1～M4 的 repository-local focused contract／regression、typed owner boundary 與既有 LINE-006 readback alignment；browser sandbox、provider、DB engine 與 production boundary 不在此結果。 |
| Anomalies repository-local integration | `completed` | 同一整合 receipt 支持 current-state registry／typed current-only mapping／LINE-004 owner consumer 與退役碼 routing 的 repository-local integration；LINE-006 完整人工處理功能及其他 owner contract 不因本列完成而存在。 |

## 3. All former Task 96 lanes

| ID | Status | Closeout disposition / successor requirement |
|---|---|---|
| `CUR-LOCAL-DB-1003-CURRENT-01` | `superseded` | 原 1003→current ordered preserve／resume／normal-startup gate 已依使用者指示停止；不得保留或引用舊 preserve PASS。未來若要做保留資料升級，須另取得明確 DB Authority、合法 `lu_test_*` target 與新 receipt。 |
| `CUR-LOCAL-DB-PORTABILITY` | `superseded` | 舊 portability／preserve-upgrade lane 不再是 Task 96 acceptance。第 2 節的 `lu_test_1` reset／current readback／no-auth startup 只作開發測試路徑，不能升格為 portability 或 production evidence。 |
| `CUR-CI-CURRENT-HEAD-ACTIONS-01` | `completed` | `origin/main` commit `37c9d063` 的 GitHub Actions run [`33460244467`](https://github.com/chrishzc/Labor_union/actions/runs/33460244467) 已 `completed / success` 且所有 jobs 綠燈；只完成 current CI gate，不外推其他 Task 96 deferred boundary。 |
| `CUR-LINE-MODULES-1-4-CLOSURE-01` | `completed` | 只收斂 repository-local LINE M1～M4 integration／focused regression／typed boundary。verified-token LIFF、provider、deployment、production DB、未核准 schema 與 external side effect 均移出 Task 96。 |
| `CUR-ANOMALY-OWNER-BACKEND-PREREQUISITES-01` | `superseded` | 最新 reachability 裁決已退出原 13-code owner prerequisite stage；`GOVSUB-007` 回 Government Subsidy 正常 owner flow，不建立 Anomalies 第二套 manual-recovery framework。 |
| `CUR-P0-ANOMALY-RECOVERY-01` | `completed` | 只完成 repository-local current-state integration：runtime routing 維持唯一 `LINE-006` 產品入口、`BECLASS-001` 回 Case Import／Client owner follow-up、退役碼不再作 current presentation。LINE-006 人工 remediation 與其他 owner predicate 仍 `deferred/not_run`。 |
| `CUR-P0-HISTORICAL-PAYMENT-SETTLEMENT-01` | `deferred/not_run` | 不把 1020 owner payment settlement qualification、真 MySQL lifecycle 或 enabled-human Browser Apply 寫成 PASS；後續須有新 owner package、合法 target 與 acceptance Authority。 |
| `CUR-CONTRACT-01` | `deferred/not_run` | enabled persisted-human Chrome chain、final PDF／metadata／storage readback 未執行；需新 Browser／storage target 與 owner acceptance。 |
| `CUR-FILE-NAS-01` | `deferred/not_run` | 真 NAS list／download／readback 未執行；需受控 NAS target、credential 與新外部 evidence。 |
| `CUR-LIFF-PROFILE-01` | `deferred/not_run` | public endpoint／LIFF verified-token boundary 未取得新 Authority；不得以 no-auth local startup 代替。 |
| `CUR-LINE-RICHMENU-01` | `deferred/not_run` | Rich Menu provider qualification、publication lineage 與 sandbox receipt 未執行；需 exact provider target。 |
| `CUR-CONTRACT-FULL-PREVIEW-01` | `deferred/not_run` | remaining owner source cells、public preview entry 與 schema boundary 未收斂；需新 contract／owner decision。 |
| `CUR-LINE-RICHMENU-AUTH-01` | `deferred/not_run` | authenticated queue→worker→provider receipt／readback 未執行；不由 repository-local tests 代替。 |
| `CUR-UX-01` | `deferred/not_run` | responsive／keyboard／WCAG 與 owner語意的 fresh UX／Chrome acceptance 未執行；需新 UX acceptance scope。 |
| `CUR-UI-01` | `deferred/not_run` | 逐頁 visual／responsive／WCAG comparison 未執行；需新的 UI acceptance owner。 |
| `CUR-PERF-01` | `deferred/not_run` | API／React／DB benchmark environment 不存在，沒有 baseline 或 performance PASS；需同環境新 benchmark Authority。 |
| `CUR-INTERNAL-UI-UNMASKED-01` | `deferred/not_run` | internal UI unmasked display 的分批盤點與驗收未執行；需依 current access／UX owner 建立 successor。 |
| `CUR-UI-STITCH-UNIFICATION-01` | `deferred/not_run` | UI stitch 尚未取得 fresh surface inventory／design adoption evidence；不再阻擋本 Task 96 closeout，後續另包。 |
| `CUR-LIFF-E2E` | `deferred/not_run` | verified-token LIFF E2E 未執行；需 exact sandbox、token 與新 external acceptance。 |
| `CUR-LINE-PROVIDER` | `deferred/not_run` | 真實 LINE provider delivery 未執行；不宣稱 provider、recipient 或 quota 通過。 |
| `CUR-LINE-BABYLOG-MEDIA-01` | `deferred/not_run` | controlled NAS staging／digest／cleanup／readback 未執行；需新 NAS authority。 |
| `CUR-LINE-AI-FEEDBACK-01` | `deferred/not_run` | feedback owner contract 與 provider effect 未取得；不得以 browser-local counter 代替。 |
| `CUR-LINE-QA` | `deferred/not_run` | workbook review input 的逐題 owner review／publish 未完成；需新 owner sign-off。 |
| `CUR-CLOUD-01` | `deferred/not_run` | external deployment 未執行；需 exact project、operator、budget、rollback scope 與 deployment Authority。 |
| `CUR-RETIRE-01` | `deferred/not_run` | production entry switch／不可逆 retirement 未執行；需 exact target、rollback gate 與新 Authority。 |

## 4. Superseded anomaly requirements

下列舊要求已由最新 anomaly reachability／current-state 裁決取代，不再是 Task 96 待辦或 completion gate：

- 13-code anomaly owner backend prerequisite 與 15-code manual action／terminal matrix。
- `GOVSUB-007` anomaly owner stage、`PAYOUT-002`、`GOVSUB-001`～`GOVSUB-005` recovery surfaces。
- `IMPORT-003` original-review→new HCM anomaly lineage、`IMPORT-006` deterministic rebuild／corrected-source branch。
- Scheduling invariant repair UI、`LINE-004` duplicate-root manual recovery，以及把 automatic retry／replay in progress／readback incomplete 當成 business anomaly。

退役碼的正常 owner validation、focused tests、transaction guard 與必要 migration readback 可留在各自 owner evidence；
它們不會因退出 Anomalies 而產生新的 manual-recovery product。

## 5. Successor and residual contradiction rules

- 任何 preserve-data upgrade（尤其 1019）、1020／1021 qualification、schema boundary、public entry、Browser、
  provider、NAS、deployment、production、performance 或 destructive cutover，均須另有新人工 Authority、exact target、
  bounded acceptance 與 fresh evidence。reset path 不得被重述成 upgrade PASS。
- 本表與 formal specs 不互相取代；後續若要重新開啟任一 deferred lane，應建立或更新其 current owner package，並由新 register
  吸收結果，不把 Task 96 重新標回 active。
- repository 外仍可能保留歷史 package／receipt 中的 `DB_CHANGE_READY`、preserve-data PASS 或 provider／Browser PASS
  結論；它們是 provenance，不是本 closeout 的 current acceptance。這些歷史文件本次不改寫；若需採用，必須由 successor
  以 current target 重新驗證。
- Current CI 已由 `origin/main` commit `37c9d063`／Actions run `33460244467` 完成；此完成只適用 CI gate，不能解除
  1019 preserve-upgrade deferment 或任何外部／人工／schema-boundary 的 `deferred/not_run` 狀態。

## 6. Closeout verification

- 本文件已維持 strict UTF-8，並完成 readability／status scan。
- `git diff --check` 應在本次文件變更後通過。
- 本次未修改 formal specs、source、tests、DB、migration script、generated release、provider configuration 或其他文件。
