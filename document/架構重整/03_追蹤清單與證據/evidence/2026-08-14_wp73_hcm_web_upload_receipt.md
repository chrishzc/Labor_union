# WP73 HCM Web Upload 實機驗收收據（2026-08-14）

範圍：去敏 synthetic `.xlsx`，工作表名稱刻意不含 HCM 關鍵字；未使用真實來源檔、未寫入 production DB。

## 已驗證

- 已啟動本機 API（`127.0.0.1:8000`）與 Streamlit（`127.0.0.1:8501`）。
- 由「📥 資料匯入中心」選取 `hcm_ui_valid_invalid.xlsx` 後點選「上傳並處理 HCM」。
- UI 收到 strict typed receipt：digest `3adb3f...43223`、`source_row_count=2`、`review_required_count=2`、其他 terminal count 為 `0`。
- 同檔由 UI 再送一次得到 `replayed_workbook=true`，未重新逐列寫入。
- API 以相同 idempotency key 送入另一份仍可解析的 workbook，回傳 `409`／`hcm_workbook_idempotency_conflict`。
- 開發模式 UI 的受控 command key 驗收欄位，以原檔 key 上傳另一份可解析 workbook，實際顯示 `上傳未完成：hcm_workbook_idempotency_conflict`。
- route unit test 同時驗證 terminal success 與 conflict 都刪除 server temporary workbook。
- 受控開發 DB 直接核對 `case_import_hcm_review_rows=2`、`case_import_hcm_review_outbox` 未發布筆數為 `0`；review 已以 Case Import 自有 root/outbox 持久化，而非只回傳畫面 count。

## 命令與結果

```text
.venv\Scripts\python.exe -m pytest -W error tests\test_hcm_import_router.py tests\test_hcm_workbook_import.py tests\test_hcm_import_api_client.py tests\test_hcm_import_safety_gate.py tests\test_import_entry_split.py tests\test_finance_import_cli_test_adapter.py --basetemp .pytest_tmp\wp73-final-focused -q
24 passed in 2.08s
```

## 未完成／不宣稱完成

- 本次 fixture 的兩列皆依既有 Case Import 規則落在 HCM review；其中原本設計為合法的一列因測試 DB 尚未完成 Case Import bootstrap 而得到 `case_import_bootstrap_blocked`，沒有把它偽稱為成功建立 Client／Order 的證據。
- HCM review 的 Query／Correct／Reject 管理端 API 不是本包已實作範圍；目前由既有異常投影承接。
- Chrome extension 在此執行環境不可用，因此使用已啟動的內嵌瀏覽器完成 UI 操作；Chrome 專項復驗仍待具備 extension 的環境執行。
- WP73 維持 `in-progress`，不可封存；Client／Staff Web cards 由 WP83 承接。
