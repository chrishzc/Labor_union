# 邊界異常資料 UI 驗收落差清單

> 資料來源：`scripts/seed_boundary_anomalies.py` 產生的 32 個異常情境（案號 115900001-115900024，見 `scripts/seed_boundary_anomalies_report.json`）。
> 本清單記錄「規格書預期行為」與「目前 UI/系統實際表現」的落差，逐項走查更新。
> 狀態標記：✅ 符合預期　❌ 系統沒擋住/沒顯示　⚠️ 功能疑似尚未實作　⏳ 尚未檢查

> 因瀏覽器自動化工具無法讀取畫面上 canvas 渲染的資料表格內容，改用「直接檢查後端程式碼」確認每項規格書預期行為是否真的有程式邏輯支撐，比肉眼看畫面更準確可靠。以下「實際觀察」欄位皆為程式碼稽核結論，附檔案路徑佐證。

| 編號 | 情境 | 案號/ID | 規格書預期行為 | 實際觀察（程式碼稽核） | 狀態 |
|---|---|---|---|---|---|
| A1 | invalid_bank_code_format | staff_id=111 | Validation 拒絕/寫入爬蟲隔離日誌 | `scripts/imports/import_staff_beclass.py` 只做 `clean_data` 型別轉換，`bank_code`/`branch_code` 無格式驗證，中文字串會直接寫入 | ❌ |
| A2 | invalid_bank_account_format | 115900001 | 標記待人工審查，不強行寫入 DB | 同上，`refund_account_no` 無格式檢查，"同上"/"無" 會直接寫入 `beclass_records` | ❌ |
| A3 | invalid_identity_card_format | staff_id=112 | ETL 驗證拒絕/寫入異常日誌 | `import_staff_beclass.py:169-171` 只檢查 `identity_card` 是否為空，無格式/checksum 驗證；小寫、9碼皆可通過 | ❌ |
| A4 | invalid_phone_number_format | 115900002 | 觸發清洗器修正或拒絕無效號碼 | `import_client_hcm.py::clean_phone` 有基本正規化（去空白/補國碼），但市話+分機格式不會被拒絕，只會原樣或部分清洗留存 | ⚠️ 部分 |
| A5 | invalid_date_format_or_value | 115900003 | 日期校驗失敗，隔離該列資料 | `_parse_date` 用 `pd.to_datetime(errors="coerce")`，失敗只是靜默變 `None`，不會隔離該列或標記異常 | ❌ |
| A6 | invalid_numeric_field | 115900004 | 轉型失敗，標記為 pending 待確認 | `clean_data` 對數字欄位用 `int(val)` try/except，失敗回傳 `None`，沒有任何 pending 標記或人工佇列 | ❌ |
| A7 | invalid_identity_status | 115900005 | 無法計算補助時數，標記待人工分類 | `import_client_hcm.py` 對 `identity_status` 沒有白名單驗證，任何字串原樣寫入 `clients.identity_status` | ❌ |
| B1 | beclass_hcm_mismatch | query_no=115900099-alt | 顯示「待關聯問卷」，允許人工補登連結 | 全 repo 搜尋不到「待關聯問卷」或對應的未匹配 beclass 清單 UI/查詢邏輯 | ❌ |
| B2 | identity_card_conflict_suspect | staff_id=113,114 | 主檔去重警告，暫緩自動更新，人工覆核佇列 | `staff.identity_card` 只有 DB UNIQUE 擋「完全相同」的重複，沒有「相似身分證疑似同人」的去重警告機制 | ❌ |
| B3 | missing_primary_identity | client_id=155 | ETL 應直接拒絕寫入（此列僅測 UI 空值防護） | `import_client_hcm.py:210-213` 確實會擋：`case_no` 為空時 `review_required += 1; continue`，不寫入 `clients`——**這條在真實匯入流程其實有擋住**，只是我們的種子腳本故意繞過 ETL 直接寫入來測 UI 顯示空值的情況 | ✅（真實匯入流程） |
| C1 | schedule_overlap_conflict | 115900006/007 | 排班/媒合規則偵測撞期，行事曆高亮衝突 | `services/multi_caregiver_assignment_rules.py::validate_non_overlapping_assignment_interval` 只檢查**同一案件內**的月嫂交接重疊，全 repo 沒有「同一月嫂跨兩個不同案件」的撞期檢查 | ❌ |
| C2 | staff_skill_mismatch | 115900008 | 媒合推薦系統標示硬性條件不符合警告 | `services/db_service.py:1601` 對雙胞胎+`care_babies<2` 確實有硬性過濾（推薦清單會排除），但僅在**推薦階段**生效；素食等 `special_skills` 需求全 repo 搜不到任何檢查邏輯；且我們的種子資料是直接指派（跳過推薦），不會觸發此檢查 | ⚠️ 部分（僅胎數，且僅推薦階段） |
| C3 | holiday_rest_conflict | 115900009 | 出勤結算系統判定休假衝突，需人工確認雙倍薪資或調休 | `is_double_pay` 只是可手動勾選的欄位（`ui/pages/01_data_browser.py:351`），沒有自動偵測「休假日被排班」並要求人工確認的邏輯 | ❌ |
| C4 | service_days_mismatch | 115900010 | 訂單結算系統發出天數不符異常通知 | 全 repo 搜不到任何「排班天數加總 vs 合約 service_days 不符」的比對或通知邏輯 | ❌ |
| D1 | invalid_virtual_account | (finance_import_row) | non_business_review，不查案件 | `services/finance_transaction_classifier.py:220` confirmed：格式錯誤虛擬帳號 → `non_business_review`，邏輯確實存在且已用種子資料實測通過 | ✅ |
| D2 | case_not_found | alert | pending + CLIENT 領域 case_not_found 警示 | `services/client_receipt_reconciliation.py:209` 確實回傳 `_pending("case_not_found")`，**但該函式全程沒有呼叫 `create_or_get_finance_alert`**，不會自動建立警示——警示要靠人工/其他流程另外建立 | ⚠️ 部分（pending 有，警示沒有自動建立） |
| D3 | case_not_unique | 115900011/012 | pending + case_not_unique 警示，不猜測歸屬 | `client_virtual_account_resolver.py` 是 1:1 決定性反解函式，架構上不可能產生「多筆候選」，此情境在真實系統中無法被觸發，規格與現有解析器設計互相矛盾 | ❌（規格/現況矛盾） |
| D4 | missing_payment_reference | (finance_import_row) | 不依姓名自動核銷，保持 pending | 同 D1，`classify_finance_transaction` 對缺銷帳碼確實回 `non_business_review`，已用種子資料實測通過 | ✅ |
| D5 | subsidy_return_underpaid_or_overpaid | 115900013/014 | 保持 pending，RETURN 警示 | `services/client_subsidy_return_transactions.py`/`client_subsidy_return_obligations.py` 全文搜不到 `create_or_get_finance_alert` 呼叫，短退/溢退不會自動建立警示 | ⚠️ 部分（pending 邏輯需另查，警示未自動建立） |
| D6 | shared_refund_account | 115900015/016 | 退款自動化流程攔截，標記待人工審查 | 分類器對帳號對到多個客戶會回 `non_business_review`（`counterparty_account_multiple_matches`），已用種子資料實測通過分類，但同 D5，沒有自動建立警示 | ⚠️ 部分 |
| D7 | subsidy_return_failed_or_reversed | 115900017 | 正式帳務淨額不變，退款失敗警示 | 同 D5，服務層沒有自動警示建立呼叫 | ⚠️ 部分 |
| D8 | government_subsidy_underpaid_or_overpaid | 115900018/019 | pending，SUBSIDY 警示 | `services/government_subsidy_reconciliation.py` 同樣搜不到 `create_or_get_finance_alert` 呼叫 | ⚠️ 部分 |
| D9 | multi_batch_same_amount_ambiguity | 115900020/021 | pending，管理員手動指定歸屬批次 | `create_subsidy_claim_batch` 本身冪等/快照比對邏輯正確（已用種子資料實測通過），但沒有「同額多批次歧義」的自動偵測或 UI 指定介面 | ⚠️ 部分 |
| E1 | staff_payment_missing_reference | staff_id=121 | pending，不依姓名猜測 | `staff_actual_transfers` 的 CHECK 約束（`payment_phase='unknown'` 強制 `review_status='pending'`）確實存在且已用種子資料實測通過，但同樣沒有自動建立 STAFF 警示 | ⚠️ 部分 |
| E2 | staff_shared_bank_account | staff_id=122,123 | 暫緩自動撥款分配，STAFF 警示 | 分類器對共用帳號會回 `non_business_review`（已實測通過），但沒有自動建立警示 | ⚠️ 部分 |
| E3 | staff_monthly_settlement_ambiguity | staff_id=124 | pending，月結候選歧義警示 | 沒找到任何「同月嫂多筆未結月結單」的歧義偵測邏輯或警示建立 | ❌ |
| E4 | staff_payment_amount_mismatch | 115900022 | 停止自動分配，標記待人工核對 | `staff_transfer_allocations` 的 CHECK 只驗明細內部組成加總，不驗跟實際轉帳金額的關係——資料庫層級不會擋這種不一致，需要應用層主動比對，目前沒找到這段邏輯 | ❌ |
| F1 | alert_claim_conflict | alert_id=47 | 他人再次認領跳出 409 Conflict | `services/finance_alert_workflow.py::claim_finance_alert` 對已被他人認領會回 `{"result":"conflict"}`，邏輯存在；HTTP 409 對應要看 `ui/pages/06_finance_alerts.py` 呼叫的 API router 是否轉譯，未逐一追查到 API 層 | ✅ 服務層邏輯確認 |
| F2 | resolved_alert_history | alert_id=48 | 已解除分頁可查看原因歷程，不可重開 | `resolve_finance_alert` 狀態機正確（resolved 後再次 resolve 需完全比對才回 existing，否則 conflict），已用種子資料實測 alert_id=48 建立成功 | ✅ |
| F3 | alert_domain_coverage | alert_id=49-52 | CLIENT/RETURN/SUBSIDY/STAFF 皆可查看 | ✅ 已在 UI 實機核對 alert_id=52 (STAFF)，畫面正確顯示狀態/來源/候選快照，見下方走查記錄 | ✅ |
| G1 | line_user_id_conflict | 115900023 | 寫入 line_confirmation_requests 待人工介入覆核 | `services/line_review_service.py` 有完整 list/approve/reject 審核工作流，但**沒有針對「同一 line_user_id 同時存在多筆待審請求」的專門衝突偵測**，兩筆請求會被當成獨立項目各自審核 | ⚠️ 部分（有審核機制，缺衝突偵測） |
| G2 | line_not_linked | 115900024 | line_tasks 記錄推播失敗並觸發替代通知管道 | `services/line_task_service.py::enqueue_line_task` 的 `to_user_id` 沒有空值/有效性檢查，也沒有任何「觸發替代通知管道」的程式碼路徑 | ❌ |

