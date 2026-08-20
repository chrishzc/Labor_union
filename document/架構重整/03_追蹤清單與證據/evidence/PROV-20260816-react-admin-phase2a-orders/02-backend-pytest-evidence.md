# 證據紀錄：02-後端 Pytest 整合與合約回歸測試 (Backend Pytest Evidence)

> **SUPERSEDED / STALE EVIDENCE**：本檔保存早期稽核歷史，測試數、工具鏈與完成判斷不得再引用。
> Current authority: `evidence-summary.md` and `verification-receipt.md`（Phase 2A status remains `blocked`）。

**證據代碼 (Evidence ID)**: `PROV-20260816-PHASE2A-EVID-02-BE-PYTEST`  
**所屬工作包 (Work Package)**: `PROV-20260816-react-admin-phase2a-orders`  
**執行時間 (Timestamp)**: `2026-08-16T12:20:32+08:00`  
**執行者 (Actor)**: Worker G4 (Verification & Evidence Ledger Writer)  
**執行環境 (Environment)**:
- OS: Windows 11 (win32 10.0.26100)
- Python: 3.14.2
- Pytest: 9.1.1
- Plugins: `anyio` 4.14.1, `pluggy` 1.6.0
- Virtualenv: `D:\project\Labor_union\.venv`

---

## 1. 測試執行指令與摘要 (Execution Command & Summary)

### 1.1 核心指定測試套件 (Core Focused Suite)
```powershell
& "D:\project\Labor_union\.venv\Scripts\python.exe" -c "import os, sys, pytest; os.chdir('D:/project/Labor_union'); sys.exit(pytest.main(['tests/test_order_summary_query.py', 'tests/test_order_detail_query.py', 'tests/test_order_calendar_detail_query.py', 'tests/test_contract_completion_workflow.py', 'tests/test_assignment_plan_workflow.py', '--basetemp', '.pytest_tmp/phase2a-orders-focused', '-v']))"
```

**結果**:
- **Collected**: 34 items
- **Passed**: 34
- **Failed**: 0
- **Duration**: 1.27s
- **Exit Code**: `0`

---

### 1.2 擴展完整訂單回歸測試套件 (Comprehensive 11-File Orders Suite)
```powershell
& "D:\project\Labor_union\.venv\Scripts\python.exe" -c "import os, sys, pytest; os.chdir('D:/project/Labor_union'); sys.exit(pytest.main(['tests/test_order_summary_query.py', 'tests/test_order_detail_query.py', 'tests/test_order_calendar_detail_query.py', 'tests/test_contract_completion_workflow.py', 'tests/test_assignment_plan_workflow.py', 'tests/test_order_summary_api_client.py', 'tests/test_order_detail_ui_client_boundary.py', 'tests/test_order_calendar_detail_api_client.py', 'tests/test_order_cancellation_workflow.py', 'tests/test_order_auto_completion_workflow.py', 'tests/test_order_reopen_workflow.py', '--basetemp', '.pytest_tmp/phase2a-orders-focused', '-v']))"
```

**結果**:
- **Collected**: 55 items
- **Passed**: 55
- **Failed**: 0
- **Duration**: 2.94s
- **Exit Code**: `0`

---

## 2. 測試案例明細 (Granular Test Case Breakdown)

### 2.1 `tests/test_order_summary_query.py` (12 Tests - PASSED)
1. `test_query_returns_canonical_page_and_stable_etag`: 驗證訂單摘要分頁查詢回傳標準分頁物件並包含穩定之 ETag。
2. `test_query_passes_case_or_client_search_text_to_repository`: 驗證案號或客戶名稱關鍵字正確傳遞至 Repository 層進行比對。
3. `test_query_rejects_non_tuple_repository_page`: 驗證 Repository 回傳型別不符合 Tuple 時進行型別防禦拒絕。
4. `test_query_rejects_duplicate_case_numbers`: 驗證防範重複案號資料進入摘要投影。
5. `test_query_rejects_datetime_for_date_projection`: 驗證日期欄位不得混入含有時分秒之 datetime 物件，維持嚴格 `date` 型別。
6. `test_query_preserves_legacy_rows_with_unknown_identity_or_planned_end`: 驗證相容遺留資料庫中未標註身分或預計結束日為空之歷史訂單。
7. `test_query_preserves_pending_case_without_planned_terms`: 驗證待簽約或洽談中案件無條款時正常呈現。
8. `test_query_normalizes_legacy_zero_days_without_a_planned_start`: 驗證無開工日且服務天數為 0 之遺留資料正規化處理。
9. `test_query_rejects_zero_days_when_a_planned_start_exists`: 驗證已有預計開工日之案件服務天數不得為 0。
10. `test_request_rejects_invalid_page_size[0]`: 驗證拒絕分頁大小小於等於 0 之無效請求。
11. `test_request_rejects_invalid_page_size[201]`: 驗證拒絕分頁大小超過 200 上限之無效請求。
12. `test_request_rejects_blank_search_text`: 驗證拒絕全空白之搜尋字串。

