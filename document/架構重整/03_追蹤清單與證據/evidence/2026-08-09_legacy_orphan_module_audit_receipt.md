---
scope: Legacy orphan module audit
status: proven-current-source
verified_at: 2026-08-09
---

# Legacy orphan module audit receipt

## 漏掃原因與補正

先前 writer inventory 驗證的是 DML writer ownership，無法找出不寫資料、也不在 runtime import
chain 的 compatibility module。此次另以 production imports、FastAPI router mounting、Streamlit
callers、test-only callers 與 direct CLI entry points 交叉檢查。

## 本次退役

- `api/routes/payments.py`：只有 retired module docstring；未被 `api/main.py` import 或 mount。
- `api/schemas/payments.py`：只服務上列未掛載 route，沒有 caller。
- `ui/pages/order/tab3_finance.py` 的 `_render_legacy_mixed_payment_overview`：無 caller 的 private
  forwarding shim；正式 UI 直接使用 `_render_tab3_finance`。

## 保留但非 orphan 的 legacy 字樣

- `line/setup_rich_menus.py` 是可直接執行的 Rich Menu 發布 CLI；其 helper 雖沿用舊名稱，仍委派
  typed publication workflow，不以 Python import 數為零而移除。
- API 的 legacy routes 若仍掛載，會明確回 `410 Gone` 以保護舊客戶端；它們不是 orphan module。
- preserve-data migration、legacy rows/read models 與 canonical Finance Import diagnostic boundary
  是現行資料保全或 fail-closed 行為，不因字串含 `legacy` 而退役。

## Router mount audit

刪除未掛載 `api/routes/payments.py` 後，以 AST 比對 `api/routes/*.py` 與 `api/main.py` 的
`include_router()`，沒有剩餘 unmounted route module。仍帶 retired module header 的
`assignment_schedule_rest_dates.py` 與 `multi_caregiver_schedule.py` 均已掛載，且只提供
typed `410 Gone` migration boundary；前者有既有 leave-resolution test，後者以直接 route test
驗證，不可當作 orphan 刪除。

## Writer inventory clarification

writer inventory 的 669 是 AST 掃到的 write／dynamic-SQL／transaction-boundary finding，不是
669 個 module 或「待刪」項目。去重後是 660 個 identity；disposition 為 451 個
`retain_canonical` 與 209 個 `retain_restricted`，`migrate_then_remove` 及
`approved_to_remove` 都是 0。只有完成 caller migration、replacement evidence 與明確 retirement
決策的項目，才可另行刪除 Python module。

## Full production import-graph retirement

納入 API、Domain、Subsystem、Infrastructure、LINE、UI、Services 與 Scripts 的 static import graph，
並扣除 API／UI／CLI entry point 後，以下零 caller module 已移除：

- `infrastructure/migration/fingerprints.py`、`journal.py`、`verification.py`：現行
  preserve-data runner 使用 `maintenance`、`preflight`、`mysql_safety`、`cutover` 與
  `rehearsal_runtime`，三個舊 utility 沒有 runner、script、test 或 external entry caller。
- `subsystems/access/security_audit_repository.py`：舊 Data Browser direct audit writer；現行管理員
  audit 由 `subsystems/access/authentication_session.py` 與 typed security-audit query／retention
  workflow 擁有。
- `subsystems/scheduling/leave_resolution_preview.py`：沒有 API、UI、test caller；目前請假／代班
  Preview／Apply 由 `domains/scheduling/leave_substitution.py`、
  `subsystems/scheduling/leave_substitution_workflow.py` 與 `/api/v1/orders/*/leave-substitution/*`
  提供。
- `ui/api_clients/order_lifecycle_api_client.py`：兩個空 class 無 caller；實際日曆 UI 使用本地的
  typed `OrderLifecycleAdminApiClient` adapter。

為避免重複漏掃，`tests/test_production_module_caller_graph.py` 現會驗證所有非 entry production
module 至少有 production 或 test static caller，並驗證每個 `api/routes/*.py` 都由
`api/main.py` 掛載。明確 API／UI／CLI entry point 以有限 allowlist 排除；新檔若沒有 caller，
test 會 fail-closed，而非等待人工以關鍵字搜尋發現。
