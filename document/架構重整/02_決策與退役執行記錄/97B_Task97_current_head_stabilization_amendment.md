---
doc_type: work-package-amendment
declared_status: active
date: 2026-08-30
task_id: 97
amends: 97_架構一致性修復與全域驗收計畫.md
supersedes_current_checkpoint: 13.27
owner: architecture-governance / domain-owners / integration-writer
stabilization_status: completed
current_receipt: ../03_追蹤清單與證據/evidence/task97_current_head_stabilization_receipt_75827fb.md
---

# Task 97 current-head stabilization amendment

## 1. 修訂目的與效力

本檔是 Task 97 在 `main` 已接收大型 WIP checkpoint 後的 current execution successor。它不刪除 `97_架構一致性修復與全域驗收計畫.md` 的 13.13～13.27 歷史紀錄，也不變更七項正式裁決、WP0～WP8、owner／SSOT／UoW 原則、DB／runtime／deployment authority 或 terminal acceptance。

本檔只修正三件已發生的 current-state drift：

1. `13.27` 仍描述 `HEAD=origin/main=153d42bedcf81220d3f5f29915ff3aced1ec99c7` 與未 commit／push 的 dirty-worktree 狀態，但該批內容已落到 `main@5dfa3b9f9224c544182b5b84f9485dc4d9934968`。
2. `main@5dfa3b9...` 的 GitHub Actions run #238 為 `failure`；因此 13.27 的 local full-suite 結果不得被外推為 current-head acceptance。
3. `153d42b... → 5dfa3b9...` 是單一大型 WIP commit，跨 API、Domain、Subsystem、Infrastructure、scripts、governance artifacts 與 DB 1015～1018。Task 97 後續必須恢復 bounded slice 規則，不再繼續吸收新的 architecture debt。

若本檔與 13.13～13.27 對「current HEAD／current CI／下一個可執行動作」的描述衝突，以本檔為準；歷史數字仍只作 provenance。

## 2. Current stabilization baseline

```yaml
stabilization:
  baseline_branch: main
  baseline_commit: 5dfa3b9f9224c544182b5b84f9485dc4d9934968
  workflow_run: 238
  workflow_conclusion: failure
  architecture_compliance_confirmed: false
  new_architecture_work_allowed: false
```

`main@5dfa3b9...` 相對上一個 tracked docs baseline `153d42b...` 為 1 commit ahead；該 commit 約 `+37412 / -44259`，必須視為待穩定化的整合 checkpoint，而不是可繼續無界擴張的 execution base。

## 3. Current CI truth

GitHub Actions run #238 的 current-head結果：

- 12-owner canonical matrix：全部成功。
- cross-domain workflow boundaries：成功。
- build：失敗。
- Agent governance validator：因 build 前置 flake8 失敗而 skipped。

build 目前有 7 個 `F821 undefined name` occurrences：

1. `infrastructure/mysql/anomaly_runtime.py` 呼叫不存在的 `project_government_subsidy_reversal_page`；current import 是 `project_government_subsidy_reversal_anomaly_page`。
2. `scripts/run_contract_signing_normal_chain.py` 使用未定義 `build_anomaly_runtime`。
3. `scripts/run_task96_hob_route_a.py` 使用未定義 `build_anomaly_runtime`。
4. `tests/test_finance_import_disposable_mysql_e2e.py` 使用未定義 `MySqlSubsidyAdvanceRecoveryRepository`。
5. 同檔一處使用未定義 `get_connection`。
6. 同檔另一處使用未定義 `get_connection`。
7. `tests/test_wp77_disposable_mysql_e2e.py` 使用未定義 `time`。

在這些 current-head defects 關閉前，不得把 `97.6 local_full_suite_passed_external_gates_blocked` 解讀為 current repository已通過 local acceptance。

## 4. Stabilization hard stop

直到本節 exit gate 全部通過，Task 97 固定禁止：

- 新增 `1019+` schema part、release manifest、descriptor 或 fresh assembly scope；唯一例外是 1015～1018 本身驗證失敗所證明必須修正的 defect，且不得改 published immutable artifact。
- 新的 legacy physical deletion／retirement；只允許修復 current build／import／reference defect，以及為既有已裁決 retirement 恢復一致性所必需的最小 correction。
- 新的跨 Domain owner redesign、T3 semantic expansion、compatibility layer 或替代架構。
- 為了讓數字下降而重新分類 writer／entry／script，除非有 exact caller／source-lock／replacement evidence。
- 把缺 DB credential、external evidence、runtime／deployment authority 降級成 skip、pass 或 assumed-complete。

