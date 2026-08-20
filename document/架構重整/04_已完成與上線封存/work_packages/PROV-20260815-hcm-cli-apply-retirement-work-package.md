---
doc_type: work-package
declared_status: completed
date: 2026-08-15
owner: Case Import / Global Entry Governance
domain: Case Import
subsystem: HCM legacy CLI apply retirement
implementation_authorization: granted-by-user-2026-08-15
---

# HCM Legacy CLI Apply 退役工作包

## Scope

移除 `scripts/imports/import_client_hcm.py` 的直接執行入口，使其不能再作為 CLI 讀取 workbook、database
target 或寫入 root。該模組暫時仍提供 HCM typed Web coordinator 所依賴的 shared normalization／row-intake
adapter。

不刪除 shared adapter、不改 Web API、HCM Domain root、WP95 resubmission、schema 或 direct SQL helper 的
內部清理；後者必須先完成 adapter extraction，另立 Work Package。

## Acceptance

1. module 不再有 CLI entrypoint，且不讀 DB target 或 workbook。
2. authenticated HCM Web Preview／Apply 的 shared adapter import 保持可用。
3. entrypoint focused regression、HCM safety／router regression 與 `git diff --check` 通過。

## 完成證據

2026-08-15 已移除 `__main__` CLI entrypoint 與 current queue 項目；shared adapter 仍由 typed Web
coordinator 使用。驗收收據：
`../03_追蹤清單與證據/evidence/hcm_cli_apply_retirement_receipt_20260815.md`。
