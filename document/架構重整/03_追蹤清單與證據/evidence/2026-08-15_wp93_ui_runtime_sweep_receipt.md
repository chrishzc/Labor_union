# WP93 UI Runtime Sweep Receipt

Date: 2026-08-15  
Scope: WP93 completion closeout; deidentified local database only.

## Result

The local API and Streamlit services were started against the current local schema release.
Chrome was unavailable in this environment, so the built-in browser was used. Each top-level
page remained open for at least five seconds without a new API or frontend error:

| Category | Page | Result |
|---|---|---|
| 營運作業 | 訂單管理、資料匯入中心、多月嫂排班、表單與履歷問卷管理、LINE 管理中心 | PASS |
| 帳務 | 帳務作業中心 | PASS |
| 異常與稽核 | 異常警示中心、資料庫原始資料瀏覽、系統狀態 | PASS |

## Defect found and repaired

The initial Orders page request returned `409 order_summary_projection_invalid`. The database
contained valid historical rows with no planned start and `service_days = 0`, plus formal
`待補件` rows with nullable planned terms. `subsystems/orders/summary_query.py` now presents
these as unknown read-model values, while the Orders lifecycle and financial eligibility remain
fail-closed. The summary service also no longer applies Python lexical ordering to MySQL cursor
results, because legacy non-ASCII case numbers are ordered by MySQL collation.

## Evidence

- `.venv\\Scripts\\python.exe -m pytest tests\\test_order_summary_query.py tests\\test_order_summary_api_client.py -q --basetemp .pytest_tmp\\wp93-ui-pending-summary-v3` — `14 passed`.
- Deidentified local summary query returned `{'status': 'ok', 'items': 134}`.
- `GET /api/v1/orders/summaries?page_size=200` returned `200` after the repair.
- Browser DOM snapshots for all pages contained the expected root heading and no error alert.

Browser console retained historical Streamlit WebSocket and Popper warnings from earlier page
navigation; neither corresponded to a page error or an API failure in this sweep.