## 5. Stabilization execution order

只允許依下列順序工作：

1. 修正上述 F821 與其直接暴露的最小 import/name defect，不順手重構。
2. 執行 strict flake8 fatal gate：`E9,F63,F7,F82`。
3. 單獨執行 `python scripts/validate_agent_governance.py`，即使 lint gate 失敗也必須取得獨立 governance 結果；後續 workflow 應把 governance validator 拆成獨立 job或等價不被 lint skip 的 gate。
4. 重跑 build、cross-domain boundaries、12-owner canonical matrix。
5. current HEAD 全綠後，重新生成／驗證 entry、production-script、writer、repository-commit artifacts；只有 generator 輸出與 exact source state 一致才可更新 current counts/hash。
6. 重新跑 local full Python／React current gates；需要 disposable MySQL 的 cases 必須保持 `BLOCKED_ENGINE_EVIDENCE`，不可假裝已執行。
7. 建立新的 hash-bound stabilization receipt，綁定「修正後 exact HEAD + GitHub Actions successful run」。完成前不得進 finishing lanes。

## 6. Finishing lanes after stabilization

只有 stabilization exit gate 全部成功後，Task 97 才恢復下列已存在 finishing work；不得新增第七類 lane：

- existing writer `migrate_then_remove` exits。
- existing entry `blocked_external_evidence` 與 2 個 canonical rewrite。
- existing production-script rewrite／delete／caller-evidence gates。
- 1015～1018 disposable fresh／preserve engine verification與其 runtime composition。
- Access T3 sink、既有 runtime／deployment／cutover gate。
- WP8 terminal acceptance。

已完成的 97.3 repository／route UoW、canonical test routing、Contract Signing owner model等只做 drift check；沒有 drift不得重做。

## 7. Current segmented status

| Slice | Current status | Stabilization interpretation |
|---|---|---|
| `97.1` inventory／governance | `passed_with_terminal_blockers` | counts/hash 必須在 CI 修正後重新綁 current HEAD；不得沿用 13.27 作永久 denominator。 |
| `97.2` Clients／typed Query／UoW | `local_contract_passed` | 不重開產品設計；physical delete仍只由 external caller closure決定。 |
| `97.3` repository／route UoW | `passed_drift_check_only` | 322／322 等數字在 current generator重跑前只作上一 checkpoint evidence；禁止重新設計。 |
| `97.4` Media／Anomaly | `stabilization_required` | local successor方向保留；禁止新 schema、新 retirement，先恢復 current CI／Authority一致性。 |
| `97.5` scripts／entry | `inventory_passed_remediation_blocked` | 只處理既有 exact gates；禁止擴張 inventory taxonomy。 |
| `97.6` final acceptance | `not_currently_passed` | run #238 build failure；必須以修正後 HEAD 的 successful CI + current local gates重建。 |

## 8. Exit gate

只有同一 exact HEAD 同時滿足以下條件，才可結束 stabilization：

```yaml
stabilization_exit:
  flake8_fatal: PASS
  agent_governance_validator: PASS
  github_build: PASS
  github_cross_domain: PASS
  github_12_owner_matrix: PASS
  current_artifact_regeneration: PASS
  local_python_non_engine: PASS
  react_current_gate: PASS
  db_engine_missing_credentials: BLOCKED_ENGINE_EVIDENCE_or_PASS
  new_schema_or_architecture_scope_added: false
```

exit 後新增一個短 current-head receipt；不要再把整個 repository-wide remediation 壓成一個新的超大型 WIP commit。

## 9. Current conclusion

```text
TASK97_STABILIZATION_CONFIRMED
ARCHITECTURE_COMPLIANCE_NOT_CONFIRMED
```

hash-bound current result 由 [Task 97 current-head stabilization receipt](../03_追蹤清單與證據/evidence/task97_current_head_stabilization_receipt_75827fb.md) 保存。後續只可恢復第 6 節既有 finishing lanes，仍不得新增架構範圍，也不得把 stabilization success 外推成 WP8 terminal acceptance。
