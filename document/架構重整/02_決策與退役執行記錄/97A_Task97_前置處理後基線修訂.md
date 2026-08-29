---
doc_type: work-package-amendment
declared_status: active
date: 2026-08-29
task_id: 97
amends: 97_架構一致性修復與全域驗收計畫.md
owner: architecture-governance / domain-owners / integration-writer
---

# Task 97 前置處理後基線修訂

## 1. 修訂範圍與效力

本檔是 `97_架構一致性修復與全域驗收計畫.md` 的 post-prep amendment，只更新 Task 97 的 execution baseline、已完成前置項、測試路由與舊 checkpoint 的有效性規則。

本修訂**不變更** Task 97 的七項正式裁決、WP0～WP8 工作包邊界、owner／SSOT／UoW 原則、DB／Browser authority、terminal acceptance 或 `ARCHITECTURE_COMPLIANCE_CONFIRMED` 判定標準。若本檔與原計畫的同日較早 baseline／test checkpoint 敘述衝突，僅在上述修訂範圍內以本檔為準；核心 architecture decisions 仍以原 Task 97 umbrella plan 為準。

## 2. Post-prep execution baseline

- baseline branch：`main`
- baseline commit：`7953b6c7c0ee560d86c07216a6fd4978bd3039d1`
- 來源：PR #59 merge 後的 current main。
- 若正式啟動／續跑 Task 97 時 `main` 已超過上述 SHA，WP0 必須先以當時 current HEAD 做 drift check，再綁定新的 execution SHA；不得把本 SHA 當成永久固定產品基線。

### 2.1 已落地前置成果

1. 既有已建模 owner 的高信心 owner-local flat test migration 已收斂；已完成 Test Map closeout 的 owner 不重新做 filename-based 搬移 audit，除非 current-head drift scan 發現新的 direct-SUT owner-local case。
2. Contract Signing 已建立 current architecture Domain／Subsystem 與 canonical Test Map，18 個 owner-local tests 已移至：
   `tests/domains/contract-signing/subsystems/contract-signing/integration/`。
3. Anomalies reclassification repository 與 Scheduling matching coordination repository 的 test-location dependency 已改為 relocation-safe，並移入各自 canonical owner root。
4. LINE admin canonical coverage 已由前置 CI 修復吸收到 main；後續 #59 restack 刻意沒有把舊 stacked 版本覆蓋回去。Task 97 不應重播較舊 LINE admin assertion／source-location contract。
5. canonical CI matrix 已從 5 個 owner 擴張為 12 個 current owner roots：
   - Orders
   - Scheduling
   - Client Finance
   - Staff Payables
   - Anomalies
   - Payroll
   - Finance Import
   - Government Subsidy
   - Case Import
   - Access
   - LINE
   - Contract Signing
6. Case Import 的 canonical CI root 固定為 `tests/subsystems/case_import`，不得機械改成 domain-style path。
7. PR #60 的 CI-only stacked branch 已關閉且未 merge；其 intended workflow 與 current main 使用相同 workflow blob，無需再吸收舊 stack ancestry。

## 3. Current canonical CI evidence

Task 97 正式續跑前可依下列已落地 evidence 判斷「前置 test architecture／canonical routing」完成，但不得把它外推為 Task 97 terminal acceptance：

- PR #58 restack：1 commit ahead / 0 behind；18 個 Contract Signing tests 為 pure rename，workflow 新增 Contract Signing 第 12 個 matrix entry。
- GitHub Actions run #230：`completed / success`，涵蓋 build、cross-domain workflow boundaries、12-owner canonical matrix。
- PR #59 restack：1 commit ahead / 0 behind；最終只保留 Anomalies 與 Scheduling 兩個仍適用的 relocation-safe migration，共 4 changed paths。
- GitHub Actions run #232：`completed / success`，涵蓋 build、cross-domain workflow boundaries、12-owner canonical matrix。
- current main `.github/workflows/python-app.yml` 已持有完整 12-owner matrix。

這些 CI 結果只證明 canonical owner test roots、build 與指定 cross-domain boundary set 在前置 baseline 上通過；不等於 Full Python、Full React、DB、Browser/runtime 或 Task 97 governance gates 已通過。

## 4. WP8 測試路由修訂

原 WP8 的 Module → Subsystem → Domain → Global → API → React → migration／DB／Browser → full suites → build/lint 順序保留。

在正式 full acceptance 前，新增一個 **Canonical owner preflight gate**：

