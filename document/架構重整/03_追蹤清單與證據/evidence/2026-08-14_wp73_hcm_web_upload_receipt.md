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

## Completion reconciliation

- 原 UI fixture 的兩列 review 證據仍有效；另以 `tests/test_case_import_disposable_mysql_e2e.py`
  補足成功建案與髒列 partial formal case：可解析 Client 欄位寫入、錯誤欄位 `NULL`、Order=`待補件`、
  service terms 為空且沒有帳務 bootstrap。
- `tests/test_hcm_import_api_disposable_mysql_e2e.py` 已穿過 authenticated multipart route 驗證 Apply、
  same-key replay、changed-payload conflict 與 HCM 歷史過渡覆蓋且不改訂單狀態。
- 本輪 focused：`54 passed, 3 xfailed in 4.64s`；disposable MySQL：`10 passed in 4.66s`。
- Query／Correct／Reject 與警示中心轉介依人工裁決移至 WP86／後續警示中心任務；不在 WP73 施工。
- 使用者已允許 Chrome 不可用時採內建瀏覽器，因此既有實際 API／Streamlit UI receipt 滿足本包 UI gate。
- WP73 第一階段 `completed`；Client／Staff Web cards 由 WP83 承接。

## Database gate

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | WP73 第一階段與最新 HCM partial-formal-case 人工裁決；警示中心處置排除 |
| Change inventory | PASS | 本包收尾無新增 DDL／seed／backfill；依賴已存在的 Case Import schema |
| Static release | PASS | 使用者已完成 canonical local update；partial formal case 所需 schema 已在 disposable DB 實跑 |
| Descriptor | PASS | Case Import current schema可建立Client／Order／receipt／warning roots；本包未新增owned object |
| Read-only plan | PASS | 先前 local update preview 明列 current import parts，之後使用者回報更新成功 |
| Engine verification | PASS | 10 個 disposable MySQL tests；髒列整列寫入、NULL、待補件、replay/conflict |
| Developer acceptance | PASS | 實際 API／Streamlit 內建瀏覽器 upload/replay/conflict receipt，且使用者採用該證據 |

總結：`DB_CHANGE_READY`。
