---
doc_type: execution-plan-amendment
declared_status: active
date: 2026-08-29
task_id: CUR-LINE-BACKEND-SLIMMING-01
amends: LINE_BACKEND_SLIMMING_PLAN.md
owner: LINE / Integration
---

# LINE 後端瘦身：前置處理後基線修訂

## 1. 修訂效力

本檔只更新 `LINE_BACKEND_SLIMMING_PLAN.md`、`LINE_BACKEND_STATE_AUDIT.md` 與 `LINE_BACKEND_RESOLVED_WRITE_SET.md` 在 Task 97 前置 repository/test architecture 整理後的 baseline、inventory 有效性與 regression route。

本修訂**不變更** LINE 後端瘦身的核心架構裁決：

- LINE 仍只擁有 `Side-channel` 與 `LINE Product` 兩類責任。
- LINE 不取得 Client / Staff / Scheduling / Matching / Assignment / Customer Service / Payroll / Payables 的正式 business ownership。
- 跨 Domain mutation 仍必須走 formal Application/API → owner Domain → Repository → DB。
- S0～S9 工作包順序、三類 blocker、Delete Gate、destructive retention規則與「不得補 M1～M4」限制維持不變。
- Task 97 在重疊 path / Authority / transaction / governance artifact 上仍具有優先權。

## 2. Post-prep baseline

- 前置處理後可引用的 tracked baseline：`main@fe54d948ba08a7533ad6698aa7de957845932dd1`。
- 其中 `935bd95f5f1c190de3e0c6e06defb7779df3606c` 是 Task 97 post-prep amendment 落地點；後續 `fe54d948...` 只新增異常瘦身 baseline amendment，未改 LINE production behavior。
- 原 `LINE_BACKEND_STATE_AUDIT.md` 的 `baseline_head: eaca24903197400343e72342e5f03970e0fda078` 保留為 S0/S1 historical inventory provenance，不再代表 current final inventory。
- 正式續跑 LINE 瘦身時若 `main` 已前進，必須先綁定當時 current HEAD 再重掃。

## 3. S0 / S1 inventory 有效性修正

原 S0/S1 inventory 的分類邏輯仍可作 evidence，但其 counts、path topology 與 resolved write set 不可直接視為 current terminal result。

Current disposition：

```text
S0 = historical-completed / refresh-required-before-S2
S1 = historical-completed / refresh-required-before-S2
S2-S9 = blocked-by-task97-priority
```

原因：

1. Task 97 現已是 tracked in-progress dependency，不再是僅存在於 dirty/untracked worktree 的假設。
2. PR #57～#59 已改變 canonical test architecture、Contract Signing owner model、Anomalies / Scheduling relocation routing與 canonical CI coverage。
3. LINE canonical test suite 在前置 CI 中暴露並修正了 relocation-sensitive tests與實際 production contract bug；因此舊 S0/S1 baseline 之後 repo 已有 LINE-relevant drift。
4. `LINE_BACKEND_RESOLVED_WRITE_SET.md` 中的 rows 必須在 Task 97 terminal evidence後重新確認 path、caller、owner、replacement與gate，不能用舊 baseline直接施工。

S0/S1 不需要現在整批重做；在 Task 97 尚未 terminal 前，舊 inventory繼續作 planning evidence。真正準備進 S2 時才重跑 current-head refresh。

## 4. Task 97 dependency 狀態

LINE plan 的既有優先序仍有效：

```text
Task 97 governance / project slimming
→ refresh LINE S0/S1 + resolved write set
→ S2-S9
→ LINE regression
→ freeze slimmed LINE backend baseline
→ re-evaluate Task 96 LINE M1-M4 closure
```

Task 97 current state 改成明確 tracked dependency：

```text
Task97 umbrella = document/架構重整/02_決策與退役執行記錄/97_架構一致性修復與全域驗收計畫.md
Task97 post-prep amendment = document/架構重整/02_決策與退役執行記錄/97A_Task97_前置處理後基線修訂.md
Task97 status for LINE = TRACKED_IN_PROGRESS / PRIORITY_BLOCKING_OVERLAP
```

所以現在仍不應啟動 S2～S9 production refactor；但理由是 Task 97 尚未 terminal，而不是 Task 97 artifact 不存在。

## 5. Canonical LINE test architecture

current LINE Test Map：

```text
test_root: tests/domains/external-integration/subsystems/line/
integration_root: tests/domains/external-integration/subsystems/line/integration/
```

目前 owner-local integration coverage 已包含：

- delivery-task action routes
- configuration query / retirement guards
- notification rule mutation / query / replay
- verified staff service-day media upload
- Rich Menu image upload typed receipt
- typed LINE admin capabilities / health contract

Release/migration/schema、disposable-MySQL/E2E、Task97、legacy UI 與 true cross-owner tests仍留在較高 verification boundary；後續 slimming 不得為了「全部搬進 LINE root」破壞這個分層。

## 6. Regression gate 修訂

未來每個 S2～S9 bounded package 完成後，先跑 owner-local preflight，再擴大 regression：

```text
focused tests for changed path
→ LINE canonical test root
→ affected cross-domain boundary tests
→ build + 12-owner canonical matrix preflight
→ LINE plan 原有 regression scope
→ 更廣的 Task 97 / full-suite / DB / Browser gates（若該 completion contract要求）
```

前置期間 GitHub Actions run #230 與 #232 均已完成 build、cross-domain workflow boundaries與12-owner canonical matrix；這只能作 baseline evidence，不能替代 S2～S9 改動後的 current-head replay。

## 7. S0/S1 refresh 必須回答的差異

Task 97 terminal後、S2開始前，refresh至少必須重新確認：

1. LINE direct cross-domain write families current count與exact callers。
2. canonical vs legacy messaging provider send paths是否仍為2。
3. canonical vs legacy Rich Menu provider implementations是否仍為2。
4. legacy webhook / worker / identity / review code是否被Task97直接退役、rewire或保留。
5. `orders.line_group_id` projection write是否仍存在且仍屬 LINE slimming write set。
6. public compatibility entries的 current entry disposition、external caller evidence與typed 410 gate。
7. current writer inventory / entry queue對LINE paths的 final disposition。
8. affected tests現在位於 canonical owner root、higher boundary或已因真正語意退役而應刪除。

任何 row若已被Task97完成，標記 `absorbed-by-task97` 並從 LINE write set移除；不得重做。

## 8. Baseline freeze 修訂

LINE slimmed baseline只有在以下條件都滿足後才能 freeze：

- Task 97 terminal evidence已讀取並完成S0/S1 refresh。
- S2～S9所有仍適用rows完成或有明確item-level blocker。
- LINE canonical owner root在current HEAD通過。
- affected cross-domain regression通過。
- 12-owner canonical preflight通過。
- 原計畫要求的LINE existing behavior regression通過。
- blocked/not_run能力仍誠實標示，不以fixture/direct DB/manual mutation偽造PASS。

本 amendment 不授權 schema drop、historical data deletion、provider、production DB、deployment、entry switch或Task96 M1～M4新功能。
