---
doc_type: completion-receipt
declared_status: completed
date: 2026-08-13
owner: Scheduling Staff Matching Profile / Staff Availability / Orders / Case Import
release_identity: labor-union-wp72-2026-08-13-v1
---

# WP72 月嫂偏好與不可服務期間 Completion Receipt

## 完成範圍

- BeClass 明確飲食回答正規化為 Orders `requires_cooking`；缺失或矛盾資料 fail closed 進 review。
- Scheduling 擁有可改顯示名稱的 numeric matching preference definition、月嫂 profile、Preview／Apply、版本、receipt 與 audit event。
- `preferred_service_days` 與 `daily_service_hours` 成為 system definitions；既有可解析時段只產生數字偏好，無法解析者保留人工 review。
- 長假／暫停接案、恢復與取消使用同一 canonical Staff Availability aggregate；Matching 與 current Calendar 消費同一根事實。
- 配對中心顯示預設全勾的檔期、服務地區、希望服務天數、下廚需求、每日服務時數，以及啟用的自訂偏好。
- 服務人員行事曆已從 legacy monthly endpoint 改讀 typed `current-calendar`，並顯示「不可服務」。

## 可重播與資料庫證據

- 官方 validation schema manifest 已更新為 106 個 schema parts；generated full release 與 manifest verifier 通過。
- `scripts/bootstrap_disposable_mysql_schema.py` 對 `lu_test_wp72_official_reset` 完整建立 base、parts 20～188 與 999 view，postcheck 通過後即刪除一次性 DB。
- 修正既有 LINE part 179／186 replay ordering；未更名 historical release artifact。
- Case Import disposable MySQL E2E：`4 passed`；一次性 DB 已刪除。

## pytest 與 Browser UI

- WP72 focused regression：`92 passed`。
- full repository regression：第一次 `1892 passed, 87 skipped, 3 governance failures`；三項均為新增 entrypoint queue 與 validation receipt digest 派生資料未同步。
- 同步後 governance regression：`37 passed`；verification receipt validator `valid: true`，entrypoint review queue `review_required=0`。
- 最終 full repository regression：`1895 passed, 87 skipped`。
- bounded 案件摘要與訂單 deep link focused regression：`8 passed`；相關 UI module compile 通過。
- Browser 使用一次性 `lu_test_dataset_wp72_browser`：偏好 Preview／Apply、自訂「舒適服務天數」、五項預設全勾、候選恢復、長假建立、Calendar 8/13～8/20 顯示「不可服務」、取消後 8/13 恢復「可接案」均通過。
- Browser 不保存截圖或影片；一次性 DB、背景 API/UI process 與 Browser tab 均已移除。

## 收尾修正（2026-08-13）

- 後續 Browser 重測發現：使用者修改不可服務期間的操作、日期或原因後，舊 Preview 仍可能留在 session；若直接 Apply，後端會正確以 stale preview 拒絕，但原 Streamlit 畫面會顯示 traceback。
- 已修正管理端：Apply 僅在 Preview 與目前表單 intent 完全一致時啟用；Preview／Apply 失敗改為畫面錯誤訊息；成功後清除 session 中的 Preview。空白初始表單不再誤顯示輸入錯誤。
- 修正後 focused availability regression：`14 passed`；Browser 重新載入已確認空白初始畫面無誤報，並確認既有長假在服務人員月曆顯示為「不可服務／長假」。

## 收尾 UI 回歸（第二輪，2026-08-13）

- 使用一次性 `lu_test_dataset_availability_round2`，以隔離 fixture 建立一筆 2026-08-20～24 的洽談中案件、可完整承接的月嫂及其 matching profile；Browser 先確認五項預設篩選全開時候選人可選。
- Browser 在「長假／暫停接案」完成 Preview → Apply，建立同一服務期間的長假；資料庫僅作結果核對，確認 block 為 `effective`。配對中心隨即顯示「目前沒有月嫂能完整承接」，服務人員月曆 8/20～8/24 顯示「不可服務／長假」。
- Browser 亦驗證變更原因後的舊 Preview 不能套用：不產生 block，畫面要求重新產生 Preview；為處理 Streamlit 重跑前仍可點擊舊按鈕的短暫狀態，Apply handler 另加 server-side intent equality gate，絕不送出舊 intent。
- Browser 完成取消不可服務期間；資料庫核對 block 為 `cancelled`，配對候選恢復可選，月曆 8/20 恢復「可接案」。
- 此輪 focused availability regression：`14 passed`；未保存截圖或影片。
- Browser tab、API／Streamlit 背景程序與一次性資料庫均已移除。

## 明示不在本包範圍

- 未套用 production schema、未修改 production data、未部署 production。
- 未執行真人 LINE App／provider 驗收；這不影響 WP72 的 preference、availability、Matching 與 Calendar completion。
- 胎數如未來取得 canonical Orders 條款，只能是可取消的月嫂偏好，不能由自由文字推測或成為 hard eligibility。
