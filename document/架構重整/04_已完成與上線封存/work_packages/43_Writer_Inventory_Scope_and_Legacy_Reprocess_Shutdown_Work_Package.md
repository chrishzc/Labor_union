---
doc_type: work-package
declared_status: completed
authorized_by: user
authorization_date: 2026-08-08
completed_at: 2026-08-11
evidence: document/架構重整/03_追蹤清單與證據/evidence/2026-08-11_active_package_closeout_receipt.md
---

# Writer Inventory Scope 與 Legacy Reprocess Shutdown Work Package

## 範圍

本 work package 只處理三件事：

1. Writer Inventory v3 的 scan roots 必須包含 `services/`，不得小於 v1 的 production
   掃描邊界；
2. disposition validator 必須要求每個 unique candidate identity 都有 disposition，缺少
   identity 時 fail closed；
3. legacy Finance Import reprocess 的 CLI 與 service `--apply` 必須在取得資料庫連線前
   拒絕，正式帳務只可走既有 typed Preview／Apply。

## 非範圍

- 不自動將任何 existing writer 標為 `gone`、不移除 production code、不中斷 dry-run
  diagnostics；
- 不新增 schema、資料遷移、銀行付款指令或外部整合；
- 不把尚未人工審查的 identity 偽裝成 `retain_canonical`。

## 驗收

- candidate manifest 列出 `services` 與 unique identity count；
- 未完整 disposition 時 validator 回傳明確的 missing identity count；
- legacy `--apply` 不建立資料庫連線，且舊 integration test 不再主張 retired writer 的
  commit 行為；
- 所有變更使用 focused pytest 驗證，inventory 維持 `blocked` 直到逐筆 disposition 完成。

## 完成確認

2026-08-11 fresh validator 完整覆蓋 660 筆 reviewed disposition，`approved_to_remove=0`；
legacy reprocess Apply 仍在取得資料庫連線前 fail closed，focused tests 通過。此完成狀態不新增
任何 writer removal authority。
