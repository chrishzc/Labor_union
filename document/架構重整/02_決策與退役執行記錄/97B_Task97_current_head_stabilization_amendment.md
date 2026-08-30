---
doc_type: work-package-amendment
declared_status: completed
date: 2026-08-30
task_id: 97
amends: 97_架構一致性修復與全域驗收計畫.md
supersedes_current_checkpoint: 13.27
owner: architecture-governance / domain-owners / integration-writer
stabilization_status: completed
repository_local_status: completed
production_acceptance: not_run
db_engine_acceptance: not_run
current_receipt: ../03_追蹤清單與證據/evidence/task97_repository_local_closeout_receipt_a48caa8.md
---

# Task 97 current-head stabilization amendment

## 1. 修訂目的與效力

本檔是 Task 97 在 `main` 已接收大型 WIP checkpoint 後的 current execution successor。它不刪除
`97_架構一致性修復與全域驗收計畫.md` 的13.13～13.27歷史紀錄，也不變更七項正式裁決、
owner／SSOT／UoW原則或DB／runtime／deployment authority。2026-08-30最新人工Authority另將Task 97
terminal acceptance改為repository-local architecture completion；其效力與結果記於第10節。

本檔只修正三件已發生的 current-state drift：

1. `13.27` 仍描述 `HEAD=origin/main=153d42bedcf81220d3f5f29915ff3aced1ec99c7` 與未 commit／push 的 dirty-worktree 狀態，但該批內容已落到 `main@5dfa3b9f9224c544182b5b84f9485dc4d9934968`。
2. `main@5dfa3b9...` 的 GitHub Actions run #238 為 `failure`；因此 13.27 的 local full-suite 結果不得被外推為 current-head acceptance。
3. `153d42b... → 5dfa3b9...` 是單一大型 WIP commit，跨 API、Domain、Subsystem、Infrastructure、scripts、governance artifacts 與 DB 1015～1018。Task 97 後續必須恢復 bounded slice 規則，不再繼續吸收新的 architecture debt。

若本檔與 13.13～13.27 對「current HEAD／current CI／下一個可執行動作」的描述衝突，以本檔為準；歷史數字仍只作 provenance。

## 2. Historical trigger and confirmed stabilization result

### 2.1 Historical stabilization trigger

```yaml
stabilization_trigger:
  historical_only: true
  baseline_branch: main
  baseline_commit: 5dfa3b9f9224c544182b5b84f9485dc4d9934968
  workflow_run: 238
  workflow_conclusion: failure
  architecture_compliance_confirmed: false
  new_architecture_work_allowed: false
  superseded_as_current_truth_by: ../03_追蹤清單與證據/evidence/task97_current_head_stabilization_receipt_75827fb.md
```

`main@5dfa3b9...` 相對上一個 tracked docs baseline `153d42b...` 為 1 commit ahead；該 commit 約 `+37412 / -44259`，當時必須視為待穩定化的整合 checkpoint，而不是可繼續無界擴張的 execution base。上述內容只保存 stabilization 的歷史觸發，不再描述 current repository 狀態。

### 2.2 Confirmed stabilization result

```yaml
stabilization_result:
  validated_branch: main
  validated_head: 75827fbcc139e87d16a3f753c4478fc9e82910f1
  validated_workflow_run: 33298062001
  validated_workflow_conclusion: success
  receipt_commit: b65d78ec7365a62150f1e65c6c4896c04909855e
  receipt_workflow_run: 33298210829
  receipt_workflow_conclusion: success
  stabilization_confirmed: true
  architecture_compliance_confirmed: false
```

此結果由 hash-bound receipt 綁定 validated HEAD、CI workflow、canonical roots、artifact generators 與 acceptance gates。current `main` 可在 receipt-only 或 docs-only commit 後前進；除非 source、workflow、generator 或 acceptance gate 發生 material change，否則不會因此使 validated stabilization result 失效。

## 3. Historical failure trigger and confirmed CI successor

### 3.1 Historical failure trigger

GitHub Actions run #238 是 stabilization 啟動時的 historical failure evidence：

- 12-owner canonical matrix：全部成功。
- cross-domain workflow boundaries：成功。
- build：失敗。
- Agent governance validator：因 build 前置 flake8 失敗而 skipped。

該次 build 有 7 個 `F821 undefined name` occurrences：