```text
build
cross-domain workflow boundaries
12-owner canonical matrix
```

執行規則：

1. 每個 bounded Task 97 slice 完成且準備進 repository-wide/full acceptance 前，先確認上述 preflight 在 current HEAD 可重播。
2. 12-owner matrix 必須逐 owner `collect-only` 後再執行 pytest，維持 `fail-fast: false`。
3. preflight 失敗時先依 owner root 定位 relocation／contract regression，不直接用 full suite 噪音掩蓋 owner-local failure。
4. preflight 成功**不能取代** WP8 的 Full Python、Full React、DB gates、Browser/runtime 或 fresh-clone驗收。

## 5. 舊 checkpoint 有效性

原 Task 97 `13.4 Final-candidate current checkpoint` 中下列數字屬於 **pre-prep historical evidence**，不得再當作 post-prep current result：

- Full Python：`4804 passed / 150 skipped / 3 xfailed / 63 failed / 12 DB setup errors`
- React tests：`1200 passed / 35 failed`

原因：前置階段已修改 test layout、canonical collection、LINE relocation-sensitive tests，並修正 CI 暴露出的 stale test contracts／runtime defects；因此舊 full-suite failure denominator 與失敗集合可能已改變。

Task 97 下一次需要引用 Full Python／React 結論時，必須在當時 current HEAD 重新執行並記錄新的 exact result。舊數字只保留 provenance，不可拿來宣稱 current failed，也不可因 canonical CI 全綠反向宣稱 full suites 已 passed。

## 6. WP0 restart rule

正式續跑 Task 97 時：

1. 記錄 current branch／HEAD／worktree 狀態。
2. 先驗證本 amendment 所列已完成項是否有 drift；沒有 drift 的 package 只做 drift check，不重做 migration。
3. 以 current HEAD 重跑 WP0 inventory／writer／entry discovery；所有 candidate counts 仍是 `OBSERVED_VALUE`，不得沿用前置或舊 13.x 數字作 current denominator。
4. architecture/test path 變更只更新 identity/path evidence，不得因 test 被搬移就機械改變 production owner、transaction owner 或 entry disposition。
5. Contract Signing 現在已有 canonical owner/test root；後續 Task 97 的 Contract Signing API／writer／entry governance 應使用該 owner model，不再視為未建模 subsystem。

## 7. 已解決項與不得重開項

除非 current drift 或新的 human Authority 明確要求，以下只驗證 drift：

- Contract Signing owner/test architecture 建模與 18 個 owner-local test routing。
- 12-owner canonical CI matrix routing。
- LINE admin canonical test relocation／current route-response-model contract。
- Anomalies reclassification repository test relocation safety。
- Scheduling matching coordination repository test relocation safety。
- 既有 Test Map 已 closeout 的 owner-local flat test migration audit。

這些前置成果不會關閉 Task 97 仍存在的 production architecture／governance blocker。

## 8. 仍保留的 Task 97 required blockers

在新的 current-head scan 證明已消失前，原 `13.4` 的下列 blocker 類型仍視為 required work，而不是因前置 CI 全綠自動關閉：

- repository commit semantic dispositions 尚未全部完成。
- raw-dict／bounded typed API candidates 尚未全部收斂。
- writer `needs_decision` 尚未清零。
- entry terminal receipts 中的 blocked cases／external evidence 缺口尚未收斂。
- Media／Anomaly 所需 schema／release／durable-job cutover 等未完成項。
- production-script canonical absorption／operator guard／caller evidence 未完成項。
- Full Python／Full React 必須以 post-prep current HEAD 重跑。
- disposable MySQL DB gates 未取得 allowlisted `lu_test_*` environment／authority 前仍為 `BLOCKED`／`NOT_RUN`；不得操作 `union_db` 或 production。
- Browser/runtime 在 completion prerequisites 未滿足且無 deployment authority 時仍為 `not_run`。

## 9. Post-prep conclusion

```yaml
post_prep:
  task97_start_ready: true
  core_decisions_changed: false
  wp_structure_changed: false
  canonical_owner_preflight_added: true
  stale_full_suite_counts_must_rerun: true
  terminal_compliance_confirmed: false
```

Task 97 可以從 current-head WP0 drift scan／inventory 重建開始正式續跑；不得重做已無 drift 的 test migration，也不得把本次前置 CI 成功外推為 `ARCHITECTURE_COMPLIANCE_CONFIRMED`。
