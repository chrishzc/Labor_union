# ADR-001: import 腳本與告警中心架構重整記錄

## 狀態
Proposed

## 日期
2026-08-05

## 脈絡 (Context)
匯入功能在最近一次重構後出現行為斷裂，主要表現為：
1. 有些腳本仍引用舊有 `services.db_service` 模組，啟動或執行時找不到來源模組。
2. 匯入異常無法穩定落地到可視的告警中心，尤其是某些 finance / beclass 異常只留在流程內部摘要。
3. 欄位驗證採列級阻擋：任一欄位錯誤會讓整列不寫入。
4. 腳本統計（如 `48/43/5`）與 UI 呈現（31）數量常不一致，且無法一眼對帳。
5. 異常原因缺乏持久化/可追溯欄位，使用者難以定位失敗欄位。
6. 略過原因未可查，僅靠控制台輸出無法支援正式稽核。

## 目標
- 將 import 系統重整為一致的架構邊界：Script → Service → Subsystem → Infrastructure/API → UI。
- 以欄位級阻擋（column-level upsert）替代列級阻擋，正常欄位可成功寫入。
- 建立可對帳的匯入可觀測性：每列結果、每個欄位狀態、每筆告警原因可追蹤。

## 決策 (Decision)
採用「兩階段匯入 + 告警投影」重構策略：
1. 在匯入應用層做欄位驗證與可寫欄位拆分，輸出 `field_result`。
2. 寫入步驟改為 `partial write`：僅阻擋失敗欄位，成功欄位正常更新。
3. 匯入結果全部轉為結構化事件，透過統一的告警投影寫入 `system_alerts`。
4. 以一致的錯誤語彙（error_code、field_name、reason、row_id、sample）建立 `finance_alert_center` 與 `beclass_review` 的橋接。
5. 建立「匯入對帳文件」與「匯入明細頁」作為正式回報入口，補齊前後台行數差異釋義。

## 現況斷層 (Gap)
- `services/finance_import_application.py` 及多個 import/API 檔仍存在舊 import 路徑風險（`services.db_service`）。
- `system_alert_projection` 的去重邏輯使用 `(case_key, alert_code)`，與腳本逐列輸出口徑不一致。
- beclass / finance 兩條告警路徑在代碼上仍混用舊新 schema，缺少 single source of truth。
- 現有失敗紀錄停留在列級摘要，缺乏欄位級原因與樣本欄位值。
- 現行腳本無法明確產生「略過原因」的可持久欄位與前端可檢索欄位。

## 架構現況與問題對應
### 1) 腳本層
- 輸入：`scripts/imports/*`  
- 問題：列級驗證與列級跳過，缺少欄位級結果集合。  
- 改造：維持輸入/列標識，輸出列級結果包成 `field_results` 與 `row_summary`。

### 2) 應用服務層
- 檔位：`services/finance_import_application.py`、`services/finance_import_dispatch.py`  
- 問題：依賴舊 services 模組入口，跨層例外處理未統一。  
- 改造：統一 DB/Adapter 入口，導入型別化錯誤（validation/write/conflict/skipped）。

### 3) 通知/異常子系統
- 檔位：`subsystems/anomalies/*`、`subsystems/finance_import/*`  
- 問題：異常 event 與 UI alert 清單的映射未一致。  
- 改造：定義單一 `ImportAlert` payload，含欄位層級原因與處理建議。

### 4) UI 呈現層
- 檔位：`ui/pages/06_finance_alerts.py`  
- 問題：僅顯示聚合後警示，難以直接還原逐列偏差。  
- 改造：新增對帳欄位 `import_job_key`、`row_no`、`skip_reason_code`、`error_code`、`field_name`，並保留展開明細。

## 重構方案（先後順序）
1. **Critical-1**：修正 import 重構遺漏的 module 路徑與 DB adapter 入口。
2. **Critical-2**：建立欄位級錯誤模型（`ImportFieldIssue`）與 `skip_reason` 模型。
3. **High-1**：改造 beclass staff/client 匯入為 `partial write`。
4. **High-2**：統一 finance alert projection/consumer 的錯誤代碼與輸出 schema。
5. **Medium-1**：新增「匯入對帳儀表」頁面（輸入列數、已入列數、skipped、review、alert 明細）。
6. **Medium-2**：補齊 migration / 驗收腳本，鎖定回歸場景（如 staff beclass 48/43/5）。

## 驗收標準
1. 啟動任一 import 腳本，不再因舊 `services` 路徑失敗。
2. 任一列只要欄位錯誤，該欄位 blocked，其餘欄位可正常寫入。
3. 所有 import 異常皆可在告警中心查得：
   - 顯示 `error_code`、`field_name`、`reason`、`row_no`、`sample_value`。
4. 跑同一批實測資料時，輸出需滿足：
   - `total_input = db_written + skipped + reviewed + ignored`
   - 並可在系統中追溯每筆 skipped/reviewed 的原因。
5. UI 呈現不得再出現「行數少很多但原因不明」；需提供對帳說明與篩選。

## 後續改善（優先排程）
- P0：移除剩餘舊 import service 參考，鎖定重構邊界。
- P1：建立欄位級錯誤規則字典與文檔化代碼位址（error_code 目錄）。
- P1：定義告警 `codebook`，前端白名單欄位只保留可穩定展示欄位。
- P2：補齊自動化回歸場景（含真實資料偏差案例），保證 6 項問題不再復發。
- P2：整理導入文件更新流程，讓 future 任務必先補齊 `invariant -> route -> projection -> alert UI -> audit` 五段鍊路。

## 風險
- 切欄位級寫入時需避免大量 SQL partial update 造成效能回退；須配合批次與欄位白名單。
- 告警去重規則變更可能導致歷史告警量增長，需規劃清理與查詢效能優化。
- 架構調整會產生一次性的回溯資料不一致，需要一次性稽核腳本進行 reconcile。
