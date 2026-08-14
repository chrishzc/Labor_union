---
doc_type: evidence-receipt
declared_status: completed
date: 2026-08-14
owner: Case Import / Orders / Finance Import / Global Management UI
work_package: WP83
---

# WP83 資料匯入中心完成收據

## 結論

資料匯入中心的 HCM、Client BeClass、Staff BeClass、歷史訂單與 Finance 五個 lane 已完成。
各 lane 只經 typed API／application service 執行 Preview／Apply；髒列有明示 review outcome，合法列
不被同檔髒列阻擋。警示中心 UI、Correct／Reject 與轉介功能不在本次完成範圍。

## 業務情境與去敏來源證據

| lane | 去敏來源／證據 | 結果 |
|---|---|---|
| HCM current／歷史過渡 | `document/資料庫、資料處理/1,HCM.xlsx`；WP73 receipt | 正式案件 partial row、invalid field 留空、review、replay、conflict 均通過。 |
| Client BeClass 過渡 | `document/資料庫、資料處理/3.client_beclass.xlsx` | 內建瀏覽器實際 upload；Preview 1 列、`review_required=1`；隔離 MySQL Apply 後 replay 明示 `replayed_workbook=true`。 |
| Staff BeClass 歷史 | `document/資料庫、資料處理/2.staff.xlsx`；WP77 receipt | 髒列建立 review；較新快照可更新姓名與整組集合；舊來源 replay 不回復較舊值。 |
| 歷史訂單 | `document/資料庫、資料處理/假資料_歷史訂單.xlsx`；WP85 receipt | 既有案件補歷史值、replay／conflict／rollback 與 review 投影通過。 |
| Finance | `台新範例對帳單.xlsx`、`永豐範例對帳單.xlsx`、`歷史對帳單.xlsx` | 三種 parser contract、root fact 寫入、不可分類列阻擋帳務 posting、UI/API Preview parity 通過。 |

所有輸出只保存去敏檔名、digest、筆數與 outcome；未保存原始列內容或個資。

## 驗證結果

| 層級 | 命令／操作 | 結果 |
|---|---|---|
| Focused contracts | `pytest`：資料匯入頁、五 lane API clients／routers／workbook services、三種 Finance parsers | `73 passed` |
| Disposable MySQL | HCM multipart API、Client binding/workbook、Staff adoption、歷史訂單 workbook | `13 passed` |
| Finance root fact | 真實形狀台新 workbook → canonical root fact／unresolved reprocess block | `1 passed` |
| Finance UI parity | Streamlit client Preview 與 owning typed Preview 同結果 | `1 passed` |
| Browser | 內建瀏覽器 `http://127.0.0.1:8502`，進入資料匯入中心、展開五類卡、上傳 Client 去敏 workbook、執行 Preview | PASS；UI 顯示 `source_row_count=1`、`review_required_count=1` |
| Read-only DB plan | `.venv\\Scripts\\python.exe -m scripts.update_local_database` | PASS；release `labor-union-wp88-2026-08-14-v4`，parts 61～194 全部 exact |

## DB change gate

WP83 本身沒有新增 schema；本表確認其依賴的 canonical release 可用。

| gate | 狀態 | 證據 |
|---|---|---|
| Scope gate | PASS | WP83 approved write set；本輪未擴張警示中心。 |
| Change inventory | PASS | WP83 schema-only／seed／backfill／destructive 皆為 none；依賴 WP77／80／88 additive releases。 |
| Static release gate | PASS | canonical plan 解析 WP88 v4 並列出 189～194。 |
| Descriptor gate | PASS | WP77、WP80、WP88 descriptor focused tests與 completion receipts。 |
| Read-only plan gate | PASS | 2026-08-14 plan：無 apply／resume，全部 exact。 |
| Engine verification gate | PASS | WP77 pre-189、WP80 pre-190 preserve candidates及 WP88 local candidate evidence。 |
| Developer acceptance gate | PASS | 開發者實跑 `update_local_database.bat` 成功，後續 read-only plan仍為 exact。 |

總結：`PASS`。本包沒有未完成的 DB change。

## 保留的 successor

- Client／Staff temporary card 只在 LIFF end-to-end 驗收前保留；removal trigger 測試仍有效。
- 警示顯示、後續處理、Correct／Reject 與轉介 command 由 WP86／WP88 接續，不屬於本收據。
