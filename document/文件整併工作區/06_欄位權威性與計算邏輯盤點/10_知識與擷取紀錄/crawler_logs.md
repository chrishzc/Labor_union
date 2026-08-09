# `crawler_logs` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`10_知識與擷取紀錄`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 表級裁決：整張表長期考慮移除。未來若確實建立 BeClass／HCM 等自動匯入監控，應依實際 Pipeline 重新設計具批次身分、來源與明細關聯的專用日誌。
- 第二遍（衍生判定）：已完成（依表級移除方向）
- 根事實展開：已完成（依表級移除方向）
- 規格反查：已完成（依表級移除方向）

- Schema：`db/schema.sql`
- live writer／reader：未找到 production caller。
- 現況資料：最近的保留資料升級證據顯示本表為空表。
- 舊規格定位：Data Pipeline 每次成功或失敗均寫入執行日誌，供 Streamlit 稽核與除錯。
- 規格漂移：舊規格另列 `records_quarantined`、`error_message`，但 live Schema 沒有這兩欄；live Schema 使用單一 `message`。舊規格描述的背景監控、手動掃描與 Streamlit 日誌頁面亦未形成 production caller。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `INT AUTO_INCREMENT PRIMARY KEY` | 預定作單次 crawler／pipeline run 日誌主鍵。 | 系統鍵／隨表長期考慮移除 | 不計算。 | DB 自增。 | 一次實際 pipeline run。 | 隨整張未使用的通用日誌表長期考慮移除。 | DB（現況） | 新增 run log | 不變 | 目前沒有 writer，沒有實際 run event 可對應。 | 已確認：隨表長期考慮移除 |
| `crawled_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | 預定記錄 pipeline 日誌寫入時間。 | 技術時間／隨表長期考慮移除 | DB `CURRENT_TIMESTAMP`。 | DB clock。 | 一次實際 pipeline run 完成或失敗的時點。 | 隨表長期考慮移除；未來專用日誌需明確定義 run 時點與 UTC 契約。 | DB／未存在的 Pipeline owner | 新增 run log | 不變 | 沒有 writer；欄名像「爬取時間」，舊規格則稱檔案處理與載入時間，事件時點不明確。 | 已確認：隨表長期考慮移除 |
| `status` | `VARCHAR(50) NOT NULL` | 預定保存執行結果，Schema 註解舉例 `SUCCESS/FAILED`。 | run 結果事實／隨表長期考慮移除 | 無 live 公式或受控值驗證。 | 未存在的 Pipeline 執行結果。 | 一次 run 是否完成。 | 隨表長期考慮移除；未來由實際 Pipeline owner 定義受控狀態。 | 未存在的 Pipeline owner | run 結束或失敗 | 不變 | 沒有 writer、CHECK／enum 或狀態契約。 | 已確認：隨表長期考慮移除 |
| `records_inserted` | `INT DEFAULT 0` | 預定保存本次新增資料列數。 | run 結果計數／隨表長期考慮移除 | 預期為本次成功 INSERT 的列數；live 無計算實作。 | 未存在的 Pipeline 執行結果。 | 本次各資料寫入操作的成功 INSERT。 | 隨表長期考慮移除；未來專用日誌由實際批次明細彙總。 | 未存在的 Pipeline owner | run 結束 | 不變 | 未定義跨表、重試、回滾與部分失敗時如何計數。 | 已確認：隨表長期考慮移除 |
| `records_updated` | `INT DEFAULT 0` | 預定保存本次更新資料列數。 | run 結果計數／隨表長期考慮移除 | 預期為本次成功 UPDATE 的列數；live 無計算實作。 | 未存在的 Pipeline 執行結果。 | 本次各資料寫入操作的成功 UPDATE。 | 隨表長期考慮移除；未來專用日誌由實際批次明細彙總。 | 未存在的 Pipeline owner | run 結束 | 不變 | 未定義資料值未變、upsert、重試、回滾與部分失敗時如何計數。 | 已確認：隨表長期考慮移除 |
| `message` | `TEXT NULL` | Schema 註解稱日誌詳細說明或錯誤原因。 | 非結構化結果摘要／隨表長期考慮移除 | 無公式。 | 未存在的 Pipeline 執行結果／exception。 | run 的人工可讀摘要或錯誤。 | 隨表長期考慮移除；未來專用日誌須區分結構化錯誤與人工可讀摘要。 | 未存在的 Pipeline owner | run 結束或失敗 | 不變 | 舊規格使用 `error_message` 並要求 traceback；live 欄位同時混合成功訊息與錯誤原因，且沒有大小與敏感資訊限制。 | 已確認：隨表長期考慮移除 |