### 2.2 `tests/test_order_detail_query.py` (6 Tests - PASSED)
1. `test_query_returns_only_declared_complete_detail_fields`: 驗證詳情查詢僅回傳明確宣告之完整欄位投影。
2. `test_query_rejects_undeclared_repository_field`: 驗證拒絕 Repository 中未在綱要宣告之未知欄位洩漏。
3. `test_query_rejects_noncanonical_date_type`: 驗證嚴格型別防禦拒絕非標準日期型別。
4. `test_query_reports_missing_selected_case`: 驗證查詢不存在之案號時正確拋出 404 Not Found。
5. `test_query_preserves_legacy_order_with_unknown_identity_status`: 驗證遺留案件之身分狀態相容性。
6. `test_query_rejects_blank_case_number_before_repository_call`: 驗證在呼叫 Repository 前即時攔截並拒絕空白案號。

### 2.3 `tests/test_order_calendar_detail_query.py` (8 Tests - PASSED)
1. `test_query_returns_validated_calendar_detail`: 驗證成功回傳校驗完整之日曆詳情物件。
2. `test_query_rejects_noncanonical_case_number[]`: 驗證拒絕空字串案號。
3. `test_query_rejects_noncanonical_case_number[ CASE-1]`: 驗證拒絕前置空白之案號。
4. `test_query_rejects_noncanonical_case_number[CASE-1 ]`: 驗證拒絕後置空白之案號。
5. `test_query_rejects_noncanonical_case_number[xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx]`: 驗證拒絕超過長度限制之案號。
6. `test_query_rejects_projection_identity_drift`: 驗證嚴格防範投影案號與請求案號不一致之漂移。
7. `test_query_rejects_unexpected_service_mode`: 驗證拒絕未定義之服務模式枚舉。
8. `test_query_maps_missing_projection_to_not_found`: 驗證無日曆投影時對應至 404 Not Found。

### 2.4 `tests/test_contract_completion_workflow.py` (5 Tests - PASSED)
1. `test_preview_apply_persists_canonical_contract_completion_chain`: 驗證預覽與套用履約結案鏈路符合標準生命週期。
2. `test_apply_replays_matching_receipt_without_new_writes`: 驗證重複套用相同結案單據時執行冪等回放，不產生二次寫入。
3. `test_query_reports_official_service_dates_blocker`: 驗證未確認正式服務日程前阻擋結案。
4. `test_apply_rejects_stale_client_finance_version`: 驗證防範客戶財務版本過期之樂觀鎖衝突。
5. `test_contract_completion_carries_the_one_precontract_deposit_obligation`: 驗證結案計算中正確承載並扣抵簽約前已收之訂金款項。

### 2.5 `tests/test_assignment_plan_workflow.py` (3 Tests - PASSED)
1. `test_assignment_plan_workflow_is_readable_source_without_bytecode_bridge`: 驗證工作流原始碼為純 Python 實作，無二進位/字節碼黑箱橋接。
2. `test_preview_combines_domain_and_downstream_fingerprints`: 驗證預覽計算精確結合領域與下游狀態指紋。
3. `test_apply_returns_matching_idempotent_receipt_without_repersisting`: 驗證排班指派之冪等寫入收據。

### 2.6 擴展訂單 API 與工作流 (21 Tests - PASSED)
- `tests/test_order_summary_api_client.py` (2 tests): 驗證 API Client 支援強型別分頁且無泛型 Envelope 污染。
- `tests/test_order_detail_ui_client_boundary.py` (5 tests): 驗證 UI Client 邊界嚴格回傳 Typed View、未選案號不發出請求。
- `tests/test_order_calendar_detail_api_client.py` (1 test): 驗證日曆詳情端點路由標準化。
- `tests/test_order_cancellation_workflow.py` (2 tests): 驗證訂單取消跨領域鏈路與冪等收據。
- `tests/test_order_auto_completion_workflow.py` (10 tests): 驗證自動結案之時區標準化、指紋比對、衝突處理與 Not Found 映射。
- `tests/test_order_reopen_workflow.py` (1 test): 驗證訂單重啟交易合約。

---

## 3. 後端零異動合約驗證 (Backend Zero-Drift Verification)

依據 Phase 2A 核心規範 (Invariant 5: Zero Backend/DB Modification)，前端真資料串接完全基於現有 FastAPI 端點，後端代碼無任何侵入性修改：
- 後端綱要未做任何變更或擴充。
- 資料庫 Migration 未產生任何額外腳本。
- 後端測試 100% 綠燈，證明前端遷移完全遵守既有後端架構與領域合約。
