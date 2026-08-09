# `system_alerts` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`07_財務匯入與警示`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema.sql`、`db/schema_parts/107_system_alert_current_projection.sql`
- Service：`services/system_alert_service.py`、`services/anomaly_alert_detection.py`
- API／UI：`api/routes/system_alerts.py`、`api/schemas/finance_alert_center.py`、`ui/pages/06_finance_alerts.py`
- 父表關係：無實體 FK；以 `alert_code + case_key` 表示被提醒的異常實例。
- 子表關係：無；本表刻意採可覆寫的目前狀態投影，不保存不可變事件歷程。
- 已確認跨表裁決：本表只處理非財務類的「流程提醒」。涉及金額與核銷的稽核警示仍由 `finance_alerts`／`finance_alert_events` 負責。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `INT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 警示列建立事實。 | 保留作 API 與人工操作定位鍵。 | DB／System Alert Service | 建立警示 | 不變 | 無。 | 已確認：SSOT 鍵 |
| `alert_code` | `VARCHAR(50) NOT NULL` | 偵測規則代碼；與 `case_key` 共同唯一識別一個目前異常實例。 | 規則識別事實 | 由各 detector 使用固定代碼寫入。 | `anomaly_alert_detection` 與其他 current-state projector。 | 哪一條業務異常規則被觸發。 | 必須是受控規則代碼；不可作人工自由文字。 | 各 detector／System Alert Service | 規則偵測到異常 | 同一規則版本內固定 | 未集中註冊時，拼字錯誤會形成另一種警示。 | 已確認：保留異常代碼 |
| `source_domain` | `VARCHAR(50) NOT NULL` | 供 API 篩選與畫面分類的警示來源領域。 | 衍生分類投影／長期考慮移除 | `source_domain = domain_of(alert_code)`；例如 `SCHEDULE-001 → SCHEDULE`。 | 受控 `alert_code` 規則定義。 | 觸發警示的 `alert_code`。 | 不具獨立權威性，長期考慮移除並於讀取時由 `alert_code` 推導；過渡期由後端固定映射產生，不允許 caller 自行輸入。 | System Alert Service（過渡期） | `alert_code` 建立 | 隨 `alert_code` 固定 | 現況由 detector 同時輸入兩欄，可能出現 `SCHEDULE-001 + ORDER` 等矛盾組合。 | 已確認：衍生分類，長期考慮移除 |
| `case_key` | `VARCHAR(100) NOT NULL` | 在單一 `alert_code` 命名空間內識別異常實例；不一定是訂單案號。 | 異常實例識別事實 | 由 detector 依規則組成；現況包含 case_no、`case_no#assign{id}`、LINE user id、`staff_id:date`、assignment id 等。 | 各 detector。 | 哪一個業務對象或對象組合目前觸發該規則。 | 保留為受 `alert_code` 規則約束的字串鍵，必須與 `alert_code` 合併解讀；不得單獨當成 order FK 或 case_no，也不為每種警示增設多型關聯欄位。 | 各 detector／System Alert Service | 建立或重新掃描 | 同一異常實例固定 | 舊文件稱「關聯案號」，但 production 實際為多型字串鍵；誤當案號會連到錯誤資料。 | 已確認：保留為 alert_code 範圍內的異常實例鍵 |
| `reason` | `VARCHAR(500) NOT NULL` | 警示清單顯示的人類可讀目前原因。 | 衍生顯示投影／長期考慮移除 | `render_reason(alert_code, details)`；現況由 detector 依目前異常資料組字，重掃時覆寫。 | `alert_code`、`details` 與顯示模板。 | 當下異常的結構化資料及其規則代碼。 | 不具獨立權威性，長期改由 `alert_code + details` 即時計算；過渡期可儲存供列表顯示，但不得作警示類型、狀態或其他程式判斷來源。 | System Alert Service／Presenter（過渡期） | 建立、異常內容或顯示模板變更 | 無業務凍結 | 模板修改後既有列仍保留舊文案，直到再次掃描；若下游解析文字會產生邏輯漂移。 | 已確認：衍生顯示投影，長期考慮移除 |
| `details` | `JSON NOT NULL` | 最近一次掃描所得的結構化異常詳情；API 將其轉為詳情畫面。 | 可覆寫目前狀態投影（不具獨立業務權威性） | detector 從訂單、指派、排班等原始業務表產生；Service 限制大小、深度、項目數並阻擋敏感欄位。 | 各 detector 對原始業務表的查詢結果。 | 對應訂單、指派、排班等原始表欄位。 | 保留作 Alert Center 解耦用的最新結構化投影；只有 detector 可覆寫。計算與業務狀態機必須讀原始業務表，不得反向以 `details` 為來源。 | 各 detector／System Alert Service | 建立或原始異常內容變更後重新掃描 | 無業務凍結，復發可覆寫 | 無固定 per-code schema，caller 與 UI 可能對欄位理解不同；若被當成業務來源會造成反向依賴。 | 已確認：保留目前狀態投影，不具獨立權威性 |
| `status` | `ENUM('open','claimed','resolved') NOT NULL DEFAULT 'open'` | 流程提醒的目前處理狀態：open 尚未承接、claimed 已有人承接、resolved 異常已解除。 | 狀態機權威欄位 | 新增／復發為 open；人工認領為 claimed；人工處理或 detector 確認異常消失時為 resolved。原始異常消失時，open 與 claimed 都必須轉為 resolved。 | System Alert Service 對原始異常偵測結果及人工命令的判定。 | 原始業務資料是否仍符合異常規則，以及是否已有承接人。 | 狀態轉換必須由 claim／resolve／重新掃描命令執行；自動解除 claimed 時保留既有 `claimed_by`、`claimed_at`。 | System Alert Service | 建立、認領、解除、復發 | 可轉換；非財務稽核軌跡 | 現況不同自動解除 helper 對 claimed row 的處理不一致，可能使已不存在的異常停留在 claimed。 | 已確認：異常消失時 open／claimed 均自動解除 |
| `claimed_by` | `VARCHAR(100) NULL` | 認領此提醒的操作人員識別。 | 人工操作事實 | claim 成功時寫入 Server 驗證過的登入身分；resolved 警示復發時清空。 | authenticated server principal。 | 哪位已驗證人員承接此提醒。 | 保留；前端請求不得傳入或覆寫 operator。尚未接妥登入機制前的 caller label 只能視為不可信過渡資料，不得當正式稽核身分。 | System Alert Service | claim／復發 | claimed 期間保留 | 現況 API 直接採用 `request.operator`，使用者可冒用他人名稱。 | 已確認：只接受 Server 驗證身分 |
| `claimed_at` | `DATETIME NULL` | 認領時間。 | 技術事件時間 | claim 成功時由 Server UTC clock 寫入；復發時清空。 | Server clock。 | claim 命令成功時點。 | 與 `claimed_by` 同步成對存在，前端不得指定。 | System Alert Service | claim／復發 | claimed 期間保留 | 若狀態與欄位不成對會產生矛盾。 | 已確認：依認領命令由 Server 寫入 |
| `resolved_by` | `VARCHAR(100) NULL` | 最後一次解除提醒的操作人員或固定 system actor。 | 解除操作事實 | 人工 resolve 寫入 Server 驗證身分；自動解除寫入固定 system actor；復發時清空。 | authenticated server principal／detector。 | 誰完成解除決策。 | 保留；人工解除不得接受前端自填 operator，自動解除使用固定 system actor。 | System Alert Service | resolve／復發 | resolved 期間保留 | 現況人工 resolve 同樣直接採用 `request.operator`，可冒用他人名稱。 | 已確認：套用相同 Server 身分權威規則 |
| `resolved_at` | `DATETIME NULL` | 最後一次解除時間。 | 技術事件時間 | resolve 成功時由 Server UTC clock 寫入；復發時清空。 | Server clock。 | resolve 命令成功時點。 | 與 `resolved_by`、`resolution_reason` 同步成組，前端不得指定。 | System Alert Service | resolve／復發 | resolved 期間保留 | 本表不保存多次解除歷史。 | 已確認：依解除命令由 Server 寫入 |
| `resolution_reason` | `VARCHAR(500) NULL` | 最近一次人工或系統解除的說明。 | 目前狀態說明事實（不具業務權威性） | 人工輸入或 detector 固定原因；由 `resolved_by` 區分人工與 system，復發時清空。 | resolve 命令／自動掃描。 | 當次解除決策的說明。 | 保留單一欄位供人員理解；不拆人工／系統欄位，不作異常是否存在的判斷來源，也不視為完整事件歷史。 | System Alert Service | resolve／復發 | resolved 期間保留 | 復發後前次原因不保留；不適合作稽核歷史。 | 已確認：保留最近一次解除說明 |
| `created_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | 此唯一警示列第一次建立時間。 | 技術建立時間 | DB default。 | DB INSERT。 | `alert_code + case_key` 第一次被持久化的時點。 | 保留作首次發現時間；復發不得重設。 | DB | 首次建立 | 不變 | 不代表最近一次復發時間。 | 已確認：沿用技術建立時間規則 |
| `updated_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` | 此列最後一次實際更新時間；列表依此排序。 | 技術更新時間 | DB on-update；Service 部分路徑亦明確寫入 UTC now。 | DB／System Alert Service。 | 任一持久欄位最後變動時點。 | 保留作列表排序與技術追蹤；只代表列更新，不等同異常首次發生、最近復發或解除時間。 | DB／System Alert Service | upsert、claim、resolve | 持續更新 | 同內容重掃不更新；其語意不是「最後掃描時間」。 | 已確認：沿用技術更新時間規則 |
