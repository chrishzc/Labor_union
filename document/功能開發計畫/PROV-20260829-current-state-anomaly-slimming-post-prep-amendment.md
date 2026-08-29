---
doc_type: execution-plan-amendment
declared_status: active
date: 2026-08-29
amends: PROV-20260829-current-state-anomaly-slimming-execution-plan.md
owner: anomalies / architecture-governance / owning-domains
task_level: T3
---

# Current-state 異常機制瘦身：前置處理後基線修訂

## 1. 修訂效力

本檔只修正 `PROV-20260829-current-state-anomaly-slimming-execution-plan.md` 在前置 repository/test architecture 整理後已失效的 baseline、Task 97 dependency、test path 與 inventory 假設。

本修訂**不變更**異常瘦身的八項人工產品裁決、15 current issues / 25 owner work items / 3 retire-or-merge 目標、current-state-only projection 方向、destructive DB gate、public contract gate或 owner/SSOT 原則，也**不擴張**目前 execution authority。

原計畫的 `declared_status: blocked_spec_gap` 與 `SPEC_GAP / NOT_READY` 結論繼續有效。除本檔明確修正的 stale blocker 外，其餘 readiness blockers 必須逐項完成後，才可依原計畫的重新收旂規則升級狀態。

## 2. Post-prep baseline

- 前置處理後可引用的 tracked baseline：`main@935bd95f5f1c190de3e0c6e06defb7779df3606c`。
- 該 commit 已包含 Task 97 tracked umbrella plan、`97A_Task97_前置處理後基線修訂.md`，以及 PR #57～#59 已落地的 canonical test architecture / CI 基線。
- 原計畫 frontmatter 的 `base_ref: eaca24903197400343e72342e5f03970e0fda078` 只保留為 historical planning provenance，不再作為 current execution baseline。
- 正式續跑本計畫時若 `main` 已前進，開始任何新的 read-only inventory 前必須先綁定當時 current HEAD；不得把上述 SHA 當永久固定產品基線。

## 3. Task 97 dependency 修正

原計畫中的下列敘述已失效：

- `Task 97 canonical dependency unavailable in base`
- Task 97 是本機 untracked artifact
- `UNAVAILABLE_IN_BASE`

Current disposition 改為：

```text
Task97 dependency = TRACKED_IN_PROGRESS
Task97 umbrella = document/架構重整/02_決策與退役執行記錄/97_架構一致性修復與全域驗收計畫.md
Task97 post-prep amendment = document/架構重整/02_決策與退役執行記錄/97A_Task97_前置處理後基線修訂.md
```

因此，「Task 97 canonical dependency unavailable in base」自 readiness blockers 移除。

但 Task 97 尚未 terminal。凡與 Task 97 的 writer disposition、entry governance、transaction ownership、shared API/router、legacy retirement、schema/release 或 global acceptance 重疊的 anomaly lane，仍維持 `blocked_by_task97_priority` / wait-for-current-evidence 規則；不能把「dependency 已 tracked」誤解成 Task 97 已完成。

## 4. 仍有效的 NOT_READY blockers

移除 stale Task97-unavailable blocker 後，至少下列 blockers 仍有效，且本 amendment 不宣稱已解決：

1. 15-code owner action source map 尚未 terminal-ready。
2. 25 owner replacements / work items 尚未完整具備 typed Query、owner UI、completion predicate 與 replacement readback。
3. 15-code subject scalar normalization 與 public redaction views 尚未完成。
4. bounded recheck owner-lock 與 maintenance subject-universe mappings 尚未完成。
5. dependency inventory 尚缺逐項 executable successor / deletion gate。
6. destructive migration target、backup implementation、allowlisted disposable DB 驗證與 Authority 尚未完成。

所以 current convergence 仍是：

```yaml
spec_route:
  status: SPEC_GAP
convergence:
  status: NOT_READY
```

## 5. Canonical test path 修正

前置 test migration 已把多個 Anomalies owner-local tests 從 flat `tests/` root 移至 canonical owner tree：

```text
tests/domains/anomalies/subsystems/anomalies/
tests/domains/anomalies/subsystems/anomalies/integration/
```

目前 Test Map 明確把 anomaly reclassification domain、repository、Staff Payables owner-query adapter、necessity lifecycle / producer cutover 與 root-fact projection repository 等列為 owner-local coverage。

因此原計畫 delete/rewrite inventory 中的下列 flat paths只可作 historical provenance，不可作 current path identity：

```text
tests/test_anomaly_reclassification_domain.py
tests/test_anomaly_reclassification_owner_query_adapter.py
tests/test_anomaly_reclassification_repository.py
```

執行 delete / replacement gate 時必須先 resolve current canonical path，再判斷該測試是在保護「即將退役的 anomaly 語意」還是仍保護 current owner-local contract。不得因原 flat path 已不存在就自動視為 test 已刪除，也不得把 relocation 本身當成產品語意完成。

仍刻意留在較高 boundary 的 schema / Task97 / cross-domain / disposable-MySQL tests，依 current Test Map 分類處理，不機械搬入 owner-local root。

## 6. 99-path inventory 失效規則

原計畫的 `99/99` direct-reference inventory 是舊 baseline 的 read-only coverage，不再可作 current denominator。

原因包括：

- owner-local test 路徑已 canonicalize；
- Anomalies Test Map 已更新；
- Task 97 tracked artifacts / dependency routing已落地；
- PR #57～#59 前置修正已改變部分 source/test reference topology。

所以在 ANM-SLIM-01～07 任何 production施工重新取得 Authority 之前，必須在當時 current HEAD 重跑 direct-reference scan，重新產生 denominator 與每列 current path / successor / readback / deletion gate。舊 99-path 表只保留 historical evidence。

## 7. Regression / preflight 修訂

異常瘦身後續每個 bounded slice 在進 broader regression 前，先使用 current canonical owner gate：

```text
Anomalies canonical owner tests
→ cross-domain workflow boundaries（若受影響）
→ 12-owner canonical CI preflight
→ 原計畫要求的 focused / API / React / migration / DB / Browser / full-suite gates
```

12-owner canonical CI 已在前置 baseline 上通過，但只證明 canonical owner roots、build 與指定 cross-domain set；不能取代本計畫自己的 owner action、public contract、destructive migration、DB、Browser 或 Task 97 terminal gates。

## 8. Task 97 terminal 後的必要 refresh

Task 97 terminal 或使用者另行調整優先序後，異常瘦身不得直接從舊 ANM-SLIM package 繼續寫 code；先做一次 bounded refresh：

1. 綁定 current HEAD。
2. 讀取 Task 97 final writer / entry / transaction / legacy-retirement evidence。
3. 重跑 15-code source map 與 25 owner replacement drift check。
4. 重跑 direct-reference inventory denominator。
5. 將所有 historical flat test identities解析到 current canonical paths。
6. 重新判斷共享 hot spots 與 write set。
7. 只有原計畫其餘 NOT_READY blockers 也全部關閉時，才可依原重新收旂 gate考慮把 plan 狀態升級。

本 amendment 不授權 production、schema、migration、provider、deployment、entry switch 或 destructive cleanup。
