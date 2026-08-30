---
doc_type: execution-authority-amendment
declared_status: active
date: 2026-08-30
amends:
  - PROV-20260829-current-state-anomaly-slimming-execution-plan.md
  - PROV-20260829-current-state-anomaly-slimming-post-prep-amendment.md
owner: anomalies / architecture-governance / owning-domains
task_level: T3
---

# Current-state Anomalies：Task 97 Authority reconciliation

## 1. 目的

本檔只修正 Anomalies 瘦身文件與 Task 97 已落地 current state 之間的 Authority／狀態衝突，不新增產品裁決。

舊 execution plan 的 `planning / read-only inventory only` 是 Task 97 取得更高 priority、完成 2026-08-30 additive successor裁決與部分 zero-reference retirement 之前的 gate。它不能再用來否定 Task 97 已依 latest human Authority 完成的 exact local changes；但 Task 97 的 local implementation也不能被外推成 production cutover、destructive DB cleanup或無界 legacy deletion authority。

控制順序固定為：

```text
latest human Authority
→ current formal Domain SSOT
→ Task 97 latest active stabilization amendment
→ 本 authority reconciliation
→ 2026-08-29 anomaly slimming execution plan / post-prep amendment（僅保留未被取代內容）
```

## 2. Current exact interpretation

### 2.1 已由 Task 97 取得 authority 並可保留的 current成果

以下只要 current-head stabilization證明沒有 regression，即視為已裁決 local successor／internal retirement，不重開產品設計：

- additive `1016_current_anomaly_issues.sql` 與 current-only projection方向。
- generic durable `anomaly.recheck` 方向；不得建立 anomaly-specific claim／delivery history。
- predicate false直接刪 current row、不保存 resolved occurrence/history。
- 已有 replacement 且 production zero-reference／public compatibility gate已明確成立的 internal source retirement。
- legacy necessity-reclassification public entry在 external caller未知時保留 stable typed `410 Gone`，而不是 physical route deletion。
- owner mutation＋recheck intent、projection reconcile＋intent complete的 outer-UoW原則。

這些成果只在「current CI／current artifact／exact zero-reference」仍成立時保留；若 stabilization 發現 breakage，只修 defect，不藉機擴張架構。

### 2.2 仍未授權的效果

以下內容仍固定禁止，除非取得新的 exact Authority 與對應 gate：

- drop legacy anomaly tables、columns、triggers或 migration provenance。
- 修改 immutable published migration artifacts。
- production／`union_db` schema apply、business-row backfill或 destructive cleanup。
- deployment、entry switch、provider effect或 runtime cutover宣告。
- 因 local static zero-reference 就刪除 external caller未知的 public HTTP entry。
- 新增 `1019+` anomaly schema，除非 current 1016驗證證明存在必須修正且無法在既有 successor contract內修復的 defect，並重新取得 scope gate。

## 3. 「舊 source 不得刪除」的精確修正

`06_Anomalies_Domain.md` 舊文字「舊 source、schema 與 tests仍是 live-drift evidence；在後續 cutover gate完成前不得刪除」必須按下列精確語意解讀：

1. **schema／migration provenance**：仍受保護，在 destructive DB gate與 runtime cutover前不得 physical drop／rewrite。
2. **public entry**：external caller未知時保留 stable typed 410 + replacement identifier；不得因 local zero-reference直接刪 route identity。
3. **internal implementation source**：若已被 current successor完全取代、production/static caller為0、focused regression存在、沒有 history／rollback obligation，而且 Task 97 exact retirement receipt已成立，可以由 Task 97 latest Authority退役；不必為了保存 live-drift evidence永久留 dead code。
4. **tests**：只保護已退役語意的 obsolete test可與 internal source一起移除，但必須有 successor contract test；保護 public 410、owner boundary、rollback、current projection或 zero-reference oracle的測試必須保留。

因此，「保留 migration/data rollback evidence」與「永久保留 dead Python implementation」不是同一要求。

## 4. Current Anomalies status

在 Task 97 stabilization完成前，Anomalies 不再使用舊的單一 `blocked_spec_gap / read-only only` 描述；current status改為：

```yaml
anomalies_task97_alignment:
  product_direction: APPROVED_ADDITIVE_SUCCESSOR
  local_successor_implementation: PRESENT_REQUIRES_STABILIZATION
  internal_zero_reference_retirement: PARTIALLY_EXECUTED
  public_external_entries: KEEP_TYPED_410_WHEN_CALLER_UNKNOWN
  destructive_db_cleanup: NOT_AUTHORIZED
  runtime_cutover: NOT_CONFIRMED
  task97_stabilization: REQUIRED
```

這不是把整份 Anomaly 瘦身計畫升級成 completed／approved-for-cutover；原本尚未完成的 15-code owner action、25 owner replacement、runtime detector/lock evidence、external caller、DB engine、backup/restore、deployment/cutover等 gate仍有效，只是它們不再否定已經獲得 Authority 的 bounded local successor成果。

## 5. 與 Task 97 finishing lane 的邊界

在 `97B_Task97_current_head_stabilization_amendment.md` exit gate通過前：

- 不再新增 Anomaly retirement slice。
- 不再新增 Anomaly schema part。
- 不重新分類 15／25／3 product taxonomy。
- 只允許修 current CI、undefined names、import/reference drift與直接 regression。

stabilization通過後，Anomalies只允許處理 Task 97 已列出的 existing finishing gates：current exact writer exits、runtime detector/lock composition、DB 1016 fresh/preserve engine evidence、external/public cutover與legacy zero-reference gate。任何新設計先另列 future debt，不吸回 Task 97。

## 6. Required reconciliation evidence

後續 Agent 在宣稱 Anomalies lane可繼續前必須同時證明：

- current HEAD GitHub build／governance／cross-domain／12-owner preflight全綠。
- current Anomalies canonical tests與 affected cross-domain tests通過。
- `1016` static manifest／descriptor／fresh assembly一致；DB engine缺 credential時維持 `BLOCKED_ENGINE_EVIDENCE`。
- 已刪 internal source沒有 current inbound reference，且 public unknown-caller route仍按 typed 410規則存在。
- current writer／entry／script artifacts由 generator重新產生，不能沿用 dirty-worktree hash。

## 7. Current conclusion

```text
ANOMALIES_DIRECTION_NOT_REOPENED
ANOMALIES_STABILIZATION_REQUIRED
DESTRUCTIVE_CUTOVER_NOT_AUTHORIZED
```

本 amendment 的目的只有一個：讓後續 Agent既不因舊 `read-only only` 文件回滾已核准 successor，也不把 Task 97 的 bounded local retirement誤解成可以繼續無界刪除的 Authority。