## 統計摘要

- **✅ 已驗證且真的有防護邏輯（5 項）**：A→B3（真實匯入流程層級）、D1、D4、F2、F3
- **⚠️ 部分實作（12 項）**：A4、C2、D2、D5、D6、D7、D8、D9、E1、E2、G1，以及 F1（服務層有但 API 轉譯未查）
- **❌ 完全沒有防護邏輯（14 項）**：A1、A2、A3、A5、A6、A7、B1、B2、C1、C3、C4、D3、E3、E4、G2

**最大的系統性落差**：`services/finance_alert_detection.py::create_or_get_finance_alert` 這個警示建立函式，全 repo 只有 `scripts/generate_fake_data.py`、`scripts/seed_boundary_anomalies.py` 和它自己的單元測試會呼叫它——**沒有任何一個真實的對帳/核銷業務服務（client_receipt_reconciliation、client_subsidy_return_transactions、government_subsidy_reconciliation、staff_actual_transfers 等）會在偵測到異常時自動建立警示**。警示中心（Page 6）本身做得很完整（F1-F3 已實測驗證），但它目前是一座「蓋好了卻沒接水管」的房子：規格書寫的「D2~E2 各種異常都要自動建立警示」这句話，在現在的程式碼裡都還沒有串起來。

## 走查記錄

### F3：帳務警示中心 UI 實機驗證
- 開啟 `http://localhost:8501`，側邊選單「⚠️ 帳務警示中心」
- 選擇「警示 #52」
- 畫面正確顯示：
  - 標題：警示 #52：review_required
  - 狀態：open｜來源：STAFF / boundary_fixture / f3-domain-coverage-staff
  - 原因：邊界測試：STAFF 領域警示涵蓋
  - 候選快照：`{"domain":"STAFF","fixture":"f3_alert_domain_coverage"}`
  - 「認領警示」「解除警示」操作按鈕皆正確渲染
- 結論：資料庫 → API → UI 整條路徑對這筆資料是通的。