1. `infrastructure/mysql/anomaly_runtime.py` 呼叫不存在的 `project_government_subsidy_reversal_page`；current import 是 `project_government_subsidy_reversal_anomaly_page`。
2. `scripts/run_contract_signing_normal_chain.py` 使用未定義 `build_anomaly_runtime`。
3. `scripts/run_task96_hob_route_a.py` 使用未定義 `build_anomaly_runtime`。
4. `tests/test_finance_import_disposable_mysql_e2e.py` 使用未定義 `MySqlSubsidyAdvanceRecoveryRepository`。
5. 同檔一處使用未定義 `get_connection`。
6. 同檔另一處使用未定義 `get_connection`。
7. `tests/test_wp77_disposable_mysql_e2e.py` 使用未定義 `time`。

上述 7 個 defects 已在 bounded stabilization package 中修正，現在只作 resolved-defect provenance；沒有 material regression evidence 時不得把它們重開為 current blocker。

### 3.2 Confirmed CI successor

- validated HEAD `75827fbcc139e87d16a3f753c4478fc9e82910f1` 的 GitHub Actions run [33298062001](https://github.com/chrishzc/Labor_union/actions/runs/33298062001) 為 `success`。
- fatal Flake8 `E9,F63,F7,F82`、Agent governance、build、cross-domain workflow boundaries 與 12-owner canonical matrix 全部 `PASS`。
- receipt-only commit `b65d78ec7365a62150f1e65c6c4896c04909855e` 的 GitHub Actions run [33298210829](https://github.com/chrishzc/Labor_union/actions/runs/33298210829) 亦為 `success`。

因此 run #238 與 7 個 F821 不再是 current stabilization blocker；原finishing lanes已依第10節重新分類，
只有`REPO_LOCAL_BLOCKER`可以阻止Task 97 repository-local closeout。

## 4. Historical stabilization hard stop — satisfied

在 stabilization exit gate 通過前，Task 97 曾固定禁止：

- 新增 `1019+` schema part、release manifest、descriptor 或 fresh assembly scope；唯一例外是 1015～1018 本身驗證失敗所證明必須修正的 defect，且不得改 published immutable artifact。
- 新的 legacy physical deletion／retirement；只允許修復 current build／import／reference defect，以及為既有已裁決 retirement 恢復一致性所必需的最小 correction。
- 新的跨 Domain owner redesign、T3 semantic expansion、compatibility layer 或替代架構。
- 為了讓數字下降而重新分類 writer／entry／script，除非有 exact caller／source-lock／replacement evidence。
- 把缺 DB credential、external evidence、runtime／deployment authority 降級成 skip、pass 或 assumed-complete。

上述 stabilization hard stop 已由第 8 節 verified result 滿足。後續可恢復第 6 節既有 finishing lanes，但下列 guard 持續有效：不得新增未授權的 architecture／schema scope；不得只為降低數字而重分類 evidence；不得把缺 DB credential、external evidence或runtime／deployment authority推定為已通過；沒有 drift 時不得重做已完成 package；不得再產生無界大型 WIP checkpoint。

## 5. Historical stabilization execution order — completed

Stabilization package 已依下列順序完成：

1. 修正上述 F821 與其直接暴露的最小 import/name defect，未順帶重構。
2. strict flake8 fatal gate `E9,F63,F7,F82` 已通過。
3. Agent governance 已作為獨立 workflow job 執行並通過，不再被 lint skip。
4. build、cross-domain boundaries 與 12-owner canonical matrix 已在同一 validated HEAD 通過。
5. entry、production-script、writer、repository-commit artifacts 已依 exact source state 重新生成並驗證。
6. local non-engine Python、React tests／build／lint 已通過；disposable MySQL cases維持 `BLOCKED_ENGINE_EVIDENCE`，未偽裝成已執行。
7. 已建立新的 hash-bound stabilization receipt，綁定修正後 exact HEAD 與 successful GitHub Actions run。

本順序是已完成的歷史執行記錄。現在的可執行範圍只剩第 6 節既有 finishing lanes，且仍受第 4 節持續 guard 約束。

## 6. Finishing lanes after stabilization（historical routing）

只有 stabilization exit gate 全部成功後，Task 97 才恢復下列已存在 finishing work；不得新增第七類 lane：

- existing writer `migrate_then_remove` exits。
- existing entry `blocked_external_evidence` 與 2 個 canonical rewrite。
- existing production-script rewrite／delete／caller-evidence gates。
- 1015～1018 disposable fresh／preserve engine verification與其 runtime composition。
- Access T3 sink、既有 runtime／deployment／cutover gate。
- WP8 terminal acceptance。

已完成的 97.3 repository／route UoW、canonical test routing、Contract Signing owner model等只做 drift check；沒有 drift不得重做。

## 7. Repository-local segmented status

| Slice | Current status | Stabilization interpretation |
|---|---|---|
| `97.1` inventory／governance | `repository_local_passed` | current generators、source hashes與focused validators通過；external／production deferred列仍保留。 |
| `97.2` Clients／typed Query／UoW | `local_contract_passed` | 不重開產品設計；physical delete仍只由 external caller closure決定。 |
| `97.3` repository／route UoW | `passed` | current generator已綁定source revision `d7167b9`重跑，308／308 passed；禁止重新設計。 |
| `97.4` Media／Anomaly | `repository_local_passed` | local owner／outbox／projection契約通過；DB engine、runtime、deployment與cutover分列deferred。 |
| `97.5` scripts／entry | `repository_local_passed_with_deferred_exact_gates` | inventory與safe disposition一致；blocked exact gates只代表後續DB／production／external acceptance。 |
| `97.6` final acceptance | `TASK97_REPOSITORY_LOCAL_COMPLETE` | local Python／React、build／lint、governance、cross-domain、owner tests與DB static contract完成；production與DB engine均未執行。 |

## 8. Verified stabilization exit result

validated HEAD `75827fbcc139e87d16a3f753c4478fc9e82910f1` 已滿足 stabilization exit gate：

```yaml
stabilization_exit:
  validated_head: 75827fbcc139e87d16a3f753c4478fc9e82910f1
  flake8_fatal: PASS
  agent_governance_validator: PASS
  github_build: PASS
  github_cross_domain: PASS
  github_12_owner_matrix: PASS
  current_artifact_regeneration: PASS
  local_python_non_engine: PASS
  react_current_gate: PASS
  db_engine_missing_credentials: BLOCKED_ENGINE_EVIDENCE
  new_schema_or_architecture_scope_added: false
  conclusion: TASK97_STABILIZATION_CONFIRMED
```

完整 hash-bound 結果由 [Task 97 current-head stabilization receipt](../03_追蹤清單與證據/evidence/task97_current_head_stabilization_receipt_75827fb.md) 保存。exit 後不得再把整個 repository-wide remediation 壓成一個新的超大型 WIP commit。

## 9. Stabilization conclusion（historical layer）

```text
TASK97_STABILIZATION_CONFIRMED
ARCHITECTURE_COMPLIANCE_NOT_CONFIRMED
```

hash-bound current result 由 [Task 97 current-head stabilization receipt](../03_追蹤清單與證據/evidence/task97_current_head_stabilization_receipt_75827fb.md) 保存。後續只可恢復第 6 節既有 finishing lanes，仍不得新增架構範圍，也不得把 stabilization success 外推成 WP8 terminal acceptance。

## 10. Repository-local terminal closeout

### 10.1 Gate separation

| Classification | Result | Interpretation |
|---|---|---|
| `REPO_LOCAL_BLOCKER` | `0` | owner／SSOT／UoW、dependency、source、inventory、static contract、tests、build／lint與tracked documents均已收斂。 |
| `DEFERRED_DB_ACCEPTANCE` | `NOT_RUN / BLOCKED_ENGINE_EVIDENCE` | 缺合法disposable MySQL；沒有連接`union_db`或production。 |
| `DEFERRED_PRODUCTION_ACCEPTANCE` | `NOT_RUN` | Access T3、deployment、runtime、entry switch、cutover、smoke及rollback交由未來獨立任務。 |
| `DEFERRED_EXTERNAL_EVIDENCE` | `NOT_RUN` | unknown caller、provider、operator及external zero-reference證據維持safe blocked disposition。 |

### 10.2 Current repository-local evidence

- Access security-alert outbox只依賴caller-composed typed sink；durable intent／delivery state由Access擁有，
  Anomalies projection不擁有commit。
- writer v3為1320 records：1085 retain-canonical、235 retain-restricted、0 migrate、0 needs-decision。
- entry governance為683 records：488 active、75 operator-only、87 retired-410、33 review-required；terminal為
  488 active-canonical、75 operator-only-guarded、87 retired-410、31 blocked-external、2 rewrite。
- production scripts為86 records：38 keep、1 rewrite、6 delete、38 test-only、3 caller-blocked；14個exact
  production／DB／external gates仍是blocked/deferred，沒有被誤記為pass。
- static schema／migration、canonical owner、cross-domain、Python／React、build與lint結果由
  [repository-local closeout receipt](../03_追蹤清單與證據/evidence/task97_repository_local_closeout_receipt_a48caa8.md)保存。

```text
TASK97_REPOSITORY_ARCHITECTURE_CONFIRMED
TASK97_REPOSITORY_LOCAL_COMPLETE
PRODUCTION_ACCEPTANCE_NOT_RUN
DB_ENGINE_ACCEPTANCE_NOT_RUN
```
